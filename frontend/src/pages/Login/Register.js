/**
 * pages/Login/Register.js
 *
 * Self-serve account creation — connected to the FastAPI backend.
 *
 * On submit:
 *   1. POST /api/v1/auth/register with full name + email + password + role.
 *   2. On success, redirect to /login with a confirmation message.
 *
 * Styled to match Login.js (same login-page / login-form classes).
 */

import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { registerUser, listRoles } from '../../api/authApi';
import './Login.css';

const MODULES = [
  '🤖 AI Recruitment',
  '🎧 Customer Support',
  '🚨 Incident Management',
  '🎙️ Meeting Intelligence',
  '📊 Analytics Dashboard',
  '👥 Employee Management',
];

export default function Register() {
  const navigate = useNavigate();

  const [fullName, setFullName] = useState('');
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [roleId,   setRoleId]   = useState('');
  const [roles,    setRoles]    = useState([]);
  const [error,    setError]    = useState('');
  const [loading,  setLoading]  = useState(false);

  useEffect(() => {
    let cancelled = false;
    listRoles()
      .then((list) => {
        if (cancelled) return;
        setRoles(list);
        const employee = list.find((r) => r.name === 'employee');
        setRoleId(String((employee || list[0])?.id || ''));
      })
      .catch(() => { if (!cancelled) setError('Could not load roles. Check backend availability.'); });
    return () => { cancelled = true; };
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!fullName.trim() || !email.trim() || !password.trim() || !roleId) {
      setError('Please fill in every field.');
      return;
    }

    setLoading(true);
    try {
      await registerUser({ fullName: fullName.trim(), email: email.trim(), password, roleId: Number(roleId) });
      navigate('/login', { state: { registered: true } });
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail) && detail.length) {
        // FastAPI/pydantic validation errors (e.g. weak password) come back
        // as a list of {msg, loc, ...} objects rather than a plain string.
        setError(detail.map((d) => d.msg?.replace(/^Value error, /, '') || 'Invalid input').join(' '));
      } else {
        setError('Could not create the account. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
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

      <div className="login-form-panel">
        <div className="login-form-header">
          <h2>Create your account</h2>
          <p>Sign up to join meetings and use the platform</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit} noValidate aria-label="Registration form">
          <div className="form-group">
            <label htmlFor="fullName">Full name</label>
            <div className="input-wrapper">
              <span className="input-icon" aria-hidden="true">🧑</span>
              <input
                id="fullName"
                type="text"
                className="form-input"
                placeholder="Jane Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                autoFocus
                aria-required="true"
                disabled={loading}
              />
            </div>
          </div>

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
                aria-required="true"
                disabled={loading}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="input-wrapper">
              <span className="input-icon" aria-hidden="true">🔒</span>
              <input
                id="password"
                type="password"
                className="form-input"
                placeholder="At least 8 characters, 1 uppercase, 1 digit"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                aria-required="true"
                disabled={loading}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="role">Role</label>
            <div className="input-wrapper">
              <span className="input-icon" aria-hidden="true">🏷️</span>
              <select
                id="role"
                className="form-input"
                value={roleId}
                onChange={(e) => setRoleId(e.target.value)}
                disabled={loading || !roles.length}
              >
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>{role.name}</option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <button type="submit" className="login-btn" disabled={loading} aria-busy={loading}>
            {loading ? 'Creating account…' : 'Create account →'}
          </button>
        </form>

        <p className="login-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
