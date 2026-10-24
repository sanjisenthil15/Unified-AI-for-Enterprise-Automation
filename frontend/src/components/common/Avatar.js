import React, { useState } from 'react';
import './Avatar.css';

function slugify(value) {
  return (value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

function initials(name) {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

/**
 * Employee/user avatar. Shows a real photo when one exists at
 * /employee-photos/<slug>.jpg (slug = the email's local-part, lowercased,
 * non-alphanumerics collapsed to '-'), falling back to an initials circle
 * otherwise. Photos are plain static assets under frontend/public/ — no
 * backend or DB change needed, and nothing breaks before any exist.
 */
export default function Avatar({ name, email, size = 36, className = '' }) {
  const [errored, setErrored] = useState(false);
  const slug = slugify(email ? email.split('@')[0] : name);
  const showPhoto = Boolean(slug) && !errored;

  return (
    <div
      className={`avatar ${className}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
      title={name || ''}
      role="img"
      aria-label={name ? `${name}'s avatar` : 'Avatar'}
    >
      {showPhoto && (
        <img src={`/employee-photos/${slug}.jpg`} alt="" onError={() => setErrored(true)} />
      )}
      {!showPhoto && <span>{initials(name)}</span>}
    </div>
  );
}
