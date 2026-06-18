"use strict";
document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    route: window.currentRoute(),
    version: "",
    status: null,
    toasts: [],
    onboardingComplete: true,   // assume done until /api/status says otherwise
    onboardingStep: 0,          // wizard step to resume on (first incomplete)
    _guard: null,
    _reverting: false,
    setGuard(fn) { this._guard = fn; },
    async init() {
      window.addEventListener("hashchange", () => {
        const next = window.currentRoute();
        // Until onboarding is finished, the wizard is the only reachable screen:
        // snap any other route back to setup.
        if (!this.onboardingComplete && next !== "setup") {
          this._reverting = true;
          location.hash = "#/setup";
          this.route = "setup";
          return;
        }
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
      const ob = s.body && s.body.onboarding;
      if (ob && !ob.complete) {
        this.onboardingComplete = false;
        this.onboardingStep = ob.next_step || 0;
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
