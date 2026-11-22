// Import one approved public reference package to a specifically named new JLCEDA project.
const a = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
const fail = (status, reason) => ({ok:false,status,reason});
try {
  if (!/^[a-z0-9][a-z0-9-]{2,47}$/.test(a.project_slug || "") ||
      !["KiCad","EAGLE"].includes(a.file_type) || a.destination !== "new_user_project")
    return fail("rejected","Reference project identity or file type is invalid");
  for (const [group,method] of [
    ["sys_Environment","isClient"],
    ["sys_Environment","isJLCEDAProEdition"],
    ["sys_FileSystem","readFileFromFileSystem"],
    ["sys_FileManager","importProjectByProjectFile"],
    ["dmt_Project","getCurrentProjectInfo"],["dmt_Project","openProject"],["dmt_Project","waitForReady"],
    ["dmt_Board","getAllBoardsInfo"],["dmt_Team","getAllTeamsInfo"],["sys_Environment","getUserInfo"]
  ]) if (typeof api?.[group]?.[method] !== "function")
    return fail("unsupported",`${group}.${method} is absent`);
  if (api.sys_Environment.isClient() !== true || api.sys_Environment.isJLCEDAProEdition() !== true)
    return fail("unsupported","Reference import requires the local JLCEDA Pro client");
  const current = await api.dmt_Project.getCurrentProjectInfo();
  if (current?.uuid) return fail("target_mismatch","The selected editor session already has a project; use a blank import session");
  const extension=String(a.source_path||"").split(".").pop().toLowerCase();
  if(a.file_type==="KiCad"&&extension!=="zip"||a.file_type==="EAGLE"&&!new Set(["brd","zip"]).has(extension))
    return fail("rejected","KiCad import requires a ZIP. EAGLE import requires a BRD or ZIP.");
  const file = await api.sys_FileSystem.readFileFromFileSystem(a.source_path);
  if (!file || !Number.isInteger(file.size) || file.size <= 0 || file.size > 100*1024*1024 ||
      typeof file.arrayBuffer !== "function")
    return fail("unsupported","Reference archive is absent, unreadable, or exceeds 100 MiB");
  const teams=await api.dmt_Team.getAllTeamsInfo();
  if (!Array.isArray(teams)) return fail("unsupported","EDA did not return a user team list");
  const user=api.sys_Environment.getUserInfo();
  const namedPersonal=teams.filter(team=>["个人","personal"].includes(String(team?.name ?? "").toLowerCase()) && typeof team.uuid==="string" && team.uuid);
  const userTeam=teams.filter(team=>typeof team?.uuid==="string" && team.uuid===user?.uuid);
  const personalTeams=namedPersonal.length===1?namedPersonal:userTeam;
  if (personalTeams.length!==1) return fail("unavailable","EDA did not identify the personal project owner without choosing another team",
    {team_count:teams.length,named_personal_count:namedPersonal.length,user_uuid_team_match_count:userTeam.length});
  const imported = await api.sys_FileManager.importProjectByProjectFile(
    file,
    a.file_type,
    {associateFootprint:true,associate3DModel:false},
    {operation:"New Project",newProjectOwnerTeamUuid:personalTeams[0].uuid,
      newProjectName:a.project_slug,newProjectFriendlyName:a.project_friendly_name}
  );
  if (!imported || typeof imported.uuid !== "string" || !imported.uuid)
    return fail("rejected","EDA did not confirm the new reference project",{import_return_type:typeof imported});
  if (await api.dmt_Project.openProject(imported.uuid) !== true ||
      await api.dmt_Project.waitForReady(imported.uuid,30000) !== true)
    return fail("partial","Reference project was created but could not be opened for inspection",
      {project_uuid:imported.uuid,project_created:true});
  const boards=await api.dmt_Board.getAllBoardsInfo();
  if (!Array.isArray(boards) || boards.length === 0 || boards.length > 64 ||
      boards.some(board=>board.parentProjectUuid!==imported.uuid || !board.pcb?.uuid || !board.schematic?.uuid))
    return fail("partial","Imported project Board associations are incomplete or ambiguous",
      {project_uuid:imported.uuid,project_created:true});
  const projectAfter=await api.dmt_Project.getCurrentProjectInfo();
  if (projectAfter?.uuid!==imported.uuid)
    return fail("target_mismatch","EDA focus changed after reference import",{project_uuid:imported.uuid,project_created:true});
  return {ok:true,status:"new_user_project_created",project_uuid:imported.uuid,
    project_name:imported.name ?? null,friendly_name:imported.friendlyName ?? null,
    destination:"new_user_project",boards:boards.map(board=>({board_name:board.name,
      pcb_uuid:board.pcb.uuid,pcb_name:board.pcb.name,schematic_uuid:board.schematic.uuid,
      schematic_name:board.schematic.name})),
    source_file_name:file.name ?? null,source_file_bytes:file.size,file_type:a.file_type,
    import_options:{associate_footprint:true,associate_3d_model:false},
    local_only:false,cloud_upload:true,source_files_are_public:true};
} catch (error) {
  return fail("rejected",String(error?.message ?? error));
}
