// Shared fixed source for drawing_state / apply_drawing_batch, never caller code.
const a = __CLI__.args;
const api = typeof eda === "undefined" ? null : eda;
const fail = (status, reason, extra = {}) => ({ok: false, status, reason, ...extra});
const need = (g, m) => { if (typeof api?.[g]?.[m] !== "function") throw new Error(`Missing ${g}.${m}`); };
const state = (o, key) => {
  const fn = `getState_${key}`;
  if (typeof o?.[fn] !== "function") throw new Error(`Missing ${fn}`);
  return o[fn]();
};
const guard = async () => {
  need("dmt_SelectControl", "getCurrentDocumentInfo");
  const d = await api.dmt_SelectControl.getCurrentDocumentInfo();
  if (d?.uuid !== a.pcb_uuid || d.documentType !== 3 || d.parentProjectUuid !== a.expected_project_uuid)
    throw new Error("Target changed");
};
const hash = async text => {
  if (!globalThis.crypto?.subtle) throw new Error("SHA-256 unavailable");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
};
const stableJson = value => {
  if (Array.isArray(value)) return value.map(stableJson);
  if (value && typeof value === "object")
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, stableJson(value[key])]));
  return value;
};
const canonicalSource = text => text.split("\n").map(line => {
  const carriageReturn = line.endsWith("\r") ? "\r" : "";
  const record = carriageReturn ? line.slice(0,-1) : line;
  if (!record) return carriageReturn;
  const split = record.indexOf("||");
  if (split < 0) return `${record}${carriageReturn}`;
  const hasTerminator = record.endsWith("|");
  try {
    const shell = JSON.parse(record.slice(0,split));
    const body = JSON.parse(record.slice(split+2,hasTerminator ? -1 : undefined));
    return `${JSON.stringify(stableJson(shell))}||${JSON.stringify(stableJson(body))}${hasTerminator ? "|" : ""}${carriageReturn}`;
  } catch (_) {
    return `${record}${carriageReturn}`;
  }
}).join("\n");
const semanticSourceHash = async text => hash(canonicalSource(text));
const source = async () => {
  await guard(); need("sys_FileManager", "getDocumentSource");
  const text = await api.sys_FileManager.getDocumentSource();
  await guard();
  if (typeof text !== "string" || !text.length || new TextEncoder().encode(text).length > 8*1024*1024)
    throw new Error("PCB source absent or exceeds 8 MiB local limit");
  const newline=text.indexOf("\n"),lineEnd=newline<0?text.length:newline;
  const rawHead=text.slice(0,lineEnd).replace(/\r$/,"");
  const tail=newline<0?"":text.slice(newline);
  const split=rawHead.indexOf("||");
  if(split<0)throw new Error("PCB source DOCHEAD delimiter is missing");
  let shell,body;
  try{shell=JSON.parse(rawHead.slice(0,split));body=JSON.parse(rawHead.slice(split+2).replace(/\|$/,""));}
  catch(_){throw new Error("PCB source DOCHEAD is malformed");}
  if(shell?.type!=="DOCHEAD"||body?.uuid!==a.pcb_uuid)throw new Error("PCB source DOCHEAD does not match the target UUID");
  // EDA may refresh DOCHEAD export metadata while the design records remain unchanged.
  delete body.updateTime;
  delete body.client;
  delete body.version;
  return `${JSON.stringify(shell)}||${JSON.stringify(body)}|${tail}`;
};
const component = async obj => {
  const id = state(obj, "PrimitiveId");
  if (typeof obj.getAllPins !== "function") throw new Error("Physical pads unavailable");
  if(typeof obj.getState_Component!=="function"||typeof obj.getState_Footprint!=="function")
    throw new Error("Device/footprint associations unavailable");
  await guard(); const physical = await obj.getAllPins(); await guard();
  if (!Array.isArray(physical)) throw new Error("Invalid pads");
  const device=obj.getState_Component(),footprint=obj.getState_Footprint();
  return {id, designator: state(obj,"Designator") ?? null, x:state(obj,"X"), y:state(obj,"Y"),
    rotation:state(obj,"Rotation"), layer:state(obj,"Layer"), locked:state(obj,"PrimitiveLock"),device,footprint,
    pads: physical.map(p => ({id:state(p,"PrimitiveId"), number:state(p,"PadNumber"),
      net:state(p,"Net") ?? null, x:state(p,"X"), y:state(p,"Y"), layer:state(p,"Layer")}))};
};
const capture = async () => {
  const before = await source();
  need("pcb_PrimitiveComponent","getAll");need("pcb_Layer","getAllLayers");need("pcb_Net","getAllNetsName");
  const objects = await api.pcb_PrimitiveComponent.getAll(); await guard();
  if (!Array.isArray(objects) || objects.length > 1000) throw new Error("Component count unsupported");
  const components = [];
  for (const obj of objects) components.push(await component(obj));
  const layers = await api.pcb_Layer.getAllLayers(); await guard();
  const nets = await api.pcb_Net.getAllNetsName(); await guard();
  if (!Array.isArray(layers) || !Array.isArray(nets)) throw new Error("Invalid layers/nets");
  let outlinePrimitiveIds = null;
  let visualGeometry = null;
  if (typeof api.pcb_PrimitivePolyline?.getAll === "function") {
    const polylines = await api.pcb_PrimitivePolyline.getAll(); await guard();
    if (!Array.isArray(polylines) || polylines.length > 50000) throw new Error("Polyline response is invalid or too large");
    outlinePrimitiveIds = polylines.filter(polyline=>state(polyline,"Layer")===11)
      .map(outline => state(outline,"PrimitiveId")).sort();
    if(outlinePrimitiveIds.length>128)throw new Error("Board-outline response exceeds the local limit");
  }
  const readPrimitiveRows = async(group,method,label,max) => {
    if(typeof api?.[group]?.[method]!=="function")return null;
    const rows=await api[group][method]();await guard();
    if(!Array.isArray(rows)||rows.length>max)throw new Error(`${label} inventory is invalid or exceeds the local limit`);
    return rows;
  };
  const tracks=await readPrimitiveRows("pcb_PrimitiveLine","getAll","Track",100000);
  const vias=await readPrimitiveRows("pcb_PrimitiveVia","getAll","Via",20000);
  const pours=await readPrimitiveRows("pcb_PrimitivePour","getAll","Copper-pour",10000);
  if(tracks!==null||vias!==null||pours!==null)
    visualGeometry={track_count:tracks?.length??null,via_count:vias?.length??null,pour_outline_count:pours?.length??null,
      board_outline_ids:outlinePrimitiveIds};
  const after = await source();
  if (before !== after) throw new Error("PCB changed while taking snapshot");
  return {source:before, source_sha256:await hash(before), semantic_source_sha256:await semanticSourceHash(before),
    components, layers, nets, outline_layer:layers.find(layer=>layer.id===11) ?? null,
    outline_primitive_ids:outlinePrimitiveIds,visual_geometry:visualGeometry,units:"mil"};
};
