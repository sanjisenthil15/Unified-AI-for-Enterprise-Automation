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
