// Initialize an already registered new PCB from its schematic after Board identity checks.
const a = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
const fail = (status,reason,extra={}) => ({ok:false,status,reason,...extra});
try {
  for (const [group,method] of [
    ["dmt_Project","getCurrentProjectInfo"],["dmt_Project","waitForReady"],
    ["dmt_Board","getAllBoardsInfo"],["dmt_Pcb","getAllPcbsInfo"],
    ["dmt_EditorControl","openDocument"],["dmt_EditorControl","activateDocument"],
    ["dmt_EditorControl","waitForDocumentReady"],["dmt_SelectControl","getCurrentDocumentInfo"],
    ["pcb_Document","importChanges"],["pcb_PrimitiveComponent","getAll"],
    ["pcb_PrimitiveLine","getAll"],["pcb_PrimitiveVia","getAll"],
    ["pcb_PrimitivePolyline","getAll"],["pcb_Net","getAllNetsName"]
  ]) if(typeof api?.[group]?.[method]!=="function")return fail("unsupported",`${group}.${method} is absent`);
  const project=await api.dmt_Project.getCurrentProjectInfo();
  if(project?.uuid!==a.expected_project_uuid)return fail("target_mismatch","Active project differs from the registered reference project");
  const boards=await api.dmt_Board.getAllBoardsInfo();
  const source=Array.isArray(boards)?boards.filter(board=>board?.parentProjectUuid===project.uuid&&
    board?.name===a.source_board_name&&board?.pcb?.uuid===a.source_pcb_uuid):[];
  const target=Array.isArray(boards)?boards.filter(board=>board?.parentProjectUuid===project.uuid&&
    board?.name===a.layout_board_name&&board?.pcb?.uuid===a.layout_pcb_uuid&&
    board?.schematic?.uuid===a.layout_schematic_uuid):[];
  const pcbs=await api.dmt_Pcb.getAllPcbsInfo();
  if(source.length!==1||source[0].pcb.uuid===a.layout_pcb_uuid||target.length!==1||
      a.layout_pcb_uuid===a.source_pcb_uuid||!Array.isArray(pcbs)||
      !pcbs.some(pcb=>pcb.uuid===a.layout_pcb_uuid&&pcb.parentProjectUuid===project.uuid))
    return fail("target_mismatch","Source and fresh-layout Board identities are not distinct and registered");
  const opened=await api.dmt_EditorControl.openDocument(a.layout_pcb_uuid);
  if(typeof opened!=="string"||!opened||await api.dmt_EditorControl.activateDocument(opened)!==true||
      await api.dmt_EditorControl.waitForDocumentReady(opened,30000)!==true)
    return fail("unavailable","The fresh-layout PCB could not be activated");
  await new Promise(resolve=>setTimeout(resolve,1000));
  const focus=await api.dmt_SelectControl.getCurrentDocumentInfo();
  if(focus?.uuid!==a.layout_pcb_uuid||focus?.parentProjectUuid!==project.uuid||focus?.documentType!==3)
    return fail("target_mismatch","Focus changed before fresh schematic import");
  const importResults=[];
  let imported=await api.pcb_Document.importChanges(a.layout_schematic_uuid);
  importResults.push({explicit_schematic_uuid:true,result:imported===true});
  let components=await api.pcb_PrimitiveComponent.getAll();
  if(imported!==true&&Array.isArray(components)&&components.length===0){
    imported=await api.pcb_Document.importChanges();
    importResults.push({explicit_schematic_uuid:false,result:imported===true});
    components=await api.pcb_PrimitiveComponent.getAll();
  }
  if(!Array.isArray(components)||components.length===0)
    return fail("partial","EDA importChanges did not place any schematic-derived components",
      {import_results:importResults,layout_pcb_uuid:a.layout_pcb_uuid});
  const lines=await api.pcb_PrimitiveLine.getAll();
  const vias=await api.pcb_PrimitiveVia.getAll();
  const outlines=await api.pcb_PrimitivePolyline.getAll("",11);
  const nets=await api.pcb_Net.getAllNetsName();
  const finalFocus=await api.dmt_SelectControl.getCurrentDocumentInfo();
  if(finalFocus?.uuid!==a.layout_pcb_uuid||finalFocus?.parentProjectUuid!==project.uuid||finalFocus?.documentType!==3)
    return fail("target_mismatch","Focus changed during fresh PCB verification");
  if(!Array.isArray(components)||components.length===0||!Array.isArray(nets)||nets.length===0||
      !Array.isArray(lines)||!Array.isArray(vias)||!Array.isArray(outlines))
    return fail("incomplete","Schematic-derived component/net inventory could not be verified");
  return {ok:true,status:"fresh_board_ready",project_uuid:project.uuid,source_board_name:a.source_board_name,
    source_pcb_uuid:a.source_pcb_uuid,source_board_still_present:true,
    source_board_association_intact:source[0].schematic?.uuid===a.source_schematic_uuid,
    layout_board_name:a.layout_board_name,layout_pcb_uuid:a.layout_pcb_uuid,
    layout_schematic_uuid:a.layout_schematic_uuid,component_count:components.length,net_count:nets.length,import_results:importResults,
    existing_track_count:lines.length,existing_via_count:vias.length,existing_outline_count:outlines.length,
    layout_ready_for_placement:lines.length===0&&vias.length===0&&outlines.length===0,
    layout_copied:false};
} catch(error){return fail("rejected",String(error?.message??error));}
