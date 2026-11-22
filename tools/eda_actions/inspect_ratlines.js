// Read all unrouted connections on one exact focused PCB and summarize by net.
try{
  const a=__CLI__.args,api=typeof eda==="undefined"?null:eda;
  const fail=(status,reason)=>({ok:false,status,reason});
  if(!api?.dmt_SelectControl?.getCurrentDocumentInfo||!api?.pcb_Document?.getRatlines)
    return fail("unsupported","Document identity or ratline API is absent");
  const guard=async()=>{const d=await api.dmt_SelectControl.getCurrentDocumentInfo();return d?.uuid===a.expected_document_uuid&&d.documentType===3&&d.parentProjectUuid===a.expected_project_uuid;};
  if(!a.expected_document_uuid||!a.expected_project_uuid||a.expected_document_uuid!==a.pcb_uuid||!await guard())
    return fail("target_mismatch","Ratline inspection requires the exact focused PCB/project UUIDs");
  const nets=new Map();let cursor,pages=0,total=0;
  do{
    const page=await api.pcb_Document.getRatlines({limit:200,...(cursor?{cursor}:{})});
    if(!await guard())return fail("target_mismatch","PCB focus changed during ratline paging");
    if(!page||!Array.isArray(page.items)||typeof page.hasMore!=="boolean")return fail("unsupported","Ratline page schema is invalid");
    for(const r of page.items){
      if(typeof r.net!=="string"||!r.net||!Number.isFinite(r.length))return fail("unsupported","Ratline entry is invalid");
      const item=nets.get(r.net)??{net:r.net,count:0,total_length:0,samples:[]};
      item.count++;item.total_length+=r.length;
      if(item.samples.length<3)item.samples.push({primitive_id:r.primitiveId,start_id:r.startId,end_id:r.endId,length:r.length});
      nets.set(r.net,item);total++;
    }
    pages++;cursor=page.nextCursor;
    if(total>100000||pages>500)return fail("unsupported","Ratline result exceeds local paging limits");
    if(page.hasMore&&(!cursor||typeof cursor!=="string"))return fail("unsupported","Ratline cursor is missing");
  }while(cursor);
  if(!await guard())return fail("target_mismatch","PCB focus changed after ratline paging");
  return {ok:true,status:"observed",pcb_uuid:a.pcb_uuid,project_uuid:a.expected_project_uuid,
    unrouted_total:total,routing_complete:total===0,routing_basis:"Native JLCEDA Pro ratline connectivity",
    page_count:pages,nets:[...nets.values()].sort((x,y)=>x.count-y.count||x.net.localeCompare(y.net)).slice(0,256),
    limitation:"This is the native ratsnest only. A zero count does not establish electrical equivalence, DRC, impedance or manufacturing acceptance."};
}catch(e){return {ok:false,status:"unavailable",reason:String(e.message)};}
