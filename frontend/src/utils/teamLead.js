/**
 * utils/teamLead.js
 *
 * "Am I a team lead" derivation — reuses data the app already fetches
 * (employeeApi.listProjects()'s nested team_lead, employeeApi
 * .getMyEmployeeRecord()'s own id) instead of adding a new backend field
 * just for this flag.
 */

export function getLedProjects(myEmployeeId, allProjects) {
  if (!myEmployeeId || !Array.isArray(allProjects)) return [];
  return allProjects.filter((p) => p.team_lead?.id === myEmployeeId);
}
