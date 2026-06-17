"use strict";

// ---- tiny DOM helper -------------------------------------------------------
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  for (const k of kids) if (k != null) n.append(k);
  return n;
};

// key -> {field, get(), wrap, depends_on}. Rebuilt each settings render.
const SETTINGS_INPUTS = {};

// group name -> connection service key (for inline "Test connection").
const SERVICE_OF_GROUP = {
  Plex: "plex", Radarr: "radarr", Sonarr: "sonarr", Seerr: "seerr", Tautulli: "tautulli",
};

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
function cronHuman(expr) { return CRON_HUMAN[(expr || "").trim()] || `cron: ${expr || "—"}`; }

// ---- field renderers -------------------------------------------------------
function renderField(field, value) {
  const wrap = el("div", { className: "field" });
  wrap.dataset.key = field.key;
  wrap.append(el("label", {}, field.label));
  let getter;

  if (field.type === "bool") {
    const cb = el("input", { type: "checkbox", checked: !!value });
    const lbl = wrap.querySelector("label");
    lbl.prepend(cb, " ");
    lbl.classList.add("toggle");
    cb.addEventListener("change", updateSettingsVisibility);
    getter = () => cb.checked;
  } else if (field.type === "enum") {
    const sel = el("select", {}, ...field.options.map((o) =>
      el("option", { value: o, selected: o === value }, o)));
    wrap.append(sel);
    getter = () => sel.value;
  } else if (field.type === "cron") {
    const raw = el("input", { type: "text", value: value == null ? "" : value,
      placeholder: field.placeholder || "0 * * * *" });
    const echo = el("div", { className: "help cron-echo" });
    const sync = () => (echo.textContent = cronHuman(raw.value));
    const customWrap = el("div", { className: "cron-custom hidden" }, raw);
    const chips = el("div", { className: "cron-presets" });
    const setActive = () => {
      const match = CRON_PRESETS.find((p) => p.value === raw.value.trim());
      chips.querySelectorAll(".chip").forEach((c) =>
        c.classList.toggle("active", c.dataset.v === (match ? match.value : "__custom")));
      customWrap.classList.toggle("hidden", !!match);
      sync();
    };
    for (const p of CRON_PRESETS) {
      const chip = el("button", { type: "button", className: "chip", textContent: p.label });
      chip.dataset.v = p.value;
      chip.addEventListener("click", () => { raw.value = p.value; setActive(); });
      chips.append(chip);
    }
    const custom = el("button", { type: "button", className: "chip", textContent: "Custom" });
    custom.dataset.v = "__custom";
    custom.addEventListener("click", () => { customWrap.classList.remove("hidden"); raw.focus(); });
    chips.append(custom);
    raw.addEventListener("input", sync);
    wrap.append(chips, customWrap, echo);
    setActive();
    getter = () => raw.value.trim();
  } else if (field.type === "multi") {
    const chosen = new Set(String(value || "").split(",").map((s) => s.trim()).filter(Boolean));
    const row = el("div", { className: "multi" });
    const boxes = field.options.map((o) => {
      const cb = el("input", { type: "checkbox", checked: chosen.has(o) });
      row.append(el("label", {}, cb, " " + o));
      return [o, cb];
    });
    wrap.append(row);
    getter = () => boxes.filter(([, cb]) => cb.checked).map(([o]) => o).join(",");
  } else if (field.type === "keyvalue") {
    const container = el("div");
    const addRow = (k = "", v = "") => {
      const ki = el("input", { type: "text", placeholder: "tag", value: k });
      const vi = el("input", { type: "text", placeholder: "label", value: v });
      const del = el("button", { type: "button", className: "btn small", textContent: "✕" });
      const r = el("div", { className: "kv-row" }, ki, vi, del);
      del.addEventListener("click", () => r.remove());
      container.append(r);
    };
    String(value || "").split(",").map((s) => s.trim()).filter(Boolean).forEach((pair) => {
      const i = pair.indexOf(":");
      addRow(pair.slice(0, i).trim(), pair.slice(i + 1).trim());
    });
    const add = el("button", { type: "button", className: "btn small", textContent: "+ Add" });
    add.addEventListener("click", () => addRow());
    wrap.append(container, add);
    getter = () => Array.from(container.querySelectorAll(".kv-row")).map((r) => {
      const [ki, vi] = r.querySelectorAll("input");
      return ki.value.trim() && vi.value.trim() ? `${ki.value.trim()}:${vi.value.trim()}` : "";
    }).filter(Boolean).join(",");
  } else if (field.type === "secret") {
    const isSet = value && value.set;
    const inp = el("input", { type: "password",
      placeholder: isSet ? "•••••• (set — leave blank to keep)" : "not set" });
    inp.dataset.dirty = "0";
    inp.addEventListener("input", () => (inp.dataset.dirty = "1"));
    wrap.append(inp);
    getter = () => (inp.dataset.dirty === "1" ? { value: inp.value } : null);
  } else { // text, int, csv
    const inp = el("input", {
      type: field.type === "int" ? "number" : "text",
      value: value == null ? "" : value,
      placeholder: field.placeholder || (field.type === "csv" ? "comma,separated" : ""),
    });
    wrap.append(inp);
    getter = () => (field.type === "int" ? (inp.value === "" ? null : Number(inp.value)) : inp.value);
  }

  if (field.help) wrap.append(el("div", { className: "help" }, field.help));
  SETTINGS_INPUTS[field.key] = { field, get: getter, wrap, depends_on: field.depends_on };
  return wrap;
}

function updateSettingsVisibility() {
  for (const { wrap, depends_on } of Object.values(SETTINGS_INPUTS)) {
    if (!depends_on) continue;
    const ctrl = SETTINGS_INPUTS[depends_on.key];
    const met = ctrl && ctrl.get() === depends_on.value;
    wrap.classList.toggle("hidden", !met);
  }
}

function renderSettingsForm(cmp) {
  for (const k of Object.keys(SETTINGS_INPUTS)) delete SETTINGS_INPUTS[k];
  const core = cmp.$refs.core, adv = cmp.$refs.adv;
  core.innerHTML = ""; adv.innerHTML = "";
  for (const group of cmp.groups) {
    const card = el("section", { className: "group" }, el("h2", {}, group.name));
    for (const field of group.fields) card.append(renderField(field, cmp.values[field.key]));
    const service = SERVICE_OF_GROUP[group.name];
    if (service) {
      const test = el("button", { type: "button", className: "btn small", textContent: "Test connection" });
      test.addEventListener("click", () => cmp.testConn(service));
      card.append(test);
    }
    (group.tier === "advanced" ? adv : core).append(card);
  }
  updateSettingsVisibility();
}

function collectSettingsPayload() {
  const payload = {};
  for (const { field, get, wrap } of Object.values(SETTINGS_INPUTS)) {
    if (wrap.classList.contains("hidden")) continue;        // depends_on hidden
    const v = get();
    if (v === null) continue;                               // int empty / secret unchanged
    payload[field.key] = field.type === "secret" ? v.value : v;
  }
  return payload;
}

// ---- Alpine components -----------------------------------------------------
document.addEventListener("alpine:init", () => {
  Alpine.data("settings", () => ({
    groups: [], values: {}, showAdvanced: false, saving: false,
    async load() {
      const [schema, config] = await Promise.all([api("/api/schema"), api("/api/config")]);
      this.groups = schema.body.groups;
      this.values = config.body.values;
      this.$nextTick(() => renderSettingsForm(this));
    },
    async save() {
      this.saving = true;
      const r = await apiPost("/api/config", collectSettingsPayload());
      this.saving = false;
      if (!r.ok) {
        this.$store.app.toast(((r.body && r.body.errors) || ["Save failed"]).join("; "), "err");
        return;
      }
      const b = r.body;
      if (!b.ok) this.$store.app.toast("Could not apply: " + (b.error || "unknown"), "err");
      else if (b.restart_fields && b.restart_fields.length)
        this.$store.app.toast("Saved. Restart required for: " + b.restart_fields.join(", "), "warn");
      else this.$store.app.toast("Applied ✓ — no restart needed", "ok");
      if (b.warnings && b.warnings.length) this.$store.app.toast(b.warnings.join("; "), "warn");
    },
    async testConn(service) {
      const r = await apiPost(`/api/connections/test/${service}`);
      const d = r.body || {};
      this.$store.app.toast(`${service}: ${d.ok ? "connected ✓ " : "failed ✗ "}${d.detail || ""}`,
        d.ok ? "ok" : "err");
    },
  }));

  Alpine.data("statusView", () => ({ start() {} }));
  Alpine.data("wizard", () => ({}));
});
