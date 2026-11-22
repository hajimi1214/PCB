// Start the native router only for a persisted preview in the managed copy.
try {
  if (!Array.isArray(a.routing_nets) || !a.routing_nets.length || a.routing_nets.length>64 ||
      !Array.isArray(a.layers) || !a.layers.length || a.layers.length>8)
    return fail("rejected","Select 1..64 existing nets and 1..8 enabled SIGNAL layers");
  const names=new Set(a.routing_nets),layers=new Set(a.layers);
  if(names.size!==a.routing_nets.length||layers.size!==a.layers.length)
    return fail("rejected","Router preview contains duplicate nets or layers");
  const baseline=await capture();
  if(baseline.source_sha256!==a.expected_source_sha256) return fail("rejected","PCB source changed since routing preview");
  if(!a.routing_nets.every(name=>baseline.nets.includes(name)))return fail("rejected","Router preview contains an unknown net");
  for(const layer of layers) {
    const info=baseline.layers.find(item=>item.id===layer);
    if(!info||info.type!=="SIGNAL"||![1,2].includes(info.layerStatus)||info.locked!==false)
      return fail("rejected","Router layer is disabled, locked, non-SIGNAL or absent");
  }
  need("pcb_Document","startAutoRouting");
  const handle=await api.pcb_Document.startAutoRouting({RoutingNets:a.routing_nets,layers:a.layers,
    ignoreNets:[],cornerStyle:0,existingPrimitiveMode:"keep",optimization:1});
  await guard();
  if(!handle||typeof handle.jobId!=="string"||!handle.jobId)return fail("unsupported","Native router did not return a job ID; inspect the copy before retrying");
  return {ok:true,status:"started",job_id:handle.jobId,pcb_uuid:a.pcb_uuid,project_uuid:a.expected_project_uuid,
    source_sha256:a.expected_source_sha256,selected_nets:a.routing_nets,layers:a.layers,
    existing_primitive_mode:"keep",optimization:"completion",corner_style:"45deg"};
} catch(e) {return fail("rejected",String(e.message));}
