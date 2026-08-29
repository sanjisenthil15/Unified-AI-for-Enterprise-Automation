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

const API_BASE_URL = 'http://127.0.0.1:8000';

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

// ── Response interceptor — handle expired / invalid tokens ──────────
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token is invalid or expired — clear storage and force re-login
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default axiosInstance;
