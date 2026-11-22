// Export one-click Gerber, BOM and pick-and-place data from the exact focused PCB.
const fileDigest = async bytes => {
  const value = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(value), b => b.toString(16).padStart(2,"0")).join("");
};
const exported = [];
try {
  if (!/^[0-9a-f]{64}$/.test(a.expected_source_sha256 || ""))
    return fail("rejected","A verified PCB source digest is required");
  if (typeof a.artifact_directory !== "string" || a.artifact_directory.length > 512)
    return fail("rejected","A managed manufacturing output directory is required");
  const folder = a.artifact_directory.replace(/[\\/]+$/, "").split(/[\\/]/).pop();
  if (!/^pcb-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{16}$/.test(folder || ""))
    return fail("rejected","Manufacturing output directory identity is invalid");
  for (const [group,method] of [
    ["pcb_ManufactureData","getGerberFile"],
    ["pcb_ManufactureData","getBomFile"],
    ["pcb_ManufactureData","getPickAndPlaceFile"],
    ["sys_FileSystem","saveFileToFileSystem"]
  ]) if (typeof api?.[group]?.[method] !== "function")
    return fail("unsupported",`${group}.${method} is absent`);
  if (await semanticSourceHash(await source()) !== a.expected_source_sha256)
    return fail("rejected","PCB changed before manufacturing export");

  const basename = folder;
  const outputs = [
    {kind:"gerber",name:"Gerber.zip",create:()=>api.pcb_ManufactureData.getGerberFile(`${basename}_Gerber`)},
    {kind:"bom",name:"BOM.xlsx",create:()=>api.pcb_ManufactureData.getBomFile(`${basename}_BOM`,"xlsx")},
    {kind:"pick_and_place",name:"PickAndPlace.tsv",create:()=>api.pcb_ManufactureData.getPickAndPlaceFile(`${basename}_PickAndPlace`,"csv","mm")}
  ];
  for (const output of outputs) {
    await guard();
    const file = await output.create();
    await guard();
    if (!file || !Number.isInteger(file.size) || file.size <= 0 || file.size > 80*1024*1024 || typeof file.arrayBuffer !== "function")
      throw new Error(`${output.kind} file is absent, unreadable, or exceeds 80 MiB`);
    const bytes = await file.arrayBuffer();
    if (!(bytes instanceof ArrayBuffer) || bytes.byteLength !== file.size)
      throw new Error(`${output.kind} byte length is inconsistent`);
    if (await semanticSourceHash(await source()) !== a.expected_source_sha256)
      throw new Error("PCB changed while manufacturing data was generated");
    const path = `${a.artifact_directory.replace(/[\\/]+$/, "")}\\${output.name}`;
    if (await api.sys_FileSystem.saveFileToFileSystem(path,file) !== true)
      throw new Error(`${output.kind} file save was not confirmed`);
    exported.push({kind:output.kind,name:output.name,bytes:file.size,sha256:await fileDigest(bytes)});
    await guard();
    if (await semanticSourceHash(await source()) !== a.expected_source_sha256)
      throw new Error("PCB changed during manufacturing export");
  }
  return {ok:true,status:"completed",pcb_uuid:a.pcb_uuid,project_uuid:a.expected_project_uuid,
    source_sha256:a.expected_source_sha256,gerber_profile:"JLCEDA one-click defaults",files:exported,
    manufacturing_acceptance:false,independent_cam_review_required:true};
} catch (e) {
  return fail(exported.length ? "partial" : "rejected",String(e.message),
    {files:exported,discard_output_directory:true});
}
