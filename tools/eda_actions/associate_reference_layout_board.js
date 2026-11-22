// Resume one exact imported-reference Board creation using registered orphan PCB/schematic IDs.
const a=__CLI__.args||{};const api=typeof eda==="undefined"?null:eda;
const fail=(status,reason,extra={})=>({ok:false,status,reason,...extra});
try{
  for(const [group,method] of [["dmt_Project","getCurrentProjectInfo"],["dmt_Project","waitForReady"],
    ["dmt_Board","getAllBoardsInfo"],["dmt_Board","createBoard"],["dmt_Pcb","getAllPcbsInfo"],
    ["dmt_Schematic","getAllSchematicsInfo"],["dmt_EditorControl","openDocument"],
    ["dmt_EditorControl","activateDocument"],["dmt_EditorControl","waitForDocumentReady"],
    ["dmt_SelectControl","getCurrentDocumentInfo"],["pcb_Document","importChanges"],
    ["pcb_PrimitiveComponent","getAll"],["pcb_PrimitiveLine","getAll"],
    ["pcb_PrimitiveVia","getAll"],["pcb_PrimitivePolyline","getAll"],["pcb_Net","getAllNetsName"]])
    if(typeof api?.[group]?.[method]!=="function")return fail("unsupported",`${group}.${method} is absent`);
  const project=await api.dmt_Project.getCurrentProjectInfo();
  if(project?.uuid!==a.expected_project_uuid)return fail("target_mismatch","Active project differs from the registered imported project");
  if(await api.dmt_Project.waitForReady(project.uuid,30000)!==true)return fail("unavailable","Project tree is not ready");
  let boards=await api.dmt_Board.getAllBoardsInfo(),pcbs=await api.dmt_Pcb.getAllPcbsInfo(),schematics=await api.dmt_Schematic.getAllSchematicsInfo();
  if(!Array.isArray(boards)||!Array.isArray(pcbs)||!Array.isArray(schematics)||boards.length>64||pcbs.length>128||schematics.length>128)
    return fail("unsupported","Project document inventory is invalid or exceeds local limits");
  const source=boards.filter(board=>board?.parentProjectUuid===project.uuid&&board?.name===a.source_board_name&&board?.pcb?.uuid===a.source_pcb_uuid);
  if(source.length!==1||a.layout_pcb_uuid===a.source_pcb_uuid||a.layout_schematic_uuid===a.source_schematic_uuid||
      !pcbs.some(pcb=>pcb.uuid===a.source_pcb_uuid&&pcb.parentProjectUuid===project.uuid)||
      !pcbs.some(pcb=>pcb.uuid===a.layout_pcb_uuid&&pcb.parentProjectUuid===project.uuid)||
      !schematics.some(schematic=>schematic.uuid===a.layout_schematic_uuid&&schematic.parentProjectUuid===project.uuid))
    return fail("target_mismatch","Source and orphan layout document identities are not present as distinct project documents");
  let associated=boards.filter(board=>board?.parentProjectUuid===project.uuid&&board?.pcb?.uuid===a.layout_pcb_uuid);
  let boardName;
  if(associated.length===0){
    boardName=await api.dmt_Board.createBoard(a.layout_schematic_uuid,a.layout_pcb_uuid);
    if(typeof boardName!=="string"||!boardName)
      return fail("partial","EDA did not associate the registered PCB/schematic documents",{layout_pcb_uuid:a.layout_pcb_uuid});
    if(await api.dmt_Project.waitForReady(project.uuid,30000)!==true)
      return fail("partial","Board association started but the project tree did not settle",{layout_board_name:boardName});
    boards=await api.dmt_Board.getAllBoardsInfo();
    associated=Array.isArray(boards)?boards.filter(board=>board?.parentProjectUuid===project.uuid&&board?.pcb?.uuid===a.layout_pcb_uuid):[];
  }
  if(associated.length!==1||associated[0]?.schematic?.uuid!==a.layout_schematic_uuid)
    return fail("target_mismatch","Registered layout PCB is associated with an unexpected Board or schematic");
  boardName=associated[0].name;
  const tab=await api.dmt_EditorControl.openDocument(a.layout_pcb_uuid);
  if(typeof tab!=="string"||!tab||await api.dmt_EditorControl.activateDocument(tab)!==true||
      await api.dmt_EditorControl.waitForDocumentReady(tab,30000)!==true)
    return fail("unavailable","Fresh PCB could not be opened");
  const focus=await api.dmt_SelectControl.getCurrentDocumentInfo();
  if(focus?.uuid!==a.layout_pcb_uuid||focus?.parentProjectUuid!==project.uuid||focus?.documentType!==3)
    return fail("target_mismatch","Focus differs from the exact fresh PCB");
  let components=await api.pcb_PrimitiveComponent.getAll();
  const importResults=[];
  if(!Array.isArray(components))return fail("incomplete","Fresh PCB component inventory is invalid");
  if(components.length===0){
    let imported=await api.pcb_Document.importChanges(a.layout_schematic_uuid,true);
    importResults.push({explicit_schematic_uuid:true,force:true,result:imported===true});
    components=await api.pcb_PrimitiveComponent.getAll();
    if(imported!==true&&Array.isArray(components)&&components.length===0){
      imported=await api.pcb_Document.importChanges(undefined,true);
      importResults.push({explicit_schematic_uuid:false,force:true,result:imported===true});
      components=await api.pcb_PrimitiveComponent.getAll();
    }
  }
  const lines=await api.pcb_PrimitiveLine.getAll(),vias=await api.pcb_PrimitiveVia.getAll();
  const outlines=await api.pcb_PrimitivePolyline.getAll("",11),nets=await api.pcb_Net.getAllNetsName();
  const finalBoards=await api.dmt_Board.getAllBoardsInfo(),finalFocus=await api.dmt_SelectControl.getCurrentDocumentInfo();
  const sourceAfter=Array.isArray(finalBoards)?finalBoards.filter(board=>board?.parentProjectUuid===project.uuid&&
    board?.name===a.source_board_name&&board?.pcb?.uuid===a.source_pcb_uuid):[];
  if(finalFocus?.uuid!==a.layout_pcb_uuid||finalFocus?.parentProjectUuid!==project.uuid||finalFocus?.documentType!==3)
    return fail("target_mismatch","Focus changed during layout verification");
  if(sourceAfter.length!==1||!Array.isArray(components)||components.length===0||!Array.isArray(nets)||nets.length===0||
      !Array.isArray(lines)||!Array.isArray(vias)||!Array.isArray(outlines))
    return fail("partial","Fresh schematic import did not produce a complete component/net inventory",
      {importResults,component_count:components?.length??null,net_count:nets?.length??null,source_board_still_present:sourceAfter.length===1});
  return {ok:true,status:"fresh_board_ready",project_uuid:project.uuid,source_board_name:a.source_board_name,
    source_pcb_uuid:a.source_pcb_uuid,source_board_still_present:true,
    source_board_association_intact:sourceAfter[0].schematic?.uuid===a.source_schematic_uuid,
    layout_board_name:boardName,layout_pcb_uuid:a.layout_pcb_uuid,layout_schematic_uuid:a.layout_schematic_uuid,
    component_count:components.length,net_count:nets.length,import_results:importResults,
    existing_track_count:lines.length,existing_via_count:vias.length,existing_outline_count:outlines.length,
    layout_ready_for_placement:lines.length===0&&vias.length===0&&outlines.length===0,layout_copied:false};
}catch(error){return fail("rejected",String(error?.message??error));}
