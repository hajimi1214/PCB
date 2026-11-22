// Project-tree reads only. Works from either the project home screen or a focused project document.
const args = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
const has = (g, m) => typeof api?.[g]?.[m] === "function";
let stage="capability-probe";
try{
for (const [g, m] of [["dmt_SelectControl", "getCurrentDocumentInfo"], ["dmt_Project", "getCurrentProjectInfo"], ["dmt_Board", "getAllBoardsInfo"], ["dmt_Pcb","getAllPcbsInfo"], ["dmt_Schematic","getAllSchematicsInfo"]])
  if (!has(g, m)) return {ok: false, status: "unsupported", reason: `${g}.${m} is absent.`};
stage="read-current-document";
const current = await api.dmt_SelectControl.getCurrentDocumentInfo();
stage="read-project";
const project = await api.dmt_Project.getCurrentProjectInfo();
if (!project?.uuid) return {ok: false, status: "unavailable", reason: "No current project is selected in EDA."};
if (args.expected_project_uuid && project.uuid !== args.expected_project_uuid)
  return {ok: false, status: "target_mismatch", reason: "Current project differs from the requested UUID."};
if (current?.parentProjectUuid && current.parentProjectUuid !== project.uuid)
  return {ok: false, status: "target_mismatch", reason: "Focused document belongs to another project."};
if (args.expected_document_uuid && current?.uuid !== args.expected_document_uuid)
  return {ok: false, status: "target_mismatch", reason: "Focused document differs from the requested UUID."};
stage="read-board-tree";
const boards = await api.dmt_Board.getAllBoardsInfo();
if (!Array.isArray(boards)||boards.length>64||boards.some(b=>!b||typeof b.name!=="string")) return {ok: false, status: "unsupported", reason: "Unexpected Board tree response."};
if (boards.some(b => b.parentProjectUuid !== project.uuid))
  return {ok: false, status: "target_mismatch", reason: "Board tree includes a different project."};
stage="read-pcbs";
const pcbs=await api.dmt_Pcb.getAllPcbsInfo();
if(!Array.isArray(pcbs)||pcbs.length>128||pcbs.some(p=>!p||typeof p.uuid!=="string"))return {ok:false,status:"unsupported",reason:"PCB document listing is invalid or exceeds the local limit."};
if(pcbs.some(p=>p.parentProjectUuid!==project.uuid))return {ok:false,status:"target_mismatch",reason:"PCB list includes another project."};
stage="read-schematics";
const schematics=await api.dmt_Schematic.getAllSchematicsInfo();
if(!Array.isArray(schematics)||schematics.length>128||schematics.some(s=>!s||typeof s.uuid!=="string"))return {ok:false,status:"unsupported",reason:"Schematic document listing is invalid or exceeds the local limit."};
if(schematics.some(s=>s.parentProjectUuid!==project.uuid))return {ok:false,status:"target_mismatch",reason:"Schematic list includes another project."};
stage="verify-focus";
const after = await api.dmt_SelectControl.getCurrentDocumentInfo();
const projectAfter = await api.dmt_Project.getCurrentProjectInfo();
if (projectAfter?.uuid !== project.uuid || after?.uuid !== current?.uuid || after?.parentProjectUuid !== current?.parentProjectUuid)
  return {ok: false, status: "target_mismatch", reason: "Focus changed during inspection; retry with an explicit target."};
return {
  ok: true, status: "observed", read_only: true,
  project: {uuid: project.uuid, name: project.friendlyName},
  current_document: current?.uuid ? {uuid: current.uuid, document_type: current.documentType, project_uuid: current.parentProjectUuid} : null,
  pcbs: pcbs.map(p=>({uuid:p.uuid,name:p.name,parent_board_name:p.parentBoardName??null})),
  schematics: schematics.map(s=>({uuid:s.uuid,name:s.name,parent_board_name:s.parentBoardName??null,
    pages:(s.page||[]).map(p=>({uuid:p.uuid,name:p.name}))})),
  boards: boards.map(b => ({
    name: b.name, project_uuid: b.parentProjectUuid,
    pcb: b.pcb ? {uuid: b.pcb.uuid, name: b.pcb.name} : null,
    schematic: b.schematic ? {uuid: b.schematic.uuid, name: b.schematic.name,
      pages: (b.schematic.page || []).map(p => ({uuid: p.uuid, name: p.name}))} : null
  })),
  limitation: "Board identity is linked by pcb.uuid; the documented Board item has no UUID field. The focused canvas may be empty; no connectivity check was performed."
};
}catch(error){return {ok:false,status:"unavailable",stage,error_name:error?.name??null,error_message:error?.message??null,error_text:String(error)};}
