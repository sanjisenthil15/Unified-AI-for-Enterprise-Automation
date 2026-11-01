/**
 * api/axiosInstance.js
 *
 * Configured Axios instance shared by all API modules.
 *
 * - Sets the base URL to the FastAPI backend.
 * - Attaches the JWT token from localStorage to every request
 *   automatically via a request interceptor.
 * - On a 401 response, clears stored credentials and redirects
 *   to /login so the user is not silently stuck.
 */

import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://127.0.0.1:8000';

const axiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// ── Request interceptor — attach Bearer token if present ────────────
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor — handle expired / revoked sessions ───────
// Dev bypass (REACT_APP_AUTH_DISABLED): the backend never issues 401s for
// missing tokens then, so there is nothing to redirect for.
const AUTH_DISABLED = process.env.REACT_APP_AUTH_DISABLED === 'true';

// Credential submissions legitimately answer 401 for a wrong password —
// those must surface on the form, not bounce the user to /login.
const CREDENTIAL_ENDPOINTS = ['/api/v1/auth/login', '/api/v1/auth/register'];

function isCredentialRequest(url = '') {
  return CREDENTIAL_ENDPOINTS.some((path) => url.includes(path));
}

function goTo(path) {
  if (window.location.pathname !== path) window.location.assign(path);
}

axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (!AUTH_DISABLED && status === 401 && !isCredentialRequest(error.config?.url)) {
      // Expired, invalid, or revoked (password changed/reset elsewhere).
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      goTo('/login');
    } else if (!AUTH_DISABLED && status === 403 && error.response?.data?.detail?.code === 'password_change_required') {
      // Only this specific 403 redirects — ordinary permission 403s are
      // shown by the page that made the request.
      try {
        const user = JSON.parse(localStorage.getItem('user') || 'null');
        if (user) localStorage.setItem('user', JSON.stringify({ ...user, must_change_password: true }));
      } catch { /* ignore malformed cache */ }
      goTo('/change-password');
    }
    return Promise.reject(error);
  }
);

export default axiosInstance;
