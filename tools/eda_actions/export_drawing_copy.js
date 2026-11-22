// Server supplies a fresh managed artifact path, never an arbitrary MCP path.
try {
  if (await hash(await source()) !== a.expected_source_sha256)
    return fail("rejected","Working PCB changed since the applied plan");
  need("sys_FileManager","getProjectFile");need("sys_FileSystem","saveFileToFileSystem");
  const file=await api.sys_FileManager.getProjectFile("pcb-working-copy",undefined,"epro2");
  await guard();
  if (!file || !Number.isInteger(file.size) || file.size<=0 || file.size>80*1024*1024 || typeof file.arrayBuffer!=="function")
    return fail("unsupported","Native project export absent or exceeds 80 MiB");
  if (await hash(await source()) !== a.expected_source_sha256)
    return fail("rejected","PCB changed while exporting; artifact was not saved");
  const bytes=await file.arrayBuffer();
  const digest=Array.from(new Uint8Array(await globalThis.crypto.subtle.digest("SHA-256",bytes)),b=>b.toString(16).padStart(2,"0")).join("");
  const saved=await api.sys_FileSystem.saveFileToFileSystem(a.artifact_path,file);
  if (saved!==true) return fail("rejected","Native artifact write not confirmed");
  await guard();
  if (await hash(await source()) !== a.expected_source_sha256)
    return fail("rejected","PCB changed during artifact save; archive requires review");
  return {ok:true,status:"completed",archive_sha256:digest,bytes:file.size,format:"epro2",native_reopen_verified:false};
} catch (e) {return fail("rejected",String(e.message));}
