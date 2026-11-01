/**
 * pages/ChangePassword/ChangePasswordForm.js
 *
 * Shared by the mandatory first-login screen and the Profile page. On success
 * the backend revokes every earlier session and returns a fresh token — that
 * token is stored here immediately, otherwise the very next request would 401.
 */

import React, { useState } from 'react';
import { changePassword, getCurrentUser } from '../../api/authApi';
import { apiErrorText, isPasswordValid, passwordRules } from '../../utils/passwordPolicy';
import '../HRDashboard/HRDashboard.css';
import './ChangePassword.css';

export default function ChangePasswordForm({ currentLabel = 'Current password', submitLabel = 'Update password', onSuccess }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const rules = passwordRules(next);
  const mismatch = confirm.length > 0 && confirm !== next;
  const sameAsCurrent = next.length > 0 && next === current;
  const canSubmit = current && isPasswordValid(next) && confirm === next && !sameAsCurrent && !submitting;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError('');
    try {
      const { access_token: token } = await changePassword({
        currentPassword: current, newPassword: next, confirmPassword: confirm,
      });
      localStorage.setItem('access_token', token);
      const user = await getCurrentUser();
      localStorage.setItem('user', JSON.stringify(user));
      setCurrent(''); setNext(''); setConfirm('');
      onSuccess?.(user);
    } catch (err) {
      setError(apiErrorText(err, 'Could not change your password. Please try again.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="cp-form" onSubmit={handleSubmit} noValidate>
      {error && <div className="cp-alert cp-alert-error" role="alert">{error}</div>}

      <label className="cp-field">
        <span>{currentLabel}</span>
        <input type="password" autoComplete="current-password" value={current}
          onChange={(e) => setCurrent(e.target.value)} disabled={submitting} required />
      </label>

      <label className="cp-field">
        <span>New password</span>
        <input type="password" autoComplete="new-password" value={next}
          onChange={(e) => setNext(e.target.value)} disabled={submitting}
          aria-describedby="cp-rules" required />
      </label>

      <ul className="cp-rules" id="cp-rules" aria-label="Password requirements">
        {rules.map((r) => (
          <li key={r.key} className={r.ok ? 'is-ok' : ''}>
            <span aria-hidden="true">{r.ok ? '✓' : '•'}</span> {r.label}
          </li>
        ))}
        <li className={next && !sameAsCurrent ? 'is-ok' : ''}>
          <span aria-hidden="true">{next && !sameAsCurrent ? '✓' : '•'}</span> Different from your current password
        </li>
      </ul>

      <label className="cp-field">
        <span>Confirm new password</span>
        <input type="password" autoComplete="new-password" value={confirm}
          onChange={(e) => setConfirm(e.target.value)} disabled={submitting}
          aria-invalid={mismatch} required />
        {mismatch && <small className="cp-field-error">Passwords do not match.</small>}
      </label>

      <button type="submit" className="btn-primary cp-submit" disabled={!canSubmit}>
        {submitting ? 'Saving…' : submitLabel}
      </button>
    </form>
  );
}
