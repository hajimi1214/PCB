// Delete only the exact registered Board clone after proving its original Board remains.
try{
  const a=__CLI__.args,api=typeof eda==="undefined"?null:eda;
  const fail=(status,reason)=>({ok:false,status,reason});
  const has=(g,m)=>typeof api?.[g]?.[m]==="function";
  for(const [g,m] of [["dmt_Project","getCurrentProjectInfo"],["dmt_Board","getAllBoardsInfo"],
    ["dmt_Board","deleteBoard"],["dmt_Project","waitForReady"]])
    if(!has(g,m))return fail("unsupported",g+"."+m+" is absent");
  const project=await api.dmt_Project.getCurrentProjectInfo();
  if(project?.uuid!==a.expected_project_uuid)return fail("target_mismatch","Current project differs from the registered test copy");
  if(a.copy_pcb_uuid===a.source_pcb_uuid||a.copy_schematic_uuid===a.source_schematic_uuid)return fail("rejected","Copy Board must have distinct PCB and schematic identities");
  const before=await api.dmt_Board.getAllBoardsInfo();
  const sources=Array.isArray(before)?before.filter(b=>b.parentProjectUuid===project.uuid&&b.pcb?.uuid===a.source_pcb_uuid&&b.schematic?.uuid===a.source_schematic_uuid):[];
  const copies=Array.isArray(before)?before.filter(b=>b.parentProjectUuid===project.uuid&&b.name===a.copy_board_name&&b.pcb?.uuid===a.copy_pcb_uuid&&b.schematic?.uuid===a.copy_schematic_uuid):[];
  if(sources.length!==1)return fail("target_mismatch","Original Board and its schematic/PCB are absent");
  if(copies.length!==1)return fail("target_mismatch","Registered cloned Board, schematic and PCB are absent");
  if(await api.dmt_Board.deleteBoard(copies[0].name)!==true)return fail("rejected","EDA did not confirm deletion of the registered test Board");
  if(await api.dmt_Project.waitForReady(project.uuid,30000)!==true)return fail("unavailable","Project tree did not settle after cleanup");
  const after=await api.dmt_Board.getAllBoardsInfo();
  if(!Array.isArray(after)||after.some(x=>x.name===copies[0].name&&(x.pcb?.uuid===a.copy_pcb_uuid||x.schematic?.uuid===a.copy_schematic_uuid))||
      !after.some(x=>x.pcb?.uuid===a.source_pcb_uuid&&x.schematic?.uuid===a.source_schematic_uuid))
    return fail("target_mismatch","Cleanup verification failed; inspect the project tree");
  return {ok:true,status:"observed",project_uuid:project.uuid,deleted_copy_board_name:copies[0].name,
    deleted_copy_pcb_uuid:a.copy_pcb_uuid,deleted_copy_schematic_uuid:a.copy_schematic_uuid,
    source_pcb_still_present:true,source_schematic_still_present:true,cleanup_verified:true};
}catch(e){return {ok:false,status:"rejected",reason:String(e.message)};}
