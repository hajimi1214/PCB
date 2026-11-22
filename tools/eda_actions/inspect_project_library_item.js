// Query one exact imported device and footprint under the explicit project-library UUID.
const a=__CLI__.args||{};const api=typeof eda==="undefined"?null:eda;
if(!/^[0-9a-f]{8,64}$/i.test(a.library_uuid||"")||!/^[0-9a-f]{8,64}$/i.test(a.device_uuid||"")||!/^[0-9a-f]{8,64}$/i.test(a.footprint_uuid||""))
  return {ok:false,status:"rejected",reason:"Exact project-library, device and footprint UUIDs are required"};
const answer={ok:true,status:"observed",library_uuid:a.library_uuid,device_uuid:a.device_uuid,footprint_uuid:a.footprint_uuid};
try{answer.device=await api.lib_Device.get(a.device_uuid,a.library_uuid);answer.device_found=!!answer.device;}
catch(error){answer.device_found=false;answer.device_error={name:error?.name??null,message:error?.message??null,text:String(error)};}
try{answer.footprint=await api.lib_Footprint.get(a.footprint_uuid,a.library_uuid);answer.footprint_found=!!answer.footprint;}
catch(error){answer.footprint_found=false;answer.footprint_error={name:error?.name??null,message:error?.message??null,text:String(error)};}
if(answer.device)answer.device={uuid:answer.device.uuid,libraryUuid:answer.device.libraryUuid,name:answer.device.name};
if(answer.footprint)answer.footprint={
  uuid:answer.footprint.uuid,libraryUuid:answer.footprint.libraryUuid,
  libraryType:answer.footprint.libraryType??null,name:answer.footprint.name,
  own_keys:Object.keys(answer.footprint).slice(0,32)
};
return answer;
