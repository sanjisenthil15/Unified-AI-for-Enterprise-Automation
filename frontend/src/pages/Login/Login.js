/**
 * pages/Login/Login.js
 *
 * Login page — connected to the FastAPI backend.
 *
 * On submit:
 *   1. POST /api/v1/auth/login with email + password.
 *   2. Store access_token and user object in localStorage.
 *   3. Navigate to /dashboard.
 *   4. On failure, show "Invalid email or password."
 *
 * UI is unchanged — only the handleSubmit logic was updated.
 */

import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { getRegistrationStatus, loginUser, getCurrentUser } from '../../api/authApi';
import './Login.css';

// Module chips shown on the brand panel (static — UI unchanged)
const MODULES = [
  '🤖 AI Recruitment',
  '🎧 Customer Support',
  '🚨 Incident Management',
  '🎙️ Meeting Intelligence',
  '📊 Analytics Dashboard',
  '👥 Employee Management',
];

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();

  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [error,    setError]    = useState('');
  const [loading,  setLoading]  = useState(false);
  // null while unknown; only offer sign-up when the backend says it's open.
  const [registrationOpen, setRegistrationOpen] = useState(null);

  useEffect(() => {
    let active = true;
    getRegistrationStatus().then((open) => { if (active) setRegistrationOpen(open); });
    return () => { active = false; };
  }, []);
  const justRegistered = Boolean(location.state?.registered);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    // Basic client-side guard
    if (!email.trim() || !password.trim()) {
      setError('Please enter your email and password.');
      return;
    }

    setLoading(true);
    try {
      // Step 1 — Authenticate and receive JWT
      const tokenData = await loginUser(email.trim(), password);

      // Step 2 — Persist token so axiosInstance can attach it
      localStorage.setItem('access_token', tokenData.access_token);

      // Step 3 — Fetch full user profile and cache it
      const user = await getCurrentUser();
      localStorage.setItem('user', JSON.stringify(user));

      // Step 4 — Accounts still on an HR-issued temporary password must set
      // their own before anything else (the backend blocks other APIs too).
      const role = user?.role?.name?.toLowerCase();
      if (user?.must_change_password) {
        navigate('/change-password', { replace: true });
      } else if (role === 'hr_manager') {
        navigate('/hr');
      } else {
        navigate('/dashboard');
      }
    } catch (err) {
      // Step 5 — Wrong credentials stay deliberately generic (no account
      // enumeration); a rate-limit lock (429) or a disabled account (403)
      // shows the server's message so the user knows to wait / ask HR.
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if ((status === 429 || status === 403) && typeof detail === 'string') {
        setError(detail);
      } else {
        setError('Invalid email or password.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">

      {/* ── Left: Brand panel (UI unchanged) ───────────────────── */}
      <div className="login-brand-panel">
        <div className="login-logo" aria-hidden="true">⚡</div>

        <h1 className="login-brand-title">
          Unified AI for<br />Enterprise Automation
        </h1>

        <p className="login-brand-subtitle">
          One intelligent platform. Six powerful modules.
          Driven by a shared AI Decision Engine.
        </p>

        <div className="login-modules" role="list" aria-label="Available modules">
          {MODULES.map((mod) => (
            <span key={mod} className="login-module-chip" role="listitem">
              {mod}
            </span>
          ))}
        </div>
      </div>

      {/* ── Right: Login form (UI unchanged) ───────────────────── */}
      <div className="login-form-panel">
        <div className="login-form-header">
          <h2>Welcome back</h2>
          <p>Sign in to your enterprise account</p>
        </div>

        <form
          className="login-form"
          onSubmit={handleSubmit}
          noValidate
          aria-label="Login form"
        >
          {justRegistered && !error && (
            <div className="login-success" role="status">
              Account created — sign in below.
            </div>
          )}

          {/* Email */}
          <div className="form-group">
            <label htmlFor="email">Email address</label>
            <div className="input-wrapper">
              <span className="input-icon" aria-hidden="true">✉️</span>
              <input
                id="email"
                type="email"
                className="form-input"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                autoFocus
                aria-required="true"
                disabled={loading}
              />
            </div>
          </div>

          {/* Password */}
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="input-wrapper">
              <span className="input-icon" aria-hidden="true">🔒</span>
              <input
                id="password"
                type="password"
                className="form-input"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                aria-required="true"
                disabled={loading}
              />
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className="login-btn"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? 'Signing in…' : 'Sign In →'}
          </button>
        </form>

        {registrationOpen === true && (
          <p className="login-footer">
            No account? <Link to="/register">Create one</Link>
          </p>
        )}
        {registrationOpen === false && (
          <p className="login-footer">
            Need an account? Ask HR or an administrator to create one for you.
          </p>
        )}
        <p className="login-footer">
          © {new Date().getFullYear()} Unified AI Enterprise Platform
        </p>
      </div>
    </div>
  );
}
