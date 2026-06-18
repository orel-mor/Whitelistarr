"use strict";
document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    route: window.currentRoute(),
    version: "",
    status: null,
    toasts: [],
    _guard: null,
    _reverting: false,
    setGuard(fn) { this._guard = fn; },
    async init() {
      window.addEventListener("hashchange", () => {
        const next = window.currentRoute();
        // A page registered a guard (e.g. Settings with unsaved edits) gets to veto
        // the navigation. If it does, snap the hash back to the current route.
        if (!this._reverting && this._guard && next !== this.route && !this._guard(next)) {
          this._reverting = true;
          location.hash = "#/" + this.route;
          return;
        }
        this._reverting = false;
        this.route = next;
      });
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
