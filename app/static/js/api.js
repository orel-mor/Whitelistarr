"use strict";
window.api = async function api(path, opts) {
  const r = await fetch(path, { cache: "no-store", ...opts });
  let body = null;
  try { body = await r.json(); } catch { /* no body */ }
  return { ok: r.ok, status: r.status, body };
};
window.apiPost = (path, data) =>
  window.api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
