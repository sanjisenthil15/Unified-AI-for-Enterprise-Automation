import React, { useEffect, useState } from 'react';
import './Avatar.css';

function slugify(value) {
  return (value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

function initials(name) {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

/**
 * Standard Circular Employee/User Avatar Component.
 *
 * Guarantees:
 *  - Perfectly circular container (border-radius: 50%, aspect-ratio: 1/1, overflow: hidden)
 *  - Fixed width/height that never stretches or squashes in flex or table layouts
 *  - object-fit: cover with object-position: center on the underlying image
 *  - Graceful fallback to styled initials if image is missing, 404, or fails to load
 *  - Dynamic error reset on prop change
 */
export default function Avatar({
  name,
  email,
  size = 36,
  className = '',
  src,
  style = {},
}) {
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    setErrored(false);
  }, [email, name, src]);

  const slug = slugify(email ? email.split('@')[0] : name);
  const imageSrc = src || (slug ? `/employee-photos/${slug}.jpg` : null);
  const showPhoto = Boolean(imageSrc) && !errored;

  const px = `${size}px`;
  const containerStyle = {
    width: px,
    height: px,
    minWidth: px,
    minHeight: px,
    maxWidth: px,
    maxHeight: px,
    fontSize: `${Math.max(10, Math.round(size * 0.38))}px`,
    ...style,
  };

  return (
    <div
      className={`avatar ${className}`.trim()}
      style={containerStyle}
      title={name || ''}
      role="img"
      aria-label={name ? `${name}'s avatar` : 'Avatar'}
    >
      {showPhoto ? (
        <img
          src={imageSrc}
          alt=""
          onError={() => setErrored(true)}
          loading="lazy"
        />
      ) : (
        <span className="avatar-initials">{initials(name)}</span>
      )}
    </div>
  );
}
