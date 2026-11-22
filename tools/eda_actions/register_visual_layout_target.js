// Register one exact blank PCB in an imported public project for footprint-only visual testing.
const a=__CLI__.args||{};const api=typeof eda==="undefined"?null:eda;
const fail=(status,reason)=>({ok:false,status,reason});
try{
  for(const [group,method] of [["dmt_Project","getCurrentProjectInfo"],["dmt_Board","getAllBoardsInfo"],
    ["dmt_Pcb","getAllPcbsInfo"],["dmt_EditorControl","openDocument"],["dmt_EditorControl","activateDocument"],
    ["dmt_EditorControl","waitForDocumentReady"],["dmt_SelectControl","getCurrentDocumentInfo"],
    ["pcb_PrimitiveComponent","getAll"],["pcb_PrimitiveLine","getAll"],["pcb_PrimitiveVia","getAll"],
    ["pcb_PrimitivePolyline","getAll"],["pcb_Net","getAllNetsName"]])
    if(typeof api?.[group]?.[method]!=="function")return fail("unsupported",`${group}.${method} is absent`);
  const project=await api.dmt_Project.getCurrentProjectInfo();
  if(project?.uuid!==a.expected_project_uuid)return fail("target_mismatch","Active project differs from registered reference");
  const boards=await api.dmt_Board.getAllBoardsInfo(),pcbs=await api.dmt_Pcb.getAllPcbsInfo();
  const source=Array.isArray(boards)?boards.filter(b=>b?.parentProjectUuid===project.uuid&&b?.name===a.source_board_name&&b?.pcb?.uuid===a.source_pcb_uuid):[];
  const target=Array.isArray(boards)?boards.filter(b=>b?.parentProjectUuid===project.uuid&&b?.name===a.layout_board_name&&b?.pcb?.uuid===a.layout_pcb_uuid):[];
  if(source.length!==1||target.length!==1||a.layout_pcb_uuid===a.source_pcb_uuid||
      !Array.isArray(pcbs)||!pcbs.some(p=>p.uuid===a.layout_pcb_uuid&&p.parentProjectUuid===project.uuid))
    return fail("target_mismatch","Visual target is not one exact PCB in the imported project, distinct from its reference");
  const tab=await api.dmt_EditorControl.openDocument(a.layout_pcb_uuid);
  if(typeof tab!=="string"||!tab||await api.dmt_EditorControl.activateDocument(tab)!==true||
      await api.dmt_EditorControl.waitForDocumentReady(tab,30000)!==true)
    return fail("unavailable","Visual target PCB did not become ready");
  const focus=await api.dmt_SelectControl.getCurrentDocumentInfo();
  if(focus?.uuid!==a.layout_pcb_uuid||focus?.parentProjectUuid!==project.uuid||focus?.documentType!==3)
    return fail("target_mismatch","Focus differs from the exact visual target PCB");
  const components=await api.pcb_PrimitiveComponent.getAll();
  const lines=await api.pcb_PrimitiveLine.getAll();const vias=await api.pcb_PrimitiveVia.getAll();
  const outlines=await api.pcb_PrimitivePolyline.getAll("",11);const nets=await api.pcb_Net.getAllNetsName();
  if(!Array.isArray(components)||!Array.isArray(lines)||!Array.isArray(vias)||!Array.isArray(outlines)||!Array.isArray(nets))
    return fail("incomplete","Visual target inventories could not be read");
  if(components.length||lines.length||vias.length||outlines.length)
    return fail("rejected","Visual target is not geometrically blank; refusing to register it as a fresh layout");
  return {ok:true,status:"blank_visual_target_registered",project_uuid:project.uuid,
    source_board_name:a.source_board_name,source_pcb_uuid:a.source_pcb_uuid,source_board_still_present:true,
    source_board_schematic_uuid:source[0].schematic?.uuid??null,
    layout_board_name:target[0].name,layout_pcb_uuid:a.layout_pcb_uuid,
    layout_schematic_uuid:target[0].schematic?.uuid??null,component_count:0,track_count:0,via_count:0,outline_count:0,
    existing_net_count:nets.length,layout_mode:"visual-only-footprints",schematic_linked_devices:false};
}catch(error){return fail("unavailable",String(error?.message??error));}
