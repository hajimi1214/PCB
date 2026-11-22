// Cached results never certify a fresh check. run=true is an intentional native check.
const args = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
const has = (g, m) => typeof api?.[g]?.[m] === "function";
const fail = (status, reason) => ({ok: false, status, reason, native_check_passed: false});
if (!args.pcb_uuid || args.expected_document_uuid !== args.pcb_uuid || !args.expected_project_uuid)
  return fail("rejected", "DRC requires the explicit PCB UUID as the focused document and a project UUID.");
if (!has("dmt_SelectControl", "getCurrentDocumentInfo")) return fail("unsupported", "Document identity read is absent.");
const guard = async () => {
  const d = await api.dmt_SelectControl.getCurrentDocumentInfo();
  return d?.uuid === args.pcb_uuid && d.parentProjectUuid === args.expected_project_uuid && d.documentType === 3;
};
if (!await guard()) return fail("target_mismatch", "Focused PCB/project differs from the explicit target.");
const run = args.run === true, method = run ? "checkDetailed" : "getDrcResult";
if (!has("pcb_Drc", method)) return fail("unsupported", `pcb_Drc.${method} is absent; no weaker check was substituted.`);
const startedAt = Date.now();
let raw;
try { raw = run ? await api.pcb_Drc.checkDetailed({includeGroups: true}) : await api.pcb_Drc.getDrcResult(); }
catch (_) { return fail("incomplete", "Native DRC threw an error; incomplete results cannot pass."); }
if (!await guard()) return fail("target_mismatch", "Focus changed during DRC; discard the result.");
if (!raw || !["notChecked","checking","passed","failed","incomplete"].includes(raw.state) ||
    !Number.isInteger(raw.totalCount) || raw.totalCount < 0 || !Number.isInteger(raw.failedItems) || raw.failedItems < 0 ||
    !Array.isArray(raw.violations)) return fail("unsupported", "Unexpected native DRC result schema.");
// Unknown timestamp units, a stale cache, or a missing timestamp must not pass.
// The SDK exposes no run token. Assuming epoch-millisecond timestamps, equality
// could be cached data from this same millisecond; ambiguous results fail closed.
const fresh = run && Number.isFinite(raw.checkedAt) && raw.checkedAt > startedAt && raw.checkedAt <= Date.now();
const passed = fresh && raw.state === "passed" && raw.totalCount === 0 && raw.failedItems === 0 && raw.violations.length === 0;
return {
  ok: true, status: "observed", project_uuid: args.expected_project_uuid, document_uuid: args.pcb_uuid,
  run_requested: run, fresh_result: fresh, native_check_passed: passed,
  state: raw.state, total_count: raw.totalCount, failed_items: raw.failedItems, checked_at: raw.checkedAt ?? null,
  violations: raw.violations.slice(0, 40), returned_violations: Math.min(raw.violations.length, 40),
  details_truncated: raw.violations.length > 40, groups: raw.groups?.slice(0, 64),
  limitation: "Only a timestamp-fresh, complete native DRC may pass this gate. Timestamp units and same-document content revisions were not verified; this is not a schematic equivalence, SI/PI, DFM or functional test."
};
