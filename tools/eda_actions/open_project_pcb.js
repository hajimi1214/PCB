// Explicitly focus one PCB inside the already selected project after identity checks.
const a=__CLI__.args;
const api=typeof eda==="undefined"?null:eda;
const has=(g,m)=>typeof api?.[g]?.[m]==="function";
const fail=(status,reason)=>({ok:false,status,reason});
for(const [g,m] of [["dmt_Project","getCurrentProjectInfo"],["dmt_Board","getAllBoardsInfo"],
                    ["dmt_EditorControl","openDocument"],["dmt_EditorControl","activateDocument"],["dmt_EditorControl","waitForDocumentReady"],
                    ["dmt_SelectControl","getCurrentDocumentInfo"]])
  if(!has(g,m))return fail("unsupported",`${g}.${m} is absent.`);
if(typeof a.pcb_uuid!=="string"||!a.pcb_uuid||typeof a.expected_project_uuid!=="string"||!a.expected_project_uuid)
  return fail("rejected","Explicit project and PCB UUIDs are required.");
const project=await api.dmt_Project.getCurrentProjectInfo();
if(project?.uuid!==a.expected_project_uuid)return fail("target_mismatch","Selected project differs from the explicit UUID.");
const boards=await api.dmt_Board.getAllBoardsInfo();
if(!Array.isArray(boards)||boards.length>64)return fail("unsupported","Board tree response is invalid or too large.");
const matched=boards.filter(b=>b?.parentProjectUuid===project.uuid&&b?.pcb?.uuid===a.pcb_uuid);
if(matched.length!==1)return fail("target_mismatch","PCB is not uniquely associated with a Board in the selected project.");
const opened=await api.dmt_EditorControl.openDocument(a.pcb_uuid);
if(typeof opened!=="string"||!opened)return fail("unavailable","EDA did not open the target PCB tab.");
if(await api.dmt_EditorControl.activateDocument(opened)!==true)return fail("unavailable","EDA did not activate the target PCB tab.");
const ready=await api.dmt_EditorControl.waitForDocumentReady(opened,20000);
const current=await api.dmt_SelectControl.getCurrentDocumentInfo();
const afterProject=await api.dmt_Project.getCurrentProjectInfo();
if(afterProject?.uuid!==project.uuid||current?.uuid!==a.pcb_uuid||current.parentProjectUuid!==project.uuid||current.documentType!==3)
  return fail("target_mismatch","Opened PCB identity did not match the requested target.");
if(ready!==true)return fail("unavailable","PCB document did not become ready; no edits were made.");
return {ok:true,status:"observed",read_only:true,project_uuid:project.uuid,pcb_uuid:current.uuid,
  board_name:matched[0].name,pcb_name:matched[0].pcb.name,limitation:"Opening a document only changes editor focus; no project geometry was modified."};
