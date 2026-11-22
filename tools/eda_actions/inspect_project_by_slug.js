// Narrowly check the personal workspace for one exact project slug.
const a = __CLI__.args || {};
const api = typeof eda === "undefined" ? null : eda;
const fail = (status, reason) => ({ok:false,status,reason});
try {
  if (!/^[a-z0-9][a-z0-9-]{2,47}$/.test(a.project_slug || ""))
    return fail("rejected","Project slug is invalid");
  for (const [group,method] of [["dmt_Team","getAllTeamsInfo"],["dmt_Project","getAllProjectsUuid"],["dmt_Project","getProjectInfo"]])
    if (typeof api?.[group]?.[method] !== "function") return fail("unsupported",`${group}.${method} is absent`);
  const teams=await api.dmt_Team.getAllTeamsInfo();
  if (!Array.isArray(teams) || teams.length>64) return fail("unsupported","Team list is invalid or exceeds the limit");
  const user=api.sys_Environment?.getUserInfo?.();
  const namedPersonal=teams.filter(team=>["个人","personal"].includes(String(team?.name ?? "").toLowerCase()) && typeof team.uuid==="string");
  const userTeam=teams.filter(team=>typeof team?.uuid==="string" && team.uuid===user?.uuid);
  const personal=namedPersonal.length===1?namedPersonal:userTeam;
  if (personal.length!==1) return {ok:false,status:"unavailable",reason:"Personal project owner could not be identified without choosing another team",
    team_count:teams.length,named_personal_count:namedPersonal.length,user_uuid_team_match_count:userTeam.length};
  const uuids=await api.dmt_Project.getAllProjectsUuid(personal[0].uuid);
  if (!Array.isArray(uuids) || uuids.length>512 || uuids.some(id=>typeof id!=="string"))
    return fail("unsupported","Personal project index is invalid or exceeds 512 entries");
  const matches=[];
  for (const uuid of uuids) {
    const project=await api.dmt_Project.getProjectInfo(uuid);
    if (!project) return fail("incomplete","A project summary was unavailable; absence cannot be confirmed");
    if (project.name===a.project_slug || project.friendlyName===`PCB visual reference - ${a.project_slug}`)
      matches.push({uuid:project.uuid ?? uuid,name:project.name ?? null,friendly_name:project.friendlyName ?? null});
  }
  return {ok:true,status:"observed",project_slug:a.project_slug,matches,exact_match_count:matches.length,
    absence_confirmed:matches.length===0,personal_project_metadata_returned_only_for_exact_matches:true};
} catch (error) {
  return fail("unavailable",String(error?.message ?? error));
}
