"use strict";
document.addEventListener("alpine:init", () => {
  Alpine.data("statusView", () => ({ start() {} }));
  Alpine.data("settings", () => ({ load() {} }));
  Alpine.data("wizard", () => ({}));
});
