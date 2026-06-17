"use strict";
window.currentRoute = function () {
  const h = (location.hash || "#/status").replace(/^#\//, "");
  return ["status", "settings", "logs", "setup"].includes(h) ? h : "status";
};
