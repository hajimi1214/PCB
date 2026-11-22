try {
  const snapshot = await capture();
  return {ok:true, status:"observed", pcb_uuid:a.pcb_uuid, project_uuid:a.expected_project_uuid, ...snapshot};
} catch (e) { return fail("rejected", String(e.message)); }
