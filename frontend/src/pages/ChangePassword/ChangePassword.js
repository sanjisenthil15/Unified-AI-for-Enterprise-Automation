/**
 * pages/ChangePassword/ChangePassword.js
 *
 * Mandatory first-login screen. Accounts onboarded with an HR-issued
 * temporary password land here and cannot reach the rest of the app until
 * they set their own (the backend answers every other API with
 * 403 password_change_required until then). Rendered outside AppLayout so
 * there is no sidebar to navigate away with.
 */

import React from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import ChangePasswordForm from './ChangePasswordForm';
import './ChangePassword.css';

function storedUser() {
  try { return JSON.parse(localStorage.getItem('user') || 'null'); } catch { return null; }
}

function homeFor(user) {
  return user?.role?.name?.toLowerCase() === 'hr_manager' ? '/hr' : '/dashboard';
}

export default function ChangePassword() {
  const navigate = useNavigate();
  const user = storedUser();

  if (!localStorage.getItem('access_token')) return <Navigate to="/login" replace />;
  // Only accounts that still hold a temporary password belong here; everyone
  // else changes their password from My Profile.
  if (!user?.must_change_password) return <Navigate to="/profile" replace />;

  function signOut() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    navigate('/login', { replace: true });
  }

  return (
    <div className="cp-page">
      <div className="cp-card" role="main">
        <div className="cp-brand" aria-hidden="true">⚡</div>
        <h1>Set your new password</h1>
        <p className="cp-intro">
          Welcome{user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}! Your account was created with a
          temporary password from HR. Choose your own password to continue — the temporary one will stop working.
        </p>

        <ChangePasswordForm
          currentLabel="Temporary password"
          submitLabel="Set password and continue"
          onSuccess={(updated) => navigate(homeFor(updated), { replace: true })}
        />

        <button type="button" className="cp-signout" onClick={signOut}>
          Not you? Sign out
        </button>
      </div>
    </div>
  );
}
