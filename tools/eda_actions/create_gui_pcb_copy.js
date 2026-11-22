// Duplicate a complete Board (schematic + PCB) in the current project.
try{
  const a=__CLI__.args;
  const api=typeof eda==="undefined"?null:eda;
  const fail=(status,reason)=>({ok:false,status,reason});
  const has=(g,m)=>typeof api?.[g]?.[m]==="function";
  for(const [g,m] of [["dmt_Project","getCurrentProjectInfo"],["dmt_Board","getAllBoardsInfo"],
    ["dmt_Board","copyBoard"],["dmt_Project","waitForReady"]])
    if(!has(g,m))return fail("unsupported",g+"."+m+" is absent");
  const project=await api.dmt_Project.getCurrentProjectInfo();
  if(project?.uuid!==a.expected_project_uuid)return fail("target_mismatch","Current project differs from the explicit project UUID");
  const before=await api.dmt_Board.getAllBoardsInfo();
  if(!Array.isArray(before)||before.length>64)return fail("unavailable","Board tree is invalid or exceeds test-copy limits");
  const sources=before.filter(b=>b?.parentProjectUuid===project.uuid&&b.pcb?.uuid===a.source_pcb_uuid);
  if(sources.length!==1||!sources[0].schematic?.uuid)return fail("target_mismatch","Source PCB must belong to one Board with a schematic");
  const source=sources[0];
  const newBoardName=await api.dmt_Board.copyBoard(source.name);
  if(typeof newBoardName!=="string"||!newBoardName)return fail("unavailable","EDA did not return the copied Board identity");
  if(await api.dmt_Project.waitForReady(project.uuid,30000)!==true)return fail("unavailable","Project tree did not settle after copy creation");
  const after=await api.dmt_Board.getAllBoardsInfo();
  const copy=Array.isArray(after)?after.find(b=>b?.name===newBoardName&&b.parentProjectUuid===project.uuid):undefined;
  const sourceAfter=Array.isArray(after)?after.find(b=>b?.name===source.name&&b.pcb?.uuid===source.pcb.uuid):undefined;
  const newBoards=Array.isArray(after)?after.filter(b=>!before.some(old=>old.name===b.name&&old.pcb?.uuid===b.pcb?.uuid)):[];
  if(!copy||!sourceAfter||newBoards.length!==1||newBoards[0].name!==copy.name||!copy.pcb?.uuid||!copy.schematic?.uuid||
      copy.pcb.uuid===source.pcb.uuid||copy.schematic.uuid===source.schematic.uuid)
    return fail("target_mismatch","Copied Board, schematic and PCB identities could not be verified");
  return {ok:true,status:"observed",project_uuid:project.uuid,source_board_name:source.name,
    source_pcb_uuid:source.pcb.uuid,source_schematic_uuid:source.schematic.uuid,
    copy_board_name:copy.name,copy_pcb_uuid:copy.pcb.uuid,copy_schematic_uuid:copy.schematic.uuid,
    cleanup_required:true,source_geometry_modified:false};
}catch(e){return {ok:false,status:"rejected",reason:String(e.message)};}
