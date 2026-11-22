// Privacy-preserving check of repeated native source reads for one focused document.
try {
  const args=__CLI__.args;
  const api=typeof eda==="undefined"?null:eda;
  if(typeof api?.dmt_SelectControl?.getCurrentDocumentInfo!=="function"||typeof api?.sys_FileManager?.getDocumentSource!=="function")
    return {ok:false,status:"unsupported",reason:"Document identity/source methods are absent."};
  const current=await api.dmt_SelectControl.getCurrentDocumentInfo();
  if(current?.uuid!==args.expected_document_uuid||current.parentProjectUuid!==args.expected_project_uuid)
    return {ok:false,status:"target_mismatch",reason:"Focused target differs from explicit document/project."};
  const first=await api.sys_FileManager.getDocumentSource();
  const second=await api.sys_FileManager.getDocumentSource();
  const last=await api.dmt_SelectControl.getCurrentDocumentInfo();
  if(last?.uuid!==current.uuid||last.parentProjectUuid!==current.parentProjectUuid)
    return {ok:false,status:"target_mismatch",reason:"Focus changed during source stability probe."};
  if(typeof first!=="string"||typeof second!=="string")
    return {ok:false,status:"unsupported",reason:"Native document source was absent."};
  const hash=async text=>{
    const bytes=new TextEncoder().encode(text);
    const digest=await globalThis.crypto.subtle.digest("SHA-256",bytes);
    return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
  };
  const rows=text=>text.split(/\r?\n/).filter(Boolean).map(line=>{
    const split=line.indexOf("||");
    if(split<0)return {type:"unknown",id:"unknown"};
    let shell;
    try{shell=JSON.parse(line.slice(0,split));}catch(_){return {type:"unknown",id:"unknown"};}
    return {type:shell?.type??"unknown",id:shell?.id??"unknown",line};
  });
  const before=rows(first),after=rows(second),limit=Math.max(before.length,after.length),counts={},contentCounts={};
  const firstLine=text=>text.split(/\r?\n/,1)[0]??"";
  const body=text=>text.replace(/^[^\r\n]*(?:\r?\n)/,"");
  const headerKeys=text=>Array.from(new Set(Array.from(firstLine(text).matchAll(/"([A-Za-z_$][A-Za-z0-9_$]*)"\s*:/g),m=>m[1]))).slice(0,40);
  let changed=0,changedContent=0,firstDifferent=null,firstContentDifferent=null;
  for(let i=0;i<limit;i++){
    if(before[i]?.type!==after[i]?.type||before[i]?.id!==after[i]?.id){
      changed++;
      if(firstDifferent===null)firstDifferent={record_index:i,before_type:before[i]?.type??null,after_type:after[i]?.type??null};
      const type=after[i]?.type??before[i]?.type??"unknown";counts[type]=(counts[type]??0)+1;
    }
    if(before[i]?.line!==after[i]?.line){
      changedContent++;
      const type=after[i]?.type??before[i]?.type??"unknown";contentCounts[type]=(contentCounts[type]??0)+1;
      if(firstContentDifferent===null)firstContentDifferent={record_index:i,type};
    }
  }
  let sourceShape={first_json:false,second_json:false,first_root:null,second_root:null,first_keys:[],second_keys:[],changed_json_paths:[]};
  try {
    const left=JSON.parse(first),right=JSON.parse(second);
    const kind=v=>Array.isArray(v)?"array":v===null?"null":typeof v;
    sourceShape.first_json=true;sourceShape.second_json=true;sourceShape.first_root=kind(left);sourceShape.second_root=kind(right);
    sourceShape.first_keys=left&&typeof left==="object"&&!Array.isArray(left)?Object.keys(left).slice(0,80):[];
    sourceShape.second_keys=right&&typeof right==="object"&&!Array.isArray(right)?Object.keys(right).slice(0,80):[];
    const pending=[["$",left,right]],seen=0;
    while(pending.length&&sourceShape.changed_json_paths.length<20&&seen<50000){
      const [path,x,y]=pending.pop();
      if(Object.is(x,y))continue;
      if(x&&y&&typeof x==="object"&&typeof y==="object"&&Array.isArray(x)===Array.isArray(y)){
        const keys=new Set([...Object.keys(x),...Object.keys(y)]);
        for(const key of keys){seen++;pending.push([Array.isArray(x)?`${path}[${key}]`:`${path}.${key}`,x[key],y[key]]);}
      }else sourceShape.changed_json_paths.push({path,before_type:kind(x),after_type:kind(y)});
    }
  }catch(_){}
  let docHead={valid:false,type_matches:false,uuid_matches:false,stable_after_volatile_metadata_removed:false,volatile_metadata_fields:["updateTime","client","version"]};
  try{
    const extract=text=>{const line=firstLine(text);const split=line.indexOf("||");if(split<0)throw new Error("No DOCHEAD separator");return {shell:JSON.parse(line.slice(0,split)),body:JSON.parse(line.slice(split+2).replace(/\|$/,""))};};
    const {shell:leftShell,body:leftBody}=extract(first),{shell:rightShell,body:rightBody}=extract(second);
    docHead.valid=true;
    docHead.type_matches=leftShell.type==="DOCHEAD"&&rightShell.type==="DOCHEAD";
    docHead.uuid_matches=leftBody.uuid===args.expected_document_uuid&&rightBody.uuid===args.expected_document_uuid;
    const stable=x=>{const copy={...x};for(const key of ["updateTime","client","version"])delete copy[key];return JSON.stringify(copy);};
    docHead.stable_after_volatile_metadata_removed=stable(leftBody)===stable(rightBody)&&JSON.stringify(leftShell)===JSON.stringify(rightShell);
  }catch(_){}
  return {ok:true,status:"observed",document_uuid:current.uuid,project_uuid:current.parentProjectUuid,
    first_bytes:new TextEncoder().encode(first).length,second_bytes:new TextEncoder().encode(second).length,
    first_sha256:await hash(first),second_sha256:await hash(second),record_count_first:before.length,record_count_second:after.length,
    changed_record_count:changed,changed_record_types:counts,first_different_record:firstDifferent,
    changed_content_record_count:changedContent,changed_content_record_types:contentCounts,first_content_different:firstContentDifferent,
    dochead_probe:docHead,
    source_text_returned:false,limitation:"This compares immediate reads only. It does not expose source records or prove transactionally consistent edits."};
}catch(e){return {ok:false,status:"unsupported",reason:String(e.message)};}
