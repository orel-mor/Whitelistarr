"use strict";

// ---- tiny DOM helper -------------------------------------------------------
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  for (const k of kids) if (k != null) n.append(k);
  return n;
};

// key -> {field, get(), wrap, depends_on}. Rebuilt each settings render.
const SETTINGS_INPUTS = {};

// Plex libraries fetched live for the "libraries" field type, plus the re-render
// closures that rebuild those checkbox sets when a fresh list arrives.
let PLEX_LIBRARIES = [];
const LIBRARY_RERENDERERS = [];

// Per-browser view preferences (which sections are expanded) so the Settings page
// reopens the way the user last saved it. Pure UI — never sent to the server.
const UI_PREFS_KEY = "wl.settings.ui";
function loadUiPref(key, dflt) {
  try {
    const o = JSON.parse(localStorage.getItem(UI_PREFS_KEY) || "{}");
    return key in o ? o[key] : dflt;
  } catch { return dflt; }
}
function saveUiPref(key, value) {
  try {
    const o = JSON.parse(localStorage.getItem(UI_PREFS_KEY) || "{}");
    o[key] = value;
    localStorage.setItem(UI_PREFS_KEY, JSON.stringify(o));
  } catch { /* storage disabled — view state just won't persist */ }
}

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
  } else if (field.type === "libraries") {
    // Dynamic checkbox set: options come from PLEX_LIBRARIES (fetched live from the
    // connected server). A saved pick whose library isn't currently listed (server
    // offline, renamed) is still shown so it isn't silently dropped. Empty = all.
    const selected = new Set(String(value || "").split(",").map((s) => s.trim()).filter(Boolean));
    const row = el("div", { className: "multi" });
    const render = () => {
      row.innerHTML = "";
      const titles = PLEX_LIBRARIES.map((l) => l.title);
      for (const t of selected) if (!titles.includes(t)) titles.push(t);
      if (!titles.length) {
        row.append(el("p", { className: "help muted", textContent:
          "Sign in to Plex, then Test connection to list libraries." }));
        return;
      }
      for (const t of titles) {
        const cb = el("input", { type: "checkbox", checked: selected.has(t) });
        cb.addEventListener("change", () => (cb.checked ? selected.add(t) : selected.delete(t)));
        row.append(el("label", {}, cb, " " + t));
      }
    };
    render();
    LIBRARY_RERENDERERS.push(render);
    wrap.append(row);
    getter = () => Array.from(selected).join(",");
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
  } else if (field.type === "lines") {
    // Newline-separated list (e.g. Apprise URLs). Stored as a CSV string, but
    // edited one-per-line so long tokenized URLs stay readable.
    const ta = el("textarea", { rows: 4,
      placeholder: field.placeholder || "one per line" });
    ta.value = String(value || "").split(",").map((s) => s.trim()).filter(Boolean).join("\n");
    wrap.append(ta);
    getter = () => ta.value.split("\n").map((s) => s.trim()).filter(Boolean).join(",");
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

// tier -> the $refs container it renders into. "hidden" groups (feature_notify)
// aren't rendered as cards; their fields are surfaced elsewhere (section toggle).
const TIER_REF = { core: "core", notify: "notify", advanced: "adv" };

function renderSettingsForm(cmp) {
  for (const k of Object.keys(SETTINGS_INPUTS)) delete SETTINGS_INPUTS[k];
  LIBRARY_RERENDERERS.length = 0;
  const refs = { core: cmp.$refs.core, notify: cmp.$refs.notify, adv: cmp.$refs.adv };
  for (const c of Object.values(refs)) c.innerHTML = "";

  for (const group of cmp.groups) {
    const refName = TIER_REF[group.tier];
    if (!refName) continue; // hidden tier (e.g. the notify toggle field)
    const card = el("section", { className: "group" }, el("h2", {}, group.name));
    for (const field of group.fields) card.append(renderField(field, cmp.values[field.key]));
    const service = SERVICE_OF_GROUP[group.name];
    if (service) {
      const test = el("button", { type: "button", className: "btn small", textContent: "Test connection" });
      test.addEventListener("click", () => cmp.testConn(service));
      card.append(test);
    }
    refs[refName].append(card);
  }

  // feature_notify is the Notifications section's enable toggle (a checkbox in the
  // section header bound to cmp.notifyEnabled) rather than a rendered field — but
  // it still needs to be collected on save, so register a synthetic input for it.
  const flag = el("div"); // never carries the "hidden" class -> always collected
  SETTINGS_INPUTS["feature_notify"] = {
    field: { key: "feature_notify", type: "bool" },
    get: () => !!cmp.notifyEnabled,
    wrap: flag,
    depends_on: null,
  };

  // Any edit anywhere in the form marks the page dirty (best-effort live hint; the
  // navigation guard re-checks against the saved baseline regardless).
  for (const c of Object.values(refs)) {
    c.addEventListener("input", () => cmp.markDirty());
    c.addEventListener("change", () => cmp.markDirty());
    c.addEventListener("click", () => cmp.$nextTick(() => cmp.markDirty()));
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
    groups: [], values: {}, showAdvanced: false, notifyEnabled: false,
    saving: false, dirty: false, _baseline: "",
    async load() {
      const [schema, config] = await Promise.all([api("/api/schema"), api("/api/config")]);
      this.groups = schema.body.groups;
      this.values = config.body.values;
      this.notifyEnabled = !!this.values.feature_notify;
      // Restore the last-saved view state so the page looks how the user left it.
      this.showAdvanced = loadUiPref("showAdvanced", false);
      this.$nextTick(() => {
        renderSettingsForm(this);
        this.captureBaseline();
        this.registerGuard();
        this.refreshLibraries();  // populate the Plex library checkboxes on entry
      });
    },
    async refreshLibraries() {
      // Pull the live library list and rebuild every "libraries" checkbox set.
      // Called on tab entry, after a Plex test/connect — keeps the picker current.
      const r = await api("/api/plex/libraries");
      PLEX_LIBRARIES = (r.body && r.body.libraries) || [];
      LIBRARY_RERENDERERS.forEach((fn) => fn());
    },
    onPlexConnected() {
      // A sign-in or disconnect inside the Plex group changed Plex creds; refresh
      // the library list to match the now-connected (or cleared) server.
      this.refreshLibraries();
    },
    captureBaseline() {
      this._baseline = JSON.stringify(collectSettingsPayload());
      this.dirty = false;
    },
    isDirty() {
      try { return JSON.stringify(collectSettingsPayload()) !== this._baseline; }
      catch { return false; }
    },
    markDirty() { this.dirty = this.isDirty(); },
    onToggle() { this.markDirty(); },
    registerGuard() {
      // Block navigation away from a dirty Settings page until the user chooses to
      // discard (reverting to the saved state) or stay.
      this.$store.app.setGuard((next) => {
        if (next === "settings" || !this.isDirty()) return true;
        if (confirm("You have unsaved changes. Discard them and leave this page?")) {
          this.revert();
          return true;
        }
        return false;
      });
    },
    async revert() {
      // Re-fetch the saved config and re-render, so changes are truly reverted
      // (not just visually reset) and view state returns to the last save.
      await this.load();
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
      // Persist view state and reset the dirty baseline to the just-saved values.
      saveUiPref("showAdvanced", this.showAdvanced);
      this.captureBaseline();
    },
    _fieldVal(key) {
      const ui = SETTINGS_INPUTS[key];
      const v = ui && ui.get();
      return typeof v === "string" ? v.trim() : "";
    },
    _secretVal(key) {
      const ui = SETTINGS_INPUTS[key];
      const v = ui && ui.get();             // secret getter: null | {value}
      return v && typeof v === "object" ? String(v.value || "").trim() : "";
    },
    async testConn(service) {
      // Probe the values typed into the form so a connection can be verified before
      // saving. When the key field is untouched, the server falls back to the saved
      // credentials for that service.
      const body = {};
      const url = this._fieldVal(`${service}_url`);
      const key = this._secretVal(`${service}_api_key`);
      // Plex isn't probed from a URL/key pair (it uses the sign-in flow), so only
      // arr/seerr/tautulli send their typed credentials; the server probes the
      // saved component otherwise.
      if (url) body.url = url;
      if (key) body.api_key = key;
      const r = await apiPost(`/api/connections/test/${service}`, body);
      const d = r.body || {};
      this.$store.app.toast(`${service}: ${d.ok ? "connected ✓ " : "failed ✗ "}${d.detail || ""}`,
        d.ok ? "ok" : "err");
      // A successful Plex probe means the library list may now be reachable.
      if (service === "plex" && d.ok) this.refreshLibraries();
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
    histList() {
      return (this.data && this.data.history) || [];
    },
    actionTitle(action) {
      return ({
        sweep: "Sweep", reverse: "Reverse", reactive: "Reactive poll",
        watch_scan: "Watch scan", "test-notification": "Test notification",
      })[action] || action;
    },
    formatResult(e) {
      if (e.action === "sweep" || e.action === "reverse")
        return `${e.changed} changed of ${e.processed}`;
      if (e.action === "reactive") {
        const titles = (e.added_titles || []).slice(0, 3).join(", ");
        return `${e.tag_changes} tag change(s), ${e.added} added` + (titles ? ` (${titles})` : "");
      }
      if (e.action === "watch_scan") return `${e.notified} notified of ${e.processed}`;
      if (e.action === "test-notification") return e.ok ? "sent" : "failed";
      return "";
    },
  }));

  Alpine.data("actionsView", () => ({
    busy: false,
    async action(name) {
      if (name === "reverse" && !confirm("Remove ALL managed labels from every Plex item?")) return;
      this.busy = true;
      const r = await apiPost(`/api/actions/${name}`, name === "reverse" ? { confirm: true } : {});
      this.busy = false;
      this.$store.app.toast(`${name}: ${r.ok ? JSON.stringify(r.body) : "failed " + r.status}`,
        r.ok ? "ok" : "err");
    },
  }));

  Alpine.data("logsView", () => ({
    // Portainer-style: each refresh fetches the last `tailN` lines and replaces the
    // view. Bigger tailN = more history shown (bounded by the in-memory buffer).
    lines: [], level: "", auto: true, intervalSec: 3, tailN: 1000, timer: null,
    async start() {
      await this.tick();
      this.schedule();
      this.$watch("auto", () => this.schedule());
      this.$watch("intervalSec", () => this.schedule());
      this.$watch("tailN", () => this.tick());
      this.$watch("level", () => this.tick());
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
      const n = Math.max(1, Number(this.tailN) || 1000);
      const q = `/api/logs?tail=${n}` + (this.level ? `&level=${this.level}` : "");
      const r = await api(q);
      if (!r.ok || !r.body) return;
      this.lines = r.body.lines;
      this.$nextTick(() => this.scrollDown());
    },
    scrollDown() { const b = this.$refs.box; if (b) b.scrollTop = b.scrollHeight; },
    logTime(iso) { return (iso || "").replace("T", " ").slice(11, 19); },
  }));

  Alpine.data("plexSignIn", (opts = {}) => ({
    // withLibraries: after connecting, show an inline library picker (onboarding)
    // instead of finishing immediately. Settings uses the standalone picker instead.
    withLibraries: !!opts.withLibraries,
    phase: "idle", pinId: null, servers: [], chosen: null, error: "", authUrl: "",
    applying: false, user: "", libraries: [], libSel: {},
    _win: null,
    async checkConnected() {
      // Settings: if Plex is already connected, show "Connected — <user>" + a
      // Disconnect button instead of the sign-in button.
      const r = await api("/api/plex/account");
      if (r.ok && r.body && r.body.connected) {
        this.phase = "connected"; this.user = r.body.username || "";
      }
    },
    async start() {
      this.error = ""; this.phase = "pending"; this.authUrl = "";
      const r = await apiPost("/api/plex/pin");
      if (!r.ok) { this.phase = "idle"; this.error = "Could not start sign-in"; return; }
      this.pinId = r.body.id;
      this._win = window.open(r.body.authUrl, "plex", "width=600,height=720");
      if (!this._win) this.authUrl = r.body.authUrl;   // popup blocked -> show link
      this.poll();
    },
    closePopup() {
      // Plex's post-login page doesn't self-close, so close the popup ourselves
      // once we've seen the PIN authorized.
      if (this._win && !this._win.closed) { try { this._win.close(); } catch { /* cross-origin */ } }
      this._win = null;
    },
    async poll() {
      const r = await api(`/api/plex/pin/${this.pinId}`);
      if (r.body && r.body.authorized) { this.closePopup(); await this.loadServers(); return; }
      setTimeout(() => this.poll(), 2000);
    },
    async loadServers() {
      const r = await api(`/api/plex/servers?pin_id=${this.pinId}`);
      this.servers = (r.body && r.body.servers) || [];
      this.phase = "pick";
    },
    async apply(uri) {
      if (this.applying) return;            // ignore double-clicks while connecting
      this.error = ""; this.chosen = uri; this.applying = true;
      const r = await apiPost("/api/plex/apply", { pin_id: this.pinId, uri });
      if (r.ok && r.body.ok !== false) {
        if (this.withLibraries) { await this.loadLibraries(); this.applying = false; }
        else { this.phase = "done"; this.$dispatch("plex-connected"); }
      } else {
        this.applying = false; this.chosen = null;
        this.error = (r.body && r.body.error) || "Apply failed";
      }
    },
    async loadLibraries() {
      const r = await api("/api/plex/libraries");
      this.libraries = (r.body && r.body.libraries) || [];
      this.libSel = {};
      this.libraries.forEach((l) => (this.libSel[l.title] = true));  // default: all checked
      this.phase = "libraries";
    },
    async saveLibraries() {
      // All checked (or nothing to pick) keeps the "all libraries" default (empty);
      // otherwise persist the chosen titles so the unchecked ones are excluded.
      const chosen = this.libraries.filter((l) => this.libSel[l.title]).map((l) => l.title);
      const all = chosen.length === this.libraries.length;
      await apiPost("/api/config", { plex_sections: all ? "" : chosen.join(",") });
      this.phase = "done"; this.$dispatch("plex-connected");
    },
    async disconnect() {
      if (!confirm("Disconnect Plex? Whitelistarr will stop syncing until you sign in again.")) return;
      await apiPost("/api/plex/disconnect", {});
      this.phase = "idle"; this.user = ""; this.chosen = null;
      this.$dispatch("plex-connected");  // let Settings refresh its library picker
    },
  }));

  Alpine.data("wizard", () => ({
    step: 0, last: 5,
    steps: ["Welcome", "Plex", "Radarr & Sonarr", "Tags", "Notifications", "Done"],
    radarr: { url: "", key: "", ok: null }, sonarr: { url: "", key: "", ok: null },
    tagRows: [{ tag: "", label: "" }],
    notify: { enabled: false, tautulliUrl: "", tautulliKey: "", tautulliOk: null,
              seerrUrl: "", seerrKey: "", seerrOk: null, apprise: "" },
    next() { if (this.step < this.last) this.step++; },
    back() { if (this.step > 0) this.step--; },
    async saveArr(which) {
      const f = this[which];
      await apiPost("/api/config", { [`${which}_url`]: f.url, [`${which}_api_key`]: f.key });
      const r = await apiPost(`/api/connections/test/${which}`,
        { url: f.url, api_key: f.key });
      f.ok = !!(r.body && r.body.ok);
      this.$store.app.toast(`${which}: ${f.ok ? "connected ✓" : "failed ✗"}`, f.ok ? "ok" : "err");
    },
    canLeaveArr() { return this.radarr.ok || this.sonarr.ok; },
    async testNotifyConn(which) {
      // Save the typed creds, then probe — mirrors saveArr so the user can verify
      // Tautulli/Seerr before leaving the Notifications step.
      const f = which === "tautulli"
        ? { url: this.notify.tautulliUrl, key: this.notify.tautulliKey }
        : { url: this.notify.seerrUrl, key: this.notify.seerrKey };
      await apiPost("/api/config", { [`${which}_url`]: f.url, [`${which}_api_key`]: f.key });
      const r = await apiPost(`/api/connections/test/${which}`, { url: f.url, api_key: f.key });
      const ok = !!(r.body && r.body.ok);
      this.notify[`${which}Ok`] = ok;
      this.$store.app.toast(`${which}: ${ok ? "connected ✓" : "failed ✗"}`, ok ? "ok" : "err");
    },
    addTagRow() { this.tagRows.push({ tag: "", label: "" }); },
    removeTagRow(i) { this.tagRows.splice(i, 1); if (!this.tagRows.length) this.addTagRow(); },
    _tagMap() {
      return this.tagRows
        .map((r) => [r.tag.trim(), r.label.trim()])
        .filter(([t, l]) => t && l)
        .map(([t, l]) => `${t}:${l}`)
        .join(",");
    },
    async saveTags() {
      const map = this._tagMap();
      if (!map) { this.$store.app.toast("Add at least one tag → label", "warn"); return; }
      await apiPost("/api/config", { tag_label_map: map });
      this.next();
    },
    async saveNotify() {
      const n = this.notify;
      if (!n.enabled) { await apiPost("/api/config", { feature_notify: false }); this.next(); return; }
      await apiPost("/api/config", {
        feature_notify: true,
        tautulli_url: n.tautulliUrl.trim(), tautulli_api_key: n.tautulliKey.trim(),
        seerr_url: n.seerrUrl.trim(), seerr_api_key: n.seerrKey.trim(),
        apprise_urls: n.apprise.split("\n").map((s) => s.trim()).filter(Boolean).join(","),
      });
      this.next();
    },
    skipNotify() { this.next(); },
    finish() { location.hash = "#/status"; this.$store.app.route = "status"; },
  }));
});
