// Check whether exact schematic-imported device and footprint IDs resolve in the current EDA libraries.
const a=__CLI__.args||{};const api=typeof eda==="undefined"?null:eda;
if(!/^[0-9a-f]{8,64}$/i.test(a.device_uuid||"")||!/^[0-9a-f]{8,64}$/i.test(a.footprint_uuid||""))
  return {ok:false,status:"rejected",reason:"Exact device and footprint UUIDs are required"};
for(const [group,method] of [["lib_Device","get"],["lib_Footprint","get"],["lib_LibrariesList","getSystemLibraryUuid"],["lib_LibrariesList","getProjectLibraryUuid"]])
  if(typeof api?.[group]?.[method]!=="function")return {ok:false,status:"unsupported",reason:`${group}.${method} is absent`};
try{
  const probe=async(stage,action)=>{try{return {value:await action()};}catch(error){return {error:{name:error?.name??null,message:error?.message??null,code:error?.code??null,text:String(error)}};}};
  const systemResult=await probe("system-library",()=>api.lib_LibrariesList.getSystemLibraryUuid());
  const systemLibraryUuid=systemResult.value;
  const projectResult=await probe("project-library",()=>api.lib_LibrariesList.getProjectLibraryUuid());
  const projectLibraryUuid=projectResult.value;
  const deviceDefault=await probe("device-default",()=>api.lib_Device.get(a.device_uuid));
  const footprintDefault=await probe("footprint-default",()=>api.lib_Footprint.get(a.footprint_uuid));
  const deviceProject=!deviceDefault.value&&projectLibraryUuid?await probe("device-project",()=>api.lib_Device.get(a.device_uuid,projectLibraryUuid)):{value:undefined};
  const footprintProject=!footprintDefault.value&&projectLibraryUuid?await probe("footprint-project",()=>api.lib_Footprint.get(a.footprint_uuid,projectLibraryUuid)):{value:undefined};
  const deviceSystem=!deviceDefault.value&&systemLibraryUuid?await probe("device-system",()=>api.lib_Device.get(a.device_uuid,systemLibraryUuid)):{value:undefined};
  const footprintSystem=!footprintDefault.value&&systemLibraryUuid?await probe("footprint-system",()=>api.lib_Footprint.get(a.footprint_uuid,systemLibraryUuid)):{value:undefined};
  const device=deviceDefault.value,footprint=footprintDefault.value;
  const fallbackDevice=deviceSystem.value,fallbackFootprint=footprintSystem.value;
  const resolvedDevice=device||deviceProject.value||fallbackDevice,resolvedFootprint=footprint||footprintProject.value||fallbackFootprint;
  return {ok:true,status:"observed",device_found:!!resolvedDevice,footprint_found:!!resolvedFootprint,
    device_uuid:a.device_uuid,footprint_uuid:a.footprint_uuid,
    device_library_uuid:resolvedDevice?.libraryUuid??null,footprint_library_uuid:resolvedFootprint?.libraryUuid??null,
    device_name:resolvedDevice?.name??null,footprint_name:resolvedFootprint?.name??null,
    lookup_errors:{system:systemResult.error??null,project:projectResult.error??null,device_default:deviceDefault.error??null,footprint_default:footprintDefault.error??null,
      device_project:deviceProject.error??null,footprint_project:footprintProject.error??null,
      device_system:deviceSystem.error??null,footprint_system:footprintSystem.error??null},
    limitation:"Library records are looked up by exact IDs; a successful lookup does not prove pad/net import parity."};
}catch(error){
  let detail;
  try{detail={name:error?.name??null,message:error?.message??null,code:error?.code??null,text:String(error)};}catch(_){detail={text:"Unable to describe error"};}
  return {ok:false,status:"unavailable",detail};
}
