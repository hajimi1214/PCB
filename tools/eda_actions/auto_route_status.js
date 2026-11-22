try {
  await guard();need("pcb_Document","getAutoJobStatus");need("pcb_Document","getAutoJobLog");need("pcb_Document","getRatlines");
  if(typeof a.job_id!=="string"||!a.job_id) return fail("rejected","Explicit job ID required");
  const status=await api.pcb_Document.getAutoJobStatus(a.job_id);await guard();
  if(!status||status.jobId!==a.job_id||!(["queued","running","completed","canceled","failed"].includes(status.state))||
      !Number.isInteger(status.progress)||status.progress<0||status.progress>100)
    return fail("unavailable","Router status was absent or malformed");
  const logs=await api.pcb_Document.getAutoJobLog(a.job_id);await guard();
  if(!logs||!Array.isArray(logs.logs))return fail("unavailable","Router log snapshot was malformed");
  const progress=logs.progress&&typeof logs.progress==="object"?logs.progress:null;
  let ratlines=null;
  if(["completed","canceled","failed"].includes(status.state)) {
    let cursor, pages=0, total=0, hasMore;
    do {
      const page=await api.pcb_Document.getRatlines({limit:200,...(cursor?{cursor}:{})});await guard();
      if(!page||!Array.isArray(page.items)||typeof page.hasMore!=="boolean")return fail("unavailable","Ratline response malformed");
      total+=page.items.length;pages++;cursor=page.nextCursor;hasMore=page.hasMore;
      if(pages>500||total>100000)return fail("unsupported","Unrouted result exceeds local limit");
      if(hasMore&&(!cursor||typeof cursor!=="string"))return fail("unavailable","Ratline cursor missing");
    } while(hasMore);
    ratlines={total,pages};
  }
  const current=await source();
  return {ok:true,status:"observed",job_id:a.job_id,state:status.state,progress_percent:status.progress,
    partial:status.partial??null,error:status.error??null,router_progress:progress&&Number.isFinite(progress.routabitity)?progress.routabitity:null,
    log_entries:logs.logs.length,source_sha256:await hash(current),source_changed:await hash(current)!==a.expected_source_sha256,
    unrouted_ratlines:ratlines,requires_drc:true,
    limitation:"Router completion does not imply every selected net is connected, correct impedance, DRC, SI/PI, DFM, or functional acceptance."};
} catch(e) {return fail("rejected",String(e.message));}
