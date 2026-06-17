"use strict";
// Pure, DOM-free helpers — shared by the browser app and Node tests. Works as a
// plain <script> (assigns to window) and as a CommonJS module (Node `require`),
// so no build step or bundler is needed.
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else Object.assign(root, api);
})(typeof self !== "undefined" ? self : globalThis, function () {
  const CRON_PRESETS = [
    { label: "Hourly", value: "0 * * * *" },
    { label: "Every 6h", value: "0 */6 * * *" },
    { label: "Every 12h", value: "0 */12 * * *" },
    { label: "Daily", value: "0 3 * * *" },
    { label: "Weekly", value: "0 3 * * 0" },
  ];

  const CRON_HUMAN = {
    "0 * * * *": "every hour",
    "0 */6 * * *": "every 6 hours",
    "0 */12 * * *": "every 12 hours",
    "0 3 * * *": "daily at 03:00",
    "0 3 * * 0": "weekly (Sun 03:00)",
  };

  function cronHuman(expr) {
    return CRON_HUMAN[(expr || "").trim()] || `cron: ${expr || "—"}`;
  }

  function relativeTime(iso) {
    if (!iso) return "never";
    const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.round(secs / 60)}m ago`;
    if (secs < 86400) return `${Math.round(secs / 3600)}h ago`;
    return `${Math.round(secs / 86400)}d ago`;
  }

  function relativeNext(iso) {
    if (!iso) return "—";
    const secs = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
    if (secs <= 0) return "due";
    if (secs < 60) return `in ${secs}s`;
    if (secs < 3600) return `in ${Math.round(secs / 60)}m`;
    if (secs < 86400) return `in ${Math.round(secs / 3600)}h`;
    return `in ${Math.round(secs / 86400)}d`;
  }

  return { CRON_PRESETS, CRON_HUMAN, cronHuman, relativeTime, relativeNext };
});
