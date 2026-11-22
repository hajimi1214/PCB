// Called only in a CLI session opened for a locally registered working copy.
const a = __CLI__.args;
if (typeof eda?.dmt_Project?.getCurrentProjectInfo !== "function")
  return {ok:false,status:"unsupported",reason:"Project identity API absent"};
const project = await eda.dmt_Project.getCurrentProjectInfo();
if (!project?.uuid) return {ok:false,status:"unavailable",reason:"Working copy has no project"};
if (!a.pcb_uuid) return {ok:true,status:"observed",project_uuid:project.uuid};
if (project.uuid !== a.expected_project_uuid)
  return {ok:false,status:"target_mismatch",reason:"Working copy project changed"};
const pcbs = await eda.dmt_Pcb.getAllPcbsInfo();
if (!pcbs.some(p => p.uuid === a.pcb_uuid && p.parentProjectUuid === project.uuid))
  return {ok:false,status:"target_mismatch",reason:"PCB not in working copy"};
const tabId = await eda.dmt_EditorControl.openDocument(a.pcb_uuid);
if (typeof tabId !== "string" || !tabId || typeof eda.dmt_EditorControl.activateDocument !== "function" ||
    await eda.dmt_EditorControl.activateDocument(tabId) !== true)
  return {ok:false,status:"unavailable",reason:"PCB tab could not be activated"};
const ready = await eda.dmt_EditorControl.waitForDocumentReady(tabId, 30000);
const doc = await eda.dmt_SelectControl.getCurrentDocumentInfo();
if (!ready || doc?.uuid !== a.pcb_uuid || doc.parentProjectUuid !== project.uuid || doc.documentType !== 3)
  return {ok:false,status:"target_mismatch",reason:"Working PCB did not become ready"};
return {ok:true,status:"observed",project_uuid:project.uuid,pcb_uuid:doc.uuid};
