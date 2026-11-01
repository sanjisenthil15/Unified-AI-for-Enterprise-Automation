/**
 * utils/passwordPolicy.js
 *
 * Client-side mirror of the backend password policy
 * (backend/core/security.py validate_password_policy) for instant feedback.
 * The backend remains the authority — this only saves a round trip.
 */

export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_BYTES = 72;

/** UTF-8 byte length (matches Python's len(s.encode("utf-8"))), computed
 * per code point so it works without TextEncoder. */
export function utf8ByteLength(value) {
  let bytes = 0;
  for (const ch of value || '') {
    const cp = ch.codePointAt(0);
    bytes += cp <= 0x7f ? 1 : cp <= 0x7ff ? 2 : cp <= 0xffff ? 3 : 4;
  }
  return bytes;
}

/** Each rule: { key, label, ok } — rendered as a live checklist. */
export function passwordRules(password) {
  const pw = password || '';
  return [
    { key: 'length', label: `At least ${PASSWORD_MIN_LENGTH} characters`, ok: pw.length >= PASSWORD_MIN_LENGTH },
    { key: 'upper', label: 'One uppercase letter', ok: /[A-Z]/.test(pw) || [...pw].some((c) => c !== c.toLowerCase()) },
    { key: 'digit', label: 'One number', ok: /\d/.test(pw) },
    { key: 'bytes', label: `No longer than ${PASSWORD_MAX_BYTES} bytes`, ok: utf8ByteLength(pw) <= PASSWORD_MAX_BYTES },
  ];
}

export function isPasswordValid(password) {
  return passwordRules(password).every((r) => r.ok);
}

/** Turns a FastAPI error (string detail, 422 list, or {code,message}) into one readable message. */
export function apiErrorText(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => String(d.msg || '').replace(/^Value error,\s*/i, '')).join(' ');
  }
  if (detail && typeof detail === 'object' && detail.message) return detail.message;
  return fallback;
}
