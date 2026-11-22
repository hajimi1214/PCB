// Create a fresh PCB associated with a selected source schematic in a managed copy.
const a = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
const fail = (status, reason, extra = {}) => ({ok:false,status,reason,...extra});
try {
  for (const [group,method] of [
    ["dmt_Project","getCurrentProjectInfo"],["dmt_Project","waitForReady"],
    ["dmt_Board","getAllBoardsInfo"],["dmt_Board","createBoard"],
    ["dmt_Pcb","createPcb"],
    ["dmt_Schematic","copySchematic"],["dmt_Schematic","getAllSchematicsInfo"],
    ["dmt_EditorControl","openDocument"],["dmt_EditorControl","activateDocument"],
    ["dmt_EditorControl","waitForDocumentReady"],["dmt_SelectControl","getCurrentDocumentInfo"],
    ["pcb_Document","importChanges"],["pcb_PrimitiveComponent","getAll"],
    ["pcb_PrimitiveLine","getAll"],["pcb_PrimitiveVia","getAll"],
    ["pcb_PrimitivePolyline","getAll"],["pcb_Net","getAllNetsName"]
  ]) if (typeof api?.[group]?.[method] !== "function")
    return fail("unsupported",`${group}.${method} is absent`);
  const project = await api.dmt_Project.getCurrentProjectInfo();
  if (project?.uuid !== a.expected_project_uuid)
    return fail("target_mismatch","Selected project differs from the explicit working-copy identity");
  const before = await api.dmt_Board.getAllBoardsInfo();
  if (!Array.isArray(before) || before.length > 64)
    return fail("unsupported","Working-copy Board tree is invalid or exceeds the local limit");
  const sources = before.filter(board => board?.parentProjectUuid === project.uuid &&
    board?.name === a.source_board_name && board?.pcb?.uuid === a.source_pcb_uuid);
  if (sources.length !== 1)
    return fail("target_mismatch","Source Board and PCB do not match one exact project Board");
  const source = sources[0];
  if(source.schematic?.uuid && source.schematic.uuid!==a.schematic_uuid)
    return fail("target_mismatch","The selected source schematic differs from the source Board association");
  const schematics=await api.dmt_Schematic.getAllSchematicsInfo();
  if(!Array.isArray(schematics)||!schematics.some(item=>item.uuid===a.schematic_uuid&&item.parentProjectUuid===project.uuid))
    return fail("target_mismatch","The selected source schematic is absent from the imported reference project");
  const layoutSchematicUuid=await api.dmt_Schematic.copySchematic(a.schematic_uuid);
  if(typeof layoutSchematicUuid!=="string"||!layoutSchematicUuid||layoutSchematicUuid===a.schematic_uuid)
    return fail("unavailable","EDA did not create an independent schematic copy; the source Board was not edited");
  if(await api.dmt_Project.waitForReady(project.uuid,30000)!==true)
    return fail("partial","Schematic copy was created but the project tree did not settle",
      {layout_schematic_uuid:layoutSchematicUuid,source_board_untouched:true});
  const pcbUuid = await api.dmt_Pcb.createPcb();
  if (typeof pcbUuid !== "string" || !pcbUuid)
    return fail("unavailable","EDA did not return the new blank PCB identity");
  if(await api.dmt_Project.waitForReady(project.uuid,30000)!==true)
    return fail("partial","Blank PCB was created but the project tree did not settle",{layout_schematic_uuid:layoutSchematicUuid,orphan_pcb_uuid:pcbUuid});
  const boardName = await api.dmt_Board.createBoard(layoutSchematicUuid,pcbUuid);
  if (typeof boardName !== "string" || !boardName)
    return fail("partial","Blank PCB was created but EDA did not confirm Board association",
      {orphan_pcb_uuid:pcbUuid,board_created:false});
  if (await api.dmt_Project.waitForReady(project.uuid,30000) !== true)
    return fail("partial","Board creation started but the project tree did not settle",{board_created:true,board_name:boardName});
  const after = await api.dmt_Board.getAllBoardsInfo();
  const created = Array.isArray(after) ? after.filter(board => board?.parentProjectUuid === project.uuid && board?.name === boardName) : [];
  const original = Array.isArray(after) ? after.filter(board => board?.parentProjectUuid === project.uuid &&
    board?.name === source.name && board?.pcb?.uuid === source.pcb.uuid &&
    (!source.schematic?.uuid || board?.schematic?.uuid === source.schematic.uuid)) : [];
  if (created.length !== 1 || original.length !== 1 || !created[0]?.pcb?.uuid ||
      created[0].pcb.uuid === source.pcb.uuid || created[0].schematic?.uuid !== layoutSchematicUuid)
    return fail("partial","EDA created a Board whose source association or original preservation could not be verified",
      {board_created:true,board_name:boardName,source_board_still_present:original.length === 1});
  if(created[0].pcb.uuid!==pcbUuid)
    return fail("target_mismatch","EDA associated a different PCB with the new Board",
      {board_created:true,board_name:boardName,pcb_uuid:created[0].pcb.uuid,orphan_pcb_uuid:pcbUuid,source_board_still_present:true});
  const sourceAfter=Array.isArray(after)?after.filter(board=>board?.parentProjectUuid===project.uuid&&
    board?.name===source.name&&board?.pcb?.uuid===source.pcb.uuid&&
    (!source.schematic?.uuid||board?.schematic?.uuid===source.schematic.uuid)):[];
  if(sourceAfter.length!==1)
    return fail("partial","Fresh Board creation did not preserve the source PCB document",
      {board_created:true,board_name:boardName,pcb_uuid:pcbUuid,layout_schematic_uuid:layoutSchematicUuid});
  const tabId = await api.dmt_EditorControl.openDocument(pcbUuid);
  if (typeof tabId !== "string" || !tabId || await api.dmt_EditorControl.activateDocument(tabId) !== true ||
      await api.dmt_EditorControl.waitForDocumentReady(tabId,30000) !== true)
    return fail("partial","New PCB was created but could not be activated for schematic import",
      {board_created:true,board_name:boardName,pcb_uuid:pcbUuid,source_board_still_present:true});
  const focus = await api.dmt_SelectControl.getCurrentDocumentInfo();
  if (focus?.uuid !== pcbUuid || focus?.parentProjectUuid !== project.uuid || focus?.documentType !== 3)
    return fail("target_mismatch","Focus changed before the new PCB schematic import",
      {board_created:true,board_name:boardName,pcb_uuid:pcbUuid,source_board_still_present:true});
  const imported = await api.pcb_Document.importChanges(layoutSchematicUuid);
  if (imported !== true)
    return fail("partial","Blank PCB exists but schematic changes were not imported",
      {board_created:true,board_name:boardName,pcb_uuid:pcbUuid,source_board_still_present:true});
  const components = await api.pcb_PrimitiveComponent.getAll();
  const lines = await api.pcb_PrimitiveLine.getAll();
  const vias = await api.pcb_PrimitiveVia.getAll();
  const outlines = await api.pcb_PrimitivePolyline.getAll("",11);
  const nets = await api.pcb_Net.getAllNetsName();
  const focused = await api.dmt_SelectControl.getCurrentDocumentInfo();
  if (focused?.uuid !== pcbUuid || focused?.parentProjectUuid !== project.uuid || focused?.documentType !== 3)
    return fail("target_mismatch","Focus changed during new-board verification",
      {board_created:true,board_name:boardName,pcb_uuid:pcbUuid,source_board_still_present:true});
  if (!Array.isArray(components) || components.length === 0 || !Array.isArray(nets) || nets.length === 0 ||
      !Array.isArray(lines) || !Array.isArray(vias) || !Array.isArray(outlines))
    return fail("incomplete","Schematic import did not produce a verifiable component/net inventory",
      {board_created:true,board_name:boardName,pcb_uuid:pcbUuid,source_board_still_present:true});
  return {ok:true,status:"fresh_board_ready",board_name:boardName,pcb_uuid:pcbUuid,
    schematic_uuid:layoutSchematicUuid,source_schematic_uuid:a.schematic_uuid,project_uuid:project.uuid,source_board_still_present:true,
    source_board_association_intact:source.schematic?.uuid===a.schematic_uuid,
    component_count:components.length,net_count:nets.length,existing_track_count:lines.length,
    existing_via_count:vias.length,existing_outline_count:outlines.length,
    layout_copied:false,layout_ready_for_placement:lines.length===0 && vias.length===0 && outlines.length===0,
    limitation:"A fresh board and schematic-derived component inventory are created. Placement, board outline, routing, DRC, manufacturing and functional checks remain separate steps."};
} catch (error) {
  return fail("rejected",String(error?.message ?? error));
}
