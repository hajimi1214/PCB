// A reviewed plan applies at most 20 placements / net lines / through vias / one board outline.
let groupId = null, committed = false, baseline = null, stage="preflight";
const close = (x,y) => Number.isFinite(x) && Number.isFinite(y) && Math.abs(x-y) <= 0.00001;
const polygonPoints = value => {
  let source;
  try {
    source=Array.isArray(value) ? value : Number.isInteger(value?.length) ?
      Array.from({length:value.length},(_,index)=>value[index]) : null;
  } catch (_) { return null; }
  if (!Array.isArray(source) || source.length<7 || source[2]!=="L" || (source.length-3)%2!==0)
    return null;
  const points=[[source[0],source[1]]];
  for(let index=3;index<source.length;index+=2)points.push([source[index],source[index+1]]);
  if(points.some(point=>!point.every(Number.isFinite)))return null;
  if(close(points[0][0],points.at(-1)[0])&&close(points[0][1],points.at(-1)[1]))points.pop();
  return points;
};
const sameClosedPolygon = (expectedSource,actualSource) => {
  const expected=polygonPoints(expectedSource),actual=polygonPoints(actualSource);
  if(!expected||!actual||expected.length!==actual.length)return false;
  for(let offset=0;offset<actual.length;offset++){
    for(const direction of [1,-1]){
      if(expected.every((point,index)=>{
        const other=actual[(offset+direction*index+actual.length)%actual.length];
        return close(point[0],other[0])&&close(point[1],other[1]);
      }))return true;
    }
  }
  return false;
};
const errorDetail = error => {
  const redact = (value, depth=0) => {
    if (depth > 2 || value == null) return value ?? null;
    if (typeof value === "string") return value.slice(0,240);
    if (typeof value === "number" || typeof value === "boolean") return value;
    if (Array.isArray(value)) return value.slice(0,8).map(item=>redact(item,depth+1));
    if (typeof value !== "object") return String(value).slice(0,240);
    const result={};
    for (const key of Object.keys(value).slice(0,12)) {
      if (/token|password|secret|authorization|cookie|credential|stack/i.test(key)) continue;
      try { result[key]=redact(value[key],depth+1); } catch (_) { result[key]="[unavailable]"; }
    }
    return result;
  };
  const fields = {};
  for (const key of ["name","message","code","status","reason","statusCode"]) {
    let value;
    try { value=error?.[key]; } catch (_) { continue; }
    if (value !== undefined) fields[key] = redact(value);
  }
  if (Object.keys(fields).length) return JSON.stringify(fields).slice(0,500);
  try { return String(error).slice(0,240); } catch (_) { return "Unknown EDA error"; }
};
try {
  if (!Array.isArray(a.operations) || a.operations.length < 1 || a.operations.length > 20)
    return fail("rejected","Batch must contain 1..20 operations");
  for (const m of ["beginCommandGroup","commitCommandGroup","rollbackCommandGroup"]) need("pcb_Document",m);
  baseline = await capture();
  if (baseline.source_sha256 !== a.expected_source_sha256)
    return fail("rejected","PCB changed since preview; prepare a new plan");
  const beforeComponents = new Map(baseline.components.map(c => [c.id,c]));
  const finite = v => typeof v === "number" && Number.isFinite(v) && Math.abs(v) <= 1000000;
  const signal = id => baseline.layers.some(l => l.id === id && l.type === "SIGNAL" && [1,2].includes(l.layerStatus) && l.locked === false);
  const net = n => typeof n === "string" && n.length > 0 && baseline.nets.includes(n);
  const moved = new Set();
  const resolvedFootprints = new Map();
  let outlineCount = 0;
  for (const op of a.operations) {
    if (op.kind === "move" || op.kind === "place") {
      const c = beforeComponents.get(op.component_id);
      if (!c || c.locked !== false || moved.has(c.id) || !finite(op.x) || !finite(op.y))
        throw new Error("Invalid, duplicate or locked component placement");
      if (!baseline.layers.some(l => l.id === c.layer &&
          (["TOP","BOTTOM"].includes(l.type) || ([1,2].includes(l.id) && l.type === "SIGNAL")) &&
          l.layerStatus !== 0 && l.locked === false))
        throw new Error("Placement requires an enabled, unlocked component side");
      if (op.kind === "place" && (!finite(op.rotation) || op.rotation < 0 || op.rotation >= 360))
        throw new Error("Placement rotation is outside 0..359.999 degrees");
      moved.add(c.id); need("pcb_PrimitiveComponent","modify"); need("pcb_PrimitiveComponent","get");
      if (op.kind === "place") need("sys_Math","rotate");
    } else if (op.kind === "line") {
      if (!net(op.net) || !signal(op.layer) || ![op.x1,op.y1,op.x2,op.y2,op.width].every(finite) || op.width <= 0 || (op.x1 === op.x2 && op.y1 === op.y2))
        throw new Error("Invalid net/layer/line geometry");
      need("pcb_PrimitiveLine","create"); need("pcb_PrimitiveLine","get");
    } else if (op.kind === "via") {
      if (!net(op.net) || ![op.x,op.y,op.hole,op.diameter].every(finite) || op.hole <= 0 || op.diameter <= op.hole)
        throw new Error("Invalid through via");
      need("pcb_PrimitiveVia","create"); need("pcb_PrimitiveVia","get");
    } else if (op.kind === "outline" || op.kind === "replace_outline") {
      const replaces=op.kind==="replace_outline";
      outlineCount++;
      if (outlineCount > 1 || baseline.outline_primitive_ids === null)
        throw new Error("Only one exact board outline operation is allowed per batch");
      if (replaces ? baseline.outline_primitive_ids.length!==1 ||
          !baseline.outline_primitive_ids.includes(op.primitive_id) :
          baseline.outline_primitive_ids.length!==0)
        throw new Error("Board outline create/replace identity differs from the verified baseline");
      if(replaces&&!/^[A-Za-z0-9_-]{1,64}$/.test(op.primitive_id))
        throw new Error("Board outline replacement requires its exact primitive identity");
      if (!baseline.outline_layer || baseline.outline_layer.id !== 11 || baseline.outline_layer.locked !== false || baseline.outline_layer.layerStatus === 0)
        throw new Error("Board outline layer 11 must be enabled and unlocked");
      if (!Array.isArray(op.points) || op.points.length < 5 || op.points.length > 64 ||
          op.points.some(point => !Array.isArray(point) || point.length !== 2 || !point.every(finite)) ||
          !finite(op.width) || op.width < 0.1 || op.width > 10)
        throw new Error("Invalid closed board outline polygon");
      if (op.points[0][0] !== op.points.at(-1)[0] || op.points[0][1] !== op.points.at(-1)[1])
        throw new Error("Board outline must explicitly return to its first point");
      const cross=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
      const on=(p,q,r)=>Math.min(p[0],q[0])-1e-8<=r[0]&&r[0]<=Math.max(p[0],q[0])+1e-8&&
        Math.min(p[1],q[1])-1e-8<=r[1]&&r[1]<=Math.max(p[1],q[1])+1e-8;
      let area=0;
      for(let i=0;i<op.points.length-1;i++){
        const p=op.points[i],q=op.points[i+1];
        if(p[0]===q[0]&&p[1]===q[1])throw new Error("Board outline has a zero-length edge");
        area+=p[0]*q[1]-q[0]*p[1];
        for(let j=i+1;j<op.points.length-1;j++){
          if(j===i+1||(i===0&&j===op.points.length-2))continue;
          const r=op.points[j],s=op.points[j+1],o1=cross(p,q,r),o2=cross(p,q,s),o3=cross(r,s,p),o4=cross(r,s,q);
          if(o1*o2<0&&o3*o4<0||Math.abs(o1)<1e-8&&on(p,q,r)||Math.abs(o2)<1e-8&&on(p,q,s)||
             Math.abs(o3)<1e-8&&on(r,s,p)||Math.abs(o4)<1e-8&&on(r,s,q))
            throw new Error("Board outline self-intersects");
        }
      }
      if(Math.abs(area)<1e-6||new Set(op.points.slice(0,-1).map(point=>point.join(","))).size<4)
        throw new Error("Board outline requires a nonzero area and at least four distinct vertices");
      need("pcb_MathPolygon","createPolygon"); need("pcb_PrimitivePolyline",replaces?"modify":"create");
      need("pcb_PrimitivePolyline","get");need("pcb_PrimitivePolyline","getAll");
    } else if(op.kind === "footprint") {
      if(!/^[0-9a-f]{16,64}$/i.test(op.library_uuid)||!/^[0-9a-f]{8,64}$/i.test(op.footprint_uuid)||
          !/^[A-Za-z][A-Za-z0-9_]*$/.test(op.designator)||!Array.isArray(op.expected_pad_numbers)||
          op.expected_pad_numbers.length>300||
          op.expected_pad_numbers.some(number=>typeof number!=="string"||!number)||op.visual_only!==true||
          ![op.x,op.y,op.rotation].every(finite)||op.rotation<0||op.rotation>=360)
        throw new Error("Invalid footprint-only visual placement identity or pose");
      const top=baseline.layers.find(layer=>layer.id===1);
      if(!top||top.layerStatus===0||top.locked!==false)throw new Error("Footprint-only visual prototype requires an enabled unlocked top layer");
      if([...beforeComponents.values()].some(component=>component.designator===op.designator)||
          a.operations.some(other=>other!==op&&other.kind==="footprint"&&other.designator===op.designator))
        throw new Error("Footprint visual prototype designator must be unique");
      need("lib_Footprint","get");need("pcb_PrimitiveComponent","create");need("pcb_PrimitiveComponent","modify");
      need("pcb_PrimitiveComponent","get");
      stage="resolve-footprint-" + op.designator;
      let footprint;
      try {
        footprint=await api.lib_Footprint.get(op.footprint_uuid,op.library_uuid);
      } catch(error) {
        throw new Error("Footprint " + op.designator + " lookup failed for " + op.footprint_uuid +
          " in library " + op.library_uuid + ": " + errorDetail(error));
      }
      await guard();
      stage="verify-footprint-library-result-" + op.designator;
      if(!footprint||footprint.uuid!==op.footprint_uuid||typeof footprint.libraryUuid!=="string"||!footprint.libraryUuid)
        throw new Error("Footprint " + op.designator + " did not resolve by exact footprint UUID and library");
      resolvedFootprints.set(op.designator,footprint);
    } else throw new Error("Unsupported operation");
  }
  // Recheck after all asynchronous preparation, before opening a write group.
  if (await hash(await source()) !== a.expected_source_sha256) throw new Error("Baseline drift");
  const group = await api.pcb_Document.beginCommandGroup(`PCB ${a.plan_id}`);
  if (!group?.groupId) throw new Error("Could not open a command group");
  groupId = group.groupId;
  const created = [];
  for (const op of a.operations) {
    stage=`write-${op.kind}`;
    await guard();
    if (op.kind === "move" || op.kind === "place") {
      const props=op.kind === "place" ? {x:op.x,y:op.y,rotation:op.rotation} : {x:op.x,y:op.y};
      if (!await api.pcb_PrimitiveComponent.modify(op.component_id,props)) throw new Error("Placement returned no object");
    } else if (op.kind === "line") {
      const obj = await api.pcb_PrimitiveLine.create(op.net,op.layer,op.x1,op.y1,op.x2,op.y2,op.width,false);
      created.push({op,id:state(obj,"PrimitiveId")});
    } else if (op.kind === "via") {
      const obj = await api.pcb_PrimitiveVia.create(op.net,op.x,op.y,op.hole,op.diameter,0,null,null,false);
      created.push({op,id:state(obj,"PrimitiveId")});
    } else if(op.kind === "footprint") {
      const footprint=resolvedFootprints.get(op.designator);
      stage="verify-footprint-library-result-" + op.designator;
      if(!footprint||footprint.uuid!==op.footprint_uuid||typeof footprint.libraryUuid!=="string"||!footprint.libraryUuid)
        throw new Error(`Footprint ${op.designator} did not resolve by exact footprint UUID`);
      stage="create-footprint-" + op.designator;
      const obj=await api.pcb_PrimitiveComponent.create(footprint,1,op.x,op.y,op.rotation,false);
      if(!obj)throw new Error(`EDA did not create footprint ${op.designator}`);
      const id=state(obj,"PrimitiveId");
      if(!id)throw new Error(`EDA did not return a component identity for ${op.designator}`);
      stage=`set-designator-${op.designator}`;
      if(!await api.pcb_PrimitiveComponent.modify(id,{designator:op.designator}))
        throw new Error(`EDA did not set visual prototype designator ${op.designator}`);
      created.push({op,id,resolved_library_uuid:footprint.libraryUuid});
    } else if(op.kind==="outline"||op.kind==="replace_outline") {
      const source=[op.points[0][0],op.points[0][1],"L",...op.points.slice(1).flat()];
      const polygon=api.pcb_MathPolygon.createPolygon(source);
      if(!polygon)throw new Error("EDA rejected the board outline polygon");
      let obj;
      if(op.kind==="replace_outline"){
        obj=await api.pcb_PrimitivePolyline.modify(op.primitive_id,{polygon,lineWidth:op.width});
        if(!obj)throw new Error("EDA did not modify the exact registered board outline");
        created.push({op,id:op.primitive_id,polygon_source:source,replaced:true});
      }else{
        obj=await api.pcb_PrimitivePolyline.create("",11,polygon,op.width,false);
        created.push({op,id:state(obj,"PrimitiveId"),polygon_source:source,replaced:false});
      }
      if(!state(obj,"PrimitiveId"))throw new Error("EDA did not return a board outline identity");
    }
    await guard();
  }
  stage="readback";
  const after = await capture();
  // Re-read all physical pads after the requested placement transforms.
  const visualFootprints=created.filter(item=>item.op.kind==="footprint");
  if (after.components.length !== baseline.components.length+visualFootprints.length) throw new Error("Component count changed");
  for (const c of after.components) {
    const b = beforeComponents.get(c.id), op = a.operations.find(o => ["move","place"].includes(o.kind) && o.component_id === c.id);
    if(!b){
      const visual=visualFootprints.find(item=>item.id===c.id)?.op;
      const createdFootprint=visualFootprints.find(item=>item.id===c.id);
      if(!visual||!createdFootprint||c.designator!==visual.designator||!close(c.x,visual.x)||!close(c.y,visual.y)||!close(c.rotation,visual.rotation)||
          c.layer!==1||c.footprint?.uuid!==visual.footprint_uuid||c.footprint?.libraryUuid!==createdFootprint.resolved_library_uuid||
          JSON.stringify(c.pads.map(pad=>pad.number).sort())!==JSON.stringify([...visual.expected_pad_numbers].sort())||
          c.device!=null)
        throw new Error("Visual-only footprint device/pose/physical-pad readback mismatch");
      continue;
    }
    const targetX=op?.x ?? b.x,targetY=op?.y ?? b.y,targetRotation=op?.kind === "place" ? op.rotation : b.rotation;
    const rotationDelta=targetRotation-b.rotation;
    if (!close(c.x,targetX) || !close(c.y,targetY) || c.layer !== b.layer || !close(c.rotation,targetRotation) ||
        c.locked !== b.locked || c.designator !== b.designator || c.pads.length !== b.pads.length)
      throw new Error("Component readback mismatch");
    for (const p of c.pads) {
      const old = b.pads.find(q => q.id === p.id);
      if (!old || p.net !== old.net || p.number !== old.number || p.layer !== old.layer)
        throw new Error("Physical pad readback mismatch");
      const rotated=rotationDelta ? api.sys_Math.rotate([{x:old.x,y:old.y}],rotationDelta,b.x,b.y)[0] : {x:old.x,y:old.y};
      const expectedX=rotated.x+targetX-b.x,expectedY=rotated.y+targetY-b.y;
      if (!close(p.x,expectedX) || !close(p.y,expectedY)) throw new Error("Physical pad transform mismatch");
    }
  }
  if (JSON.stringify([...after.nets].sort()) !== JSON.stringify([...baseline.nets].sort()) || JSON.stringify(after.layers) !== JSON.stringify(baseline.layers))
    throw new Error("Nets or layers changed");
  const outlineOperation=a.operations.find(operation=>operation.kind==="outline"||operation.kind==="replace_outline");
  if(outlineOperation){
    if(after.outline_primitive_ids===null)throw new Error("Board outline inventory is unavailable after the edit");
    if(outlineOperation.kind==="outline"){
      const createdOutline=created.find(item=>item.op===outlineOperation);
      if(after.outline_primitive_ids.length!==1||!createdOutline||
          !after.outline_primitive_ids.includes(createdOutline.id)||baseline.outline_primitive_ids.length!==0)
        throw new Error("New board outline readback identity differs");
    }else if(after.outline_primitive_ids.length!==baseline.outline_primitive_ids.length||
        JSON.stringify(after.outline_primitive_ids)!==JSON.stringify(baseline.outline_primitive_ids)){
      throw new Error("Replaced board outline changed its primitive identity or count");
    }
  }
  for (const {op,id,polygon_source,resolved_library_uuid} of created) {
    await guard();
    const group=op.kind === "line" ? "pcb_PrimitiveLine" : op.kind === "via" ? "pcb_PrimitiveVia" : ["outline","replace_outline"].includes(op.kind) ? "pcb_PrimitivePolyline" : "pcb_PrimitiveComponent";
    const obj = await api[group].get(id);
    await guard();
    if (op.kind === "outline" || op.kind==="replace_outline") {
      const polygon=state(obj,"Polygon");
      const actualPolygon=polygon?.getSource?.()??null;
      if (state(obj,"Layer")!==11 || !close(state(obj,"LineWidth"),op.width) ||
          !sameClosedPolygon(polygon_source,actualPolygon))
        throw new Error("Board outline readback mismatch " + JSON.stringify({
          layer:state(obj,"Layer"),line_width:state(obj,"LineWidth"),
          expected_line_width:op.width,expected_length:polygon_source.length,
          actual_type:typeof actualPolygon,actual_length:Array.isArray(actualPolygon)?actualPolygon.length:null,
          actual_start:Array.isArray(actualPolygon)?actualPolygon.slice(0,6):actualPolygon,
          actual_end:Array.isArray(actualPolygon)?actualPolygon.slice(-6):null
        }));
    } else if(op.kind==="footprint"){
      const actual=state(obj,"Footprint");
      if(state(obj,"Designator")!==op.designator||actual?.uuid!==op.footprint_uuid||actual?.libraryUuid!==resolved_library_uuid)
        throw new Error("Visual-only footprint entity readback mismatch");
    } else if (state(obj,"Net") !== op.net) throw new Error("Created primitive net mismatch");
    if (op.kind === "line") {
      if (state(obj,"Layer") !== op.layer || !close(state(obj,"StartX"),op.x1) || !close(state(obj,"StartY"),op.y1) ||
          !close(state(obj,"EndX"),op.x2) || !close(state(obj,"EndY"),op.y2) || !close(state(obj,"LineWidth"),op.width))
        throw new Error("Line readback differs (automatic splitting requires a new plan)");
    } else if (op.kind === "via" && (!close(state(obj,"X"),op.x) || !close(state(obj,"Y"),op.y) || !close(state(obj,"HoleDiameter"),op.hole) ||
        !close(state(obj,"Diameter"),op.diameter) || state(obj,"ViaType") !== 0)) throw new Error("Via readback mismatch");
  }
  stage="commit";
  await guard();
  if (!await api.pcb_Document.commitCommandGroup(groupId)) throw new Error("Command group commit not confirmed");
  committed = true;
  const finalSource = await source();
  return {ok:true,status:"completed",group_id:groupId,operation_count:a.operations.length,created_ids:created.map(x=>x.id),
    source:finalSource,source_sha256:await hash(finalSource),saved_to_native_project:false,drc_required:true,
    visual_only_component_count:visualFootprints.length,visual_only_no_device_or_net_binding:visualFootprints.length>0,
    limitation:"Footprint-only visual prototypes do not inherit schematic device or net binding. No collision/keepout proof, DRC, routing completeness, SI/PI, DFM or functional pass; do not fabricate until engineering verification."};
} catch (e) {
  let rollback = "not_needed";
  if (groupId && !committed) {
    try {
      await guard();
      if (!await api.pcb_Document.rollbackCommandGroup(groupId)) throw new Error("Rollback false");
      rollback = await hash(await source()) === baseline?.source_sha256 ? "source_verified" : "unverified";
    } catch (_) { rollback = "unverified"; }
  } else if (committed) rollback = "not_attempted_after_commit";
  const errorMessage=errorDetail(e);
  return fail("rejected",errorMessage,{stage,error_type:e?.name??typeof e,rollback,
    recovery_required:rollback !== "not_needed" && rollback !== "source_verified",committed});
}
