"use strict";

const $ = (sel) => document.querySelector(sel);
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  for (const k of kids) n.append(k);
  return n;
};

let SCHEMA = [];
const inputs = {}; // key -> {field, get(), el, depends_on}

async function api(path, opts) {
  const r = await fetch(path, opts);
  let body = null;
  try { body = await r.json(); } catch { /* no body */ }
  return { ok: r.ok, status: r.status, body };
}

function showErrors(list) {
  const box = $("#errors");
  if (!list || !list.length) { box.classList.add("hidden"); return; }
  box.innerHTML = "";
  box.append(el("strong", {}, "Please fix:"));
  box.append(el("ul", {}, ...list.map((e) => el("li", {}, e))));
  box.classList.remove("hidden");
}

function banner(msg) {
  const b = $("#banner");
  if (!msg) { b.classList.add("hidden"); return; }
  b.textContent = msg;
  b.classList.remove("hidden");
}

// ---- field renderers -------------------------------------------------------
function renderField(field, value) {
  const wrap = el("div", { className: "field" });
  wrap.dataset.key = field.key;
  wrap.append(el("label", {}, field.label));
  let getter;

  if (field.type === "bool") {
    const cb = el("input", { type: "checkbox", checked: !!value });
    wrap.querySelector("label").prepend(cb, " ");
    wrap.querySelector("label").classList.add("toggle");
    getter = () => cb.checked;
    cb.addEventListener("change", updateVisibility);
  } else if (field.type === "enum") {
    const sel = el("select", {}, ...field.options.map((o) =>
      el("option", { value: o, selected: o === value }, o)));
    wrap.append(sel);
    getter = () => sel.value;
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
    const inp = el("input", { type: "password", placeholder: isSet ? "•••••• (set — leave blank to keep)" : "not set" });
    inp.dataset.dirty = "0";
    inp.addEventListener("input", () => (inp.dataset.dirty = "1"));
    wrap.append(inp);
    getter = () => (inp.dataset.dirty === "1" ? { value: inp.value } : null); // null = unchanged
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
  inputs[field.key] = { field, get: getter, el: wrap, depends_on: field.depends_on };
  return wrap;
}

function updateVisibility() {
  for (const { field, el: wrap, depends_on } of Object.values(inputs)) {
    if (!depends_on) continue;
    const ctrl = inputs[depends_on.key];
    const met = ctrl && ctrl.get() === depends_on.value;
    wrap.classList.toggle("hidden", !met);
  }
}

// ---- load / save -----------------------------------------------------------
async function load() {
  const [schema, config] = await Promise.all([api("/api/schema"), api("/api/config")]);
  SCHEMA = schema.body.groups;
  const values = config.body.values;
  const form = $("#config-form");
  form.innerHTML = "";
  for (const group of SCHEMA) {
    const card = el("section", { className: "card" }, el("h2", {}, group.name));
    for (const field of group.fields) card.append(renderField(field, values[field.key]));
    form.append(card);
  }
  updateVisibility();
  showErrors(config.body.errors);
}

async function save() {
  const payload = {};
  for (const { field, get, el: wrap } of Object.values(inputs)) {
    if (wrap.classList.contains("hidden")) continue; // skip dependency-hidden
    const v = get();
    if (v === null) continue;                  // int empty / secret unchanged
    if (field.type === "secret") payload[field.key] = v.value;
    else payload[field.key] = v;
  }
  $("#save-status").textContent = "Saving…";
  const r = await api("/api/config", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!r.ok) {
    $("#save-status").textContent = "Save failed";
    showErrors((r.body && r.body.errors) || ["Save failed"]);
    return;
  }
  $("#save-status").textContent = "Saved";
  showErrors(r.body.warnings);
  banner("Saved. Restart the container to apply changes.");
}

async function runAction(name) {
  const result = $("#action-result");
  if (name === "reverse" && !confirm("Remove ALL managed labels from every Plex item?")) return;
  result.textContent = "Running…";
  const r = await api(`/api/actions/${name}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: name === "reverse" ? JSON.stringify({ confirm: true }) : "{}",
  });
  result.textContent = r.ok ? `${name}: ${JSON.stringify(r.body)}`
                            : `${name} failed (${r.status}): ${JSON.stringify(r.body)}`;
}

document.addEventListener("DOMContentLoaded", () => {
  $("#save-btn").addEventListener("click", save);
  document.querySelectorAll("[data-action]").forEach((b) =>
    b.addEventListener("click", () => runAction(b.dataset.action)));
  load();
});
