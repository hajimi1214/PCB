// Fixed, read-only action body. CLI supplies __CLI__.args; no user source code.
const args = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
if (!api) return {ok: false, status: "unsupported", reason: "EDA API is absent."};
const has = (group, method) => typeof api[group]?.[method] === "function";
const capabilities = {};
for (const [group, methods] of Object.entries({
  sys_Environment: ["getEditorCurrentVersion", "isClient", "isJLCEDAProEdition"],
  lib_Device: ["get"],
  lib_Footprint: ["get"],
  lib_LibrariesList: ["getSystemLibraryUuid", "getProjectLibraryUuid"],
  dmt_SelectControl: ["getCurrentDocumentInfo"],
  dmt_Project: ["getCurrentProjectInfo", "waitForReady"],
  dmt_Board: ["getAllBoardsInfo", "createBoard"],
  dmt_Schematic: ["getAllSchematicsInfo", "copySchematic"],
  dmt_Team: ["getAllTeamsInfo"],
  dmt_EditorControl: ["openDocument", "activateDocument", "waitForDocumentReady"],
  pcb_PrimitiveComponent: ["getAll", "get", "modify", "create"],
  pcb_PrimitiveLine: ["getAll", "get", "create"],
  pcb_PrimitiveVia: ["getAll", "get", "create"],
  pcb_Layer: ["getAllLayers"],
  pcb_Net: ["getAllNets", "getAllNetsName"],
  sch_ManufactureData: ["getNetlistFile"],
  pcb_ManufactureData: ["getNetlistFile", "getGerberFile", "getBomFile", "getPickAndPlaceFile"],
  pcb_Drc: ["getDrcResult", "checkDetailed"],
  sys_FileManager: ["getDocumentSource", "getProjectFile", "importProjectByProjectFile"],
  sys_FileSystem: ["saveFileToFileSystem", "readFileFromFileSystem"],
  pcb_Document: ["beginCommandGroup", "commitCommandGroup", "rollbackCommandGroup", "startAutoRouting", "getAutoJobStatus", "cancelAutoJob", "getAutoJobLog", "getRatlines", "importChanges"],
  pcb_PrimitivePolyline: ["create", "get", "getAll"],
  pcb_MathPolygon: ["createPolygon"],
  pcb_PrimitiveLine: ["create", "get"],
  pcb_PrimitiveVia: ["create", "get"]
})) for (const method of methods) capabilities[`${group}.${method}`] = has(group, method);
let current = null;
if (has("dmt_SelectControl", "getCurrentDocumentInfo")) current = await api.dmt_SelectControl.getCurrentDocumentInfo();
if (args.expected_document_uuid && current?.uuid !== args.expected_document_uuid)
  return {ok: false, status: "target_mismatch", reason: "Focused document differs from the requested UUID."};
return {
  ok: true, status: "observed", read_only: true,
  version: has("sys_Environment", "getEditorCurrentVersion") ? api.sys_Environment.getEditorCurrentVersion() : null,
  is_client: has("sys_Environment", "isClient") ? api.sys_Environment.isClient() : null,
  is_jlceda_pro: has("sys_Environment", "isJLCEDAProEdition") ? api.sys_Environment.isJLCEDAProEdition() : null,
  current_document: current ? {uuid: current.uuid, document_type: current.documentType, project_uuid: current.parentProjectUuid} : null,
  runtime_primitives: {
    web_crypto_sha256: typeof globalThis.crypto?.subtle?.digest === "function",
    file_array_buffer: typeof File !== "undefined" && typeof File.prototype.arrayBuffer === "function"
  },
  capabilities,
  limitation: "Method presence is not a successful operation or a board verification."
};
