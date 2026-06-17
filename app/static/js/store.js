"use strict";
document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    route: window.currentRoute(),
    version: "",
    status: null,
    toasts: [],
    async init() {
      window.addEventListener("hashchange", () => (this.route = window.currentRoute()));
      const h = await window.api("/health");
      this.version = h.body ? "v" + h.body.version : "";
      const s = await window.api("/api/status");
      if (s.body && !s.body.configured) {
        location.hash = "#/setup";
        this.route = "setup";
      }
    },
    toast(msg, kind = "ok") {
      const id = Date.now() + Math.random();
      this.toasts.push({ id, msg, kind });
      setTimeout(() => (this.toasts = this.toasts.filter((t) => t.id !== id)), 4000);
    },
  });
});
