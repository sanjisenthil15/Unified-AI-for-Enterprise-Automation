/**
 * api/authApi.js
 *
 * API functions for the Authentication module.
 * All calls go through the shared axiosInstance which attaches
 * the JWT token automatically.
 */

import axiosInstance from './axiosInstance';

/**
 * POST /api/v1/auth/login
 *
 * Sends email and password to the backend.
 * Returns { access_token, token_type } on success.
 * Throws an Axios error on failure (4xx / 5xx).
 *
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{ access_token: string, token_type: string }>}
 */
export async function loginUser(email, password) {
  const response = await axiosInstance.post('/api/v1/auth/login', {
    email,
    password,
  });
  return response.data;
}

/**
 * GET /api/v1/auth/me
 *
 * Fetches the currently authenticated user's profile.
 * Requires a valid Bearer token in localStorage (attached by interceptor).
 * Returns { id, full_name, email, role: { id, name } } on success.
 *
 * @returns {Promise<{ id: number, full_name: string, email: string, role: { id: number, name: string } }>}
 */
export async function getCurrentUser() {
  const response = await axiosInstance.get('/api/v1/auth/me');
  return response.data;
}

/**
 * GET /api/v1/auth/roles
 *
 * Public listing of roles, used to populate the registration form.
 *
 * @returns {Promise<Array<{ id: number, name: string, description: string|null }>>}
 */
export async function listRoles() {
  const response = await axiosInstance.get('/api/v1/auth/roles');
  return response.data;
}

/**
 * GET /api/v1/auth/users
 *
 * Lists active user accounts — used to populate "assign to" dropdowns.
 *
 * @returns {Promise<Array<{ id: number, full_name: string, email: string }>>}
 */
export async function listUsers() {
  const response = await axiosInstance.get('/api/v1/auth/users');
  return response.data;
}

/**
 * POST /api/v1/auth/register
 *
 * Creates a new user account.
 *
 * @param {{ fullName: string, email: string, password: string, roleId: number }} payload
 * @returns {Promise<{ id: number, full_name: string, email: string, role: object }>}
 */
/** Public: whether self-registration is open (closed on hosted deployments
 * unless an administrator enables it). Treated as closed if unknown. */
export async function getRegistrationStatus() {
  try {
    const response = await axiosInstance.get('/api/v1/auth/registration-status');
    return {
      enabled: Boolean(response.data?.enabled),
      customerRegistrationEnabled: response.data?.customer_registration_enabled !== false,
    };
  } catch {
    return { enabled: false, customerRegistrationEnabled: true };
  }
}

export async function registerUser({ fullName, email, password }) {
  const response = await axiosInstance.post('/api/v1/auth/register', {
    full_name: fullName,
    email,
    password,
  });
  return response.data;
}

export async function registerCustomer({ fullName, email, password, confirmPassword }) {
  const response = await axiosInstance.post('/api/v1/auth/register-customer', {
    full_name: fullName,
    email,
    password,
    confirm_password: confirmPassword,
  });
  return response.data;
}

/**
 * POST /api/v1/auth/change-password
 *
 * Changes the caller's own password (also completes the mandatory first-login
 * change). Every earlier session is revoked server-side; the response carries
 * the ONLY valid token afterwards, so callers must store it.
 *
 * @returns {Promise<{ access_token: string, token_type: string }>}
 */
export async function changePassword({ currentPassword, newPassword, confirmPassword }) {
  const response = await axiosInstance.post('/api/v1/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
    confirm_password: confirmPassword,
  });
  return response.data;
}

/**
 * POST /api/v1/auth/users/{userId}/reset-password  (admin / HR only)
 *
 * Issues a one-time temporary password for another account, forces a change
 * at their next login and signs out their existing sessions.
 *
 * @returns {Promise<{ user_id: number, temporary_password: string, must_change_password: boolean }>}
 */
export async function resetUserPassword(userId) {
  const response = await axiosInstance.post(`/api/v1/auth/users/${userId}/reset-password`);
  return response.data;
}
