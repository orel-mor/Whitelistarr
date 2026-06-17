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

// CRON_PRESETS, CRON_HUMAN, cronHuman, relativeTime, relativeNext come from
// helpers.js (loaded first; assigned to window). Kept DOM-free + Node-testable.

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

  Alpine.data("statusView", () => ({
    data: null, timer: null,
    async start() {
      await this.refresh();
      // Poll, but only fetch while the Status screen is showing and the tab is
      // visible — don't hammer /api/status (and the arr/Plex APIs) off-screen.
      this.timer = setInterval(() => { if (this.active()) this.refresh(); }, 10000);
      document.addEventListener("visibilitychange", () => { if (this.active()) this.refresh(); });
    },
    active() {
      return this.$store.app.route === "status" && !document.hidden;
    },
    async refresh() {
      const r = await api("/api/status");
      if (r.ok) this.data = r.body;
    },
    connList() {
      const c = (this.data && this.data.connections) || {};
      return Object.keys(c).map((name) => ({ name, ...c[name] }));
    },
    labelRows() {
      const m = (this.data && this.data.label_map) || {};
      return Object.keys(m).sort().map((tag) => ({ tag, label: m[tag] }));
    },
    summary(job) {
      const last = this.data && this.data.last && this.data.last[job];
      if (!last) return "never run";
      let n;
      if (job === "sweep") n = `${last.changed} changed`;
      else if (job === "reactive") n = `${last.tag_changes} reacted`;
      else n = `${last.notified} notified`;
      return `${n}, ${relativeTime(last.at)}`;
    },
    recentlyAdded() {
      const last = this.data && this.data.last && this.data.last.reactive;
      if (!last) return "never run";
      const titles = (last.added_titles || []).slice(0, 3).join(", ");
      const what = last.added ? `${last.added} added` : "none";
      return `${what}${titles ? " (" + titles + ")" : ""}, ${relativeTime(last.at)}`;
    },
    async action(name) {
      if (name === "reverse" && !confirm("Remove ALL managed labels from every Plex item?")) return;
      const r = await apiPost(`/api/actions/${name}`, name === "reverse" ? { confirm: true } : {});
      this.$store.app.toast(`${name}: ${r.ok ? JSON.stringify(r.body) : "failed " + r.status}`,
        r.ok ? "ok" : "err");
      this.refresh();
    },
  }));

  Alpine.data("logsView", () => ({
    lines: [], lastId: 0, level: "", auto: true, intervalSec: 3, timer: null,
    async start() {
      await this.tick();
      this.schedule();
      // Reschedule when the user toggles auto-refresh or changes the interval.
      this.$watch("auto", () => this.schedule());
      this.$watch("intervalSec", () => this.schedule());
      document.addEventListener("visibilitychange", () => {
        if (this.active() && this.auto) this.tick();
      });
    },
    active() {
      return this.$store.app.route === "logs" && !document.hidden;
    },
    schedule() {
      clearInterval(this.timer);
      const secs = Math.max(1, Number(this.intervalSec) || 3);
      this.timer = setInterval(() => {
        if (this.active() && this.auto) this.tick();
      }, secs * 1000);
    },
    async tick() {
      const q = `/api/logs?after=${this.lastId}` + (this.level ? `&level=${this.level}` : "");
      const r = await api(q);
      if (!r.ok || !r.body) return;
      if (r.body.lines.length) {
        this.lines.push(...r.body.lines);
        if (this.lines.length > 1000) this.lines.splice(0, this.lines.length - 1000);
        this.lastId = r.body.last_id;
        this.$nextTick(() => this.scrollDown());
      }
    },
    // Level change re-queries from scratch so the filter applies to history too.
    reset() { this.lines = []; this.lastId = 0; this.tick(); },
    clearView() { this.lines = []; },
    scrollDown() { const b = this.$refs.box; if (b) b.scrollTop = b.scrollHeight; },
    logTime(iso) { return (iso || "").replace("T", " ").slice(11, 19); },
  }));

  Alpine.data("plexSignIn", () => ({
    phase: "idle", pinId: null, servers: [], chosen: null, error: "", authUrl: "",
    async start() {
      this.error = ""; this.phase = "pending"; this.authUrl = "";
      const r = await apiPost("/api/plex/pin");
      if (!r.ok) { this.phase = "idle"; this.error = "Could not start sign-in"; return; }
      this.pinId = r.body.id;
      const win = window.open(r.body.authUrl, "plex", "width=600,height=720");
      if (!win) this.authUrl = r.body.authUrl;   // popup blocked -> show link
      this.poll();
    },
    async poll() {
      const r = await api(`/api/plex/pin/${this.pinId}`);
      if (r.body && r.body.authorized) { await this.loadServers(); return; }
      setTimeout(() => this.poll(), 2000);
    },
    async loadServers() {
      const r = await api(`/api/plex/servers?pin_id=${this.pinId}`);
      this.servers = (r.body && r.body.servers) || [];
      this.phase = "pick";
    },
    async apply(uri) {
      const r = await apiPost("/api/plex/apply", { pin_id: this.pinId, uri });
      if (r.ok && r.body.ok !== false) {
        this.phase = "done"; this.chosen = uri; this.$dispatch("plex-connected");
      } else {
        this.error = (r.body && r.body.error) || "Apply failed";
      }
    },
  }));

  Alpine.data("wizard", () => ({
    step: 0, last: 4, steps: ["Welcome", "Plex", "Radarr & Sonarr", "Tags", "Done"],
    radarr: { url: "", key: "", ok: null }, sonarr: { url: "", key: "", ok: null },
    tagMap: "",
    next() { if (this.step < this.last) this.step++; },
    back() { if (this.step > 0) this.step--; },
    async saveArr(which) {
      const f = this[which];
      await apiPost("/api/config", { [`${which}_url`]: f.url, [`${which}_api_key`]: f.key });
      const r = await apiPost(`/api/connections/test/${which}`);
      f.ok = !!(r.body && r.body.ok);
      this.$store.app.toast(`${which}: ${f.ok ? "connected ✓" : "failed ✗"}`, f.ok ? "ok" : "err");
    },
    canLeaveArr() { return this.radarr.ok || this.sonarr.ok; },
    async saveTags() {
      if (!this.tagMap.trim()) { this.$store.app.toast("Add at least one tag → label", "warn"); return; }
      await apiPost("/api/config", { tag_label_map: this.tagMap.trim() });
      this.next();
    },
    finish() { location.hash = "#/status"; this.$store.app.route = "status"; },
  }));
});
