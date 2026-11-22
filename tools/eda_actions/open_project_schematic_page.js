// Open one exact Board-associated schematic page without changing schematic data.
const a=__CLI__.args||{};const api=typeof eda==="undefined"?null:eda;
const fail=(status,reason)=>({ok:false,status,reason});
try{
  for(const [group,method] of [["dmt_Project","getCurrentProjectInfo"],["dmt_Board","getAllBoardsInfo"],
    ["dmt_EditorControl","openDocument"],["dmt_EditorControl","activateDocument"],["dmt_EditorControl","waitForDocumentReady"],
    ["dmt_SelectControl","getCurrentDocumentInfo"]])
    if(typeof api?.[group]?.[method]!=="function")return fail("unsupported",`${group}.${method} is absent`);
  const project=await api.dmt_Project.getCurrentProjectInfo();
  if(project?.uuid!==a.expected_project_uuid)return fail("target_mismatch","Selected project differs from the expected project UUID");
  const boards=await api.dmt_Board.getAllBoardsInfo();
  if(!Array.isArray(boards)||boards.length>64)return fail("unsupported","Board tree is invalid or exceeds the local limit");
  const matches=boards.filter(board=>board?.parentProjectUuid===project.uuid&&board?.name===a.board_name&&
    board?.pcb?.uuid===a.pcb_uuid&&board?.schematic?.uuid===a.schematic_uuid&&
    (board.schematic.page||[]).some(page=>page.uuid===a.page_uuid));
  if(matches.length!==1)return fail("target_mismatch","Schematic page is not uniquely associated with the requested Board and PCB");
  const tab=await api.dmt_EditorControl.openDocument(a.page_uuid);
  if(typeof tab!=="string"||!tab||await api.dmt_EditorControl.activateDocument(tab)!==true||
      await api.dmt_EditorControl.waitForDocumentReady(tab,30000)!==true)return fail("unavailable","Schematic page did not become ready");
  const doc=await api.dmt_SelectControl.getCurrentDocumentInfo();
  if(doc?.uuid!==a.page_uuid||doc?.documentType!==1||doc?.parentProjectUuid!==project.uuid)
    return fail("target_mismatch","Focused schematic page differs from the exact requested page");
  return {ok:true,status:"observed",read_only:true,project_uuid:project.uuid,board_name:a.board_name,
    pcb_uuid:a.pcb_uuid,schematic_uuid:a.schematic_uuid,page_uuid:a.page_uuid};
}catch(error){return fail("unavailable",String(error?.message??error));}
