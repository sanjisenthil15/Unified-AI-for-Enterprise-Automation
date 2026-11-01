/**
 * utils/projectLifecycle.js
 *
 * Project lifecycle rules shared by the Projects page and Employee
 * Management. These mirror backend/modules/employee_management/service.py
 * (ALLOWED_TRANSITIONS) and core/authorization.py — the backend is the
 * real enforcement; this only decides which controls to show.
 */

export const PROJECT_STATUSES = ['planning', 'active', 'on_hold', 'completed', 'cancelled', 'archived'];

export const ALLOWED_PROJECT_TRANSITIONS = {
  planning: ['active', 'cancelled', 'archived'],
  active: ['on_hold', 'completed', 'cancelled', 'archived'],
  on_hold: ['active', 'cancelled', 'archived'],
  completed: ['archived'],
  cancelled: ['archived'],
  archived: [],
};

export const PROJECT_STATUS_BADGE = {
  planning: 'blue',
  active: 'green',
  on_hold: 'amber',
  completed: 'green',
  cancelled: 'red',
  archived: 'purple',
};

// Metadata (name/description/dates) is frozen once a project reaches one of these.
export const METADATA_LOCKED_STATUSES = ['completed', 'cancelled', 'archived'];

// Who may create/delete projects and assign managers or team leads.
export const PROJECT_ADMIN_ROLES = ['admin', 'hr_manager'];

export function projectStatusLabel(status) {
  return (status || 'planning').replace('_', ' ');
}

export function allowedNextStatuses(status) {
  return ALLOWED_PROJECT_TRANSITIONS[status || 'planning'] || [];
}

/** Admin / HR Manager manage every project; a Manager only the projects
 * they're assigned to (project.manager.id). Team leads and employees are
 * read-only. */
export function canManageProject(role, userId, project) {
  if (PROJECT_ADMIN_ROLES.includes(role)) return true;
  return role === 'manager' && project?.manager?.id != null && project.manager.id === userId;
}

export function canEditProjectMetadata(role, userId, project) {
  return canManageProject(role, userId, project)
    && !METADATA_LOCKED_STATUSES.includes(project?.status || 'planning');
}
