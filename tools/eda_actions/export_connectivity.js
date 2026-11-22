// Read the focused PCB or one linked SCH page. No document switching or writes.
const args = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
const has = (g, m) => typeof api?.[g]?.[m] === "function";
const fail = (status, reason, extra = {}) => ({ok: false, status, reason, ...extra});
const readSource = async () => {
  if (!has("sys_FileManager","getDocumentSource")) throw new Error("Document source API unavailable");
  const value = await api.sys_FileManager.getDocumentSource();
  if (typeof value !== "string") throw new Error("Document source unavailable");
  const newline=value.indexOf("\n"),lineEnd=newline<0?value.length:newline;
  const rawHead=value.slice(0,lineEnd).replace(/\r$/,"");
  const tail=newline<0?"":value.slice(newline);
  const split=rawHead.indexOf("||");
  if(split<0)throw new Error("PCB source DOCHEAD delimiter is missing");
  let shell,body;
  try{shell=JSON.parse(rawHead.slice(0,split));body=JSON.parse(rawHead.slice(split+2).replace(/\|$/,""));}
  catch(_){throw new Error("PCB source DOCHEAD is malformed");}
  if(shell?.type!=="DOCHEAD"||body?.uuid!==args.expected_document_uuid)throw new Error("PCB source DOCHEAD target identity differs");
  delete body.updateTime;delete body.client;delete body.version;
  return JSON.stringify(shell)+"||"+JSON.stringify(body)+"|"+tail;
};
const sourceDigest = async value => {
  const digest=await globalThis.crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
};
if (!args.pcb_uuid || !args.expected_document_uuid || !args.expected_project_uuid)
  return fail("rejected", "Explicit project, focused document and associated PCB UUIDs are required.");
for (const [g, m] of [["dmt_SelectControl", "getCurrentDocumentInfo"], ["dmt_Board", "getAllBoardsInfo"]])
  if (!has(g, m)) return fail("unsupported", `${g}.${m} is absent.`);
const guard = async () => {
  const d = await api.dmt_SelectControl.getCurrentDocumentInfo();
  return d?.uuid === args.expected_document_uuid && d.parentProjectUuid === args.expected_project_uuid ? d : null;
};
const current = await guard();
if (!current) return fail("target_mismatch", "Focused document/project differs from the explicit target.");
const boards = await api.dmt_Board.getAllBoardsInfo();
if (!Array.isArray(boards)) return fail("unsupported", "Unexpected Board tree response.");
const matches = boards.filter(b => b.pcb?.uuid === args.pcb_uuid && b.parentProjectUuid === args.expected_project_uuid);
if (matches.length !== 1) return fail("target_mismatch", "Associated Board could not be uniquely identified by PCB UUID.");
const board = matches[0];
const isPcb = current.uuid === board.pcb.uuid && current.documentType === 3;
const isSch = current.documentType === 1 && (board.schematic?.page || []).some(p => p.uuid === current.uuid);
if (!isPcb && !isSch) return fail("target_mismatch", "Focused document is outside the requested Board.");
const group = isPcb ? "pcb_ManufactureData" : "sch_ManufactureData";
if (!has(group, "getNetlistFile")) return fail("unsupported", `${group}.getNetlistFile is absent.`);
if (!await guard()) return fail("target_mismatch", "Focus changed before export.");
if (typeof args.artifact_path !== "string" || !args.artifact_path || args.artifact_path.length>512 ||
    !has("sys_FileSystem","saveFileToFileSystem"))
  return fail("rejected", "A managed local netlist path and filesystem export API are required.");
const before = await readSource();
const file = await api[group].getNetlistFile(undefined, "JLCEDA");
if (!file || typeof file.arrayBuffer !== "function" || !Number.isFinite(file.size) || file.size<=0 || file.size>80*1024*1024)
  return fail("unsupported", "Native netlist is absent, unreadable, or exceeds 80 MiB.");
const bytes = await file.arrayBuffer();
if (!(bytes instanceof ArrayBuffer) || bytes.byteLength !== file.size)
  return fail("unsupported", "Native netlist byte length did not match the EDA file.");
const digestBytes = async data => {
  if (!globalThis.crypto?.subtle) throw new Error("SHA-256 unavailable");
  const digest = await globalThis.crypto.subtle.digest("SHA-256",data);
  return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
};
const netlistSha256 = await digestBytes(bytes);
const afterNetlistSource=await readSource();
if (afterNetlistSource !== before) return fail("target_mismatch","PCB source changed while obtaining native netlist.",{
  source_before_bytes:new TextEncoder().encode(before).length,source_after_bytes:new TextEncoder().encode(afterNetlistSource).length,
  source_before_sha256:await sourceDigest(before),source_after_sha256:await sourceDigest(afterNetlistSource)
});
if (!await guard()) return fail("target_mismatch","Focus changed before netlist save.");
const saved = await api.sys_FileSystem.saveFileToFileSystem(args.artifact_path,file);
if (saved !== true) return fail("rejected","Native netlist file save was not confirmed.");
if (!await guard() || await readSource() !== before) return fail("target_mismatch","PCB source/focus changed during netlist save.");
const result = {
  ok: true, status: "observed", read_only: true, project_uuid: args.expected_project_uuid,
  document_uuid: current.uuid, pcb_uuid: board.pcb.uuid, schematic_uuid: board.schematic?.uuid,
  kind: isPcb ? "pcb" : "schematic", units: isPcb ? "mil" : "10mil",
  native_netlist: {format: "JLCEDA", sha256: netlistSha256, bytes: file.size, artifact_path: args.artifact_path},
  limitation: "Native declarations only. Schematic-to-PCB equivalence, same-document content revision consistency, and physical copper connectivity have not been verified."
};
if (isPcb) {
  if (!has("pcb_PrimitiveComponent", "getAll") || !has("pcb_Layer", "getAllLayers"))
    return fail("unsupported", "PCB component/layer reads are absent.");
  if (!await guard()) return fail("target_mismatch", "Focus changed before PCB reads.");
  const all = await api.pcb_PrimitiveComponent.getAll();
  if (!await guard()) return fail("target_mismatch", "Focus changed during component listing.");
  if (!Array.isArray(all)) return fail("unsupported", "Unexpected component response.");
  const read = (obj, name) => {
    if (typeof obj?.[name] !== "function") throw new Error("UNSUPPORTED_COMPONENT_GETTER");
    return obj[name]();
  };
  try {
    all.sort((a,b) => String(read(a,"getState_PrimitiveId")).localeCompare(String(read(b,"getState_PrimitiveId"))));
    const offset = args.component_offset ?? 0, limit = args.limit ?? 4, padOffset = args.pad_offset ?? 0;
    if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(padOffset) || padOffset < 0 ||
        !Number.isInteger(limit) || limit < 1 || limit > 8) return fail("rejected", "Invalid pagination.");
    const rows = [], pads = [];
    for (const c of all.slice(offset, offset + limit)) {
      if (!await guard()) return fail("target_mismatch", "Focus changed during component reads.");
      const id = read(c, "getState_PrimitiveId");
      if (typeof c.getAllPins !== "function") return fail("unsupported", "Component physical-pad read is absent.");
      const physical = await c.getAllPins();
      if (!await guard()) return fail("target_mismatch", "Focus changed during physical-pad reads.");
      if (!Array.isArray(physical)) return fail("unsupported", "Unexpected physical pad response.");
      rows.push({primitive_id: id, designator: read(c,"getState_Designator"),
        footprint: read(c,"getState_Footprint"), x: read(c,"getState_X"), y: read(c,"getState_Y"),
        layer: read(c,"getState_Layer"), rotation: read(c,"getState_Rotation"), physical_pad_count: physical.length});
      for (const p of physical) pads.push({component_id: id, primitive_id: read(p,"getState_PrimitiveId"),
        pad_number: read(p,"getState_PadNumber"), net: read(p,"getState_Net"),
        x: read(p,"getState_X"), y: read(p,"getState_Y"), layer: read(p,"getState_Layer")});
    }
    pads.sort((a,b) => `${a.component_id}/${a.primitive_id}`.localeCompare(`${b.component_id}/${b.primitive_id}`));
    result.components = rows;
    result.pads = pads.slice(padOffset, padOffset + 100);
    result.pagination = {component_offset: offset, total_components: all.length, pad_offset: padOffset,
      selected_physical_pads: pads.length, next_pad_offset: padOffset + 100 < pads.length ? padOffset + 100 : null,
      next_component_offset: offset + limit < all.length ? offset + limit : null};
    if (!await guard()) return fail("target_mismatch", "Focus changed before layer reads.");
    const allLayers=await api.pcb_Layer.getAllLayers();
    await guard();
    if(!Array.isArray(allLayers))return fail("unsupported","PCB layer response is not an array.");
    const copperTypes=new Set(["TOP","BOTTOM","SIGNAL","PLANE"]);
    result.layer_count_total=allLayers.length;
    result.layers=allLayers.filter(layer=>copperTypes.has(layer.type)&&layer.layerStatus!==0)
      .map(layer=>({id:layer.id,name:layer.name,type:layer.type,layer_status:layer.layerStatus,locked:layer.locked}));
  } catch (_) { return fail("unsupported", "PCB primitive response does not match the documented getter contract."); }
}
if (!await guard()) return fail("target_mismatch", "Focus changed during export; discard this observation.");
return result;
