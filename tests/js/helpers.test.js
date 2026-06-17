"use strict";
const test = require("node:test");
const assert = require("node:assert");
const h = require("../../app/static/js/helpers.js");

test("cronHuman maps known presets", () => {
  assert.equal(h.cronHuman("0 * * * *"), "every hour");
  assert.equal(h.cronHuman("0 3 * * *"), "daily at 03:00");
  assert.equal(h.cronHuman("0 3 * * 0"), "weekly (Sun 03:00)");
});

test("cronHuman falls back to the raw expression", () => {
  assert.equal(h.cronHuman("*/7 * * * *"), "cron: */7 * * * *");
  assert.equal(h.cronHuman(""), "cron: —");
});

test("relativeTime formats past timestamps", () => {
  const now = Date.now();
  assert.equal(h.relativeTime(new Date(now - 5000).toISOString()), "5s ago");
  assert.equal(h.relativeTime(new Date(now - 120000).toISOString()), "2m ago");
  assert.equal(h.relativeTime(new Date(now - 7200000).toISOString()), "2h ago");
  assert.equal(h.relativeTime(null), "never");
});

test("relativeNext formats future timestamps", () => {
  const now = Date.now();
  assert.equal(h.relativeNext(new Date(now + 90000).toISOString()), "in 2m");
  assert.equal(h.relativeNext(new Date(now + 7200000).toISOString()), "in 2h");
  assert.equal(h.relativeNext(new Date(now - 1000).toISOString()), "due");
  assert.equal(h.relativeNext(null), "—");
});

test("cron presets cover the documented cadences", () => {
  const values = h.CRON_PRESETS.map((p) => p.value);
  assert.ok(values.includes("0 * * * *"));
  assert.ok(values.includes("0 3 * * 0"));
});
