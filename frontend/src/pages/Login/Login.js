/**
 * pages/Login/Login.js
 *
 * Login & Customer Registration page — connected to the FastAPI backend.
 *
 * Supports:
 *   1. Sign in (JWT authentication for all roles)
 *   2. Register as Customer (creates role="customer", navigates directly to /customer-support)
 */

import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { getRegistrationStatus, loginUser, getCurrentUser, registerCustomer } from '../../api/authApi';
import './Login.css';

// Module chips shown on the brand panel
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

  const [mode, setMode] = useState(() => {
    const params = new URLSearchParams(location.search);
    return params.get('tab') === 'customer' || params.get('register') === 'customer' ? 'register-customer' : 'login';
  });

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState(
    location.state?.registered ? 'Account created — sign in below.' : ''
  );
  const [loading, setLoading] = useState(false);
  const [registrationStatus, setRegistrationStatus] = useState({ enabled: null, customerRegistrationEnabled: true });

  useEffect(() => {
    let active = true;
    getRegistrationStatus().then((statusObj) => {
      if (active) {
        if (typeof statusObj === 'boolean') {
          setRegistrationStatus({ enabled: statusObj, customerRegistrationEnabled: true });
        } else {
          setRegistrationStatus(statusObj);
        }
      }
    });
    return () => { active = false; };
  }, []);

  async function handleLogin(e) {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    if (!email.trim() || !password.trim()) {
      setError('Please enter your email and password.');
      return;
    }

    setLoading(true);
    try {
      const tokenData = await loginUser(email.trim(), password);
      localStorage.setItem('access_token', tokenData.access_token);

      const user = await getCurrentUser();
      localStorage.setItem('user', JSON.stringify(user));

      const role = user?.role?.name?.toLowerCase();
      if (user?.must_change_password) {
        navigate('/change-password', { replace: true });
      } else if (role === 'customer') {
        navigate('/customer-support', { replace: true });
      } else if (role === 'hr_manager') {
        navigate('/hr');
      } else {
        navigate('/dashboard');
      }
    } catch (err) {
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

  async function handleCustomerRegister(e) {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    if (!fullName.trim() || !email.trim() || !password || !confirmPassword) {
      setError('Please fill in all required fields.');
      return;
    }

    if (fullName.trim().length < 2) {
      setError('Full name must be at least 2 characters.');
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      setError('Please enter a valid email address.');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (!/[A-Z]/.test(password) || !/[0-9]/.test(password)) {
      setError('Password must contain at least one uppercase letter and one digit.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await registerCustomer({
        fullName: fullName.trim(),
        email: email.trim(),
        password,
        confirmPassword,
      });

      // Automatically sign in the customer upon successful registration
      try {
        const tokenData = await loginUser(email.trim(), password);
        localStorage.setItem('access_token', tokenData.access_token);
        const user = await getCurrentUser();
        localStorage.setItem('user', JSON.stringify(user));
        navigate('/customer-support', { replace: true });
      } catch {
        setSuccessMsg('Customer account created successfully! Please sign in below.');
        setMode('login');
        setPassword('');
        setConfirmPassword('');
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail) && detail.length) {
        setError(detail.map((d) => d.msg?.replace(/^Value error, /, '') || 'Invalid input').join(' '));
      } else {
        setError('Could not create customer account. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      {/* ── Left: Brand panel ───────────────────── */}
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

      {/* ── Right: Form panel ───────────────────── */}
      <div className="login-form-panel">
        {/* Tab switcher: Sign In vs Register as Customer */}
        <div className="login-tabs" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'login'}
            className={`login-tab-btn ${mode === 'login' ? 'active' : ''}`}
            onClick={() => { setMode('login'); setError(''); }}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'register-customer'}
            className={`login-tab-btn ${mode === 'register-customer' ? 'active' : ''}`}
            onClick={() => { setMode('register-customer'); setError(''); }}
          >
            Register as Customer
          </button>
        </div>

        <div className="login-form-header">
          <h2>{mode === 'login' ? 'Welcome back' : 'Register as Customer'}</h2>
          <p>
            {mode === 'login'
              ? 'Sign in to your enterprise account'
              : 'Create an account to submit and track support tickets'}
          </p>
        </div>

        {mode === 'login' ? (
          <form
            className="login-form"
            onSubmit={handleLogin}
            noValidate
            aria-label="Login form"
          >
            {successMsg && !error && (
              <div className="login-success" role="status">
                {successMsg}
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
        ) : (
          <form
            className="login-form"
            onSubmit={handleCustomerRegister}
            noValidate
            aria-label="Customer registration form"
          >
            {/* Full Name */}
            <div className="form-group">
              <label htmlFor="reg-fullname">Full Name *</label>
              <div className="input-wrapper">
                <span className="input-icon" aria-hidden="true">👤</span>
                <input
                  id="reg-fullname"
                  type="text"
                  className="form-input"
                  placeholder="e.g. Jane Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  autoFocus
                  aria-required="true"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Email */}
            <div className="form-group">
              <label htmlFor="reg-email">Email Address *</label>
              <div className="input-wrapper">
                <span className="input-icon" aria-hidden="true">✉️</span>
                <input
                  id="reg-email"
                  type="email"
                  className="form-input"
                  placeholder="customer@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  aria-required="true"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Password */}
            <div className="form-group">
              <label htmlFor="reg-password">Password *</label>
              <div className="input-wrapper">
                <span className="input-icon" aria-hidden="true">🔒</span>
                <input
                  id="reg-password"
                  type="password"
                  className="form-input"
                  placeholder="8+ chars, 1 uppercase, 1 digit"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  aria-required="true"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Confirm Password */}
            <div className="form-group">
              <label htmlFor="reg-confirm">Confirm Password *</label>
              <div className="input-wrapper">
                <span className="input-icon" aria-hidden="true">🔒</span>
                <input
                  id="reg-confirm"
                  type="password"
                  className="form-input"
                  placeholder="Re-enter your password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
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
              {loading ? 'Creating Customer Account…' : 'Register as Customer →'}
            </button>
          </form>
        )}

        {/* Footers */}
        <div style={{ marginTop: '1.5rem', textAlign: 'center' }}>
          {mode === 'login' ? (
            <>
              <p className="login-footer" style={{ marginTop: 0, marginBottom: '0.5rem' }}>
                Need support?{' '}
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => { setMode('register-customer'); setError(''); }}
                >
                  Register as Customer
                </button>
              </p>
              {registrationStatus.enabled === true && (
                <p className="login-footer" style={{ marginTop: '0.25rem', marginBottom: '0.5rem' }}>
                  No account? <Link to="/register">Create one</Link>
                </p>
              )}
              {registrationStatus.enabled === false && (
                <p className="login-footer" style={{ marginTop: '0.25rem', marginBottom: '0.5rem' }}>
                  Need an account? Ask HR or an administrator to create one for you.
                </p>
              )}
            </>
          ) : (
            <p className="login-footer" style={{ marginTop: 0, marginBottom: '0.5rem' }}>
              Already registered?{' '}
              <button
                type="button"
                className="link-btn"
                onClick={() => { setMode('login'); setError(''); }}
              >
                Sign In
              </button>
            </p>
          )}
        </div>

        <p className="login-footer">
          © {new Date().getFullYear()} Unified AI Enterprise Platform
        </p>
      </div>
    </div>
  );
}
