try {
  await guard();need("pcb_Document","cancelAutoJob");need("pcb_Document","getAutoJobStatus");
  if(typeof a.job_id!=="string"||!a.job_id)return fail("rejected","Explicit job ID required");
  const before=await api.pcb_Document.getAutoJobStatus(a.job_id);await guard();
  if(!before||before.jobId!==a.job_id||!["queued","running"].includes(before.state))
    return fail("rejected","Only an active job in this target can be canceled");
  const accepted=await api.pcb_Document.cancelAutoJob(a.job_id);await guard();
  return {ok:true,status:"observed",job_id:a.job_id,cancel_requested:accepted===true,
    limitation:"Cancellation request is not a terminal state; poll auto_route_status before proceeding."};
} catch(e) {return fail("rejected",String(e.message));}
