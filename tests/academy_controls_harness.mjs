// Project: VirtualGlove
// File: tests/academy_controls_harness.mjs
// Purpose: Exercise the rendered Glove Academy controls in a dependency-free DOM harness.
// Author: Iain Bennett
// Copyright (c) 2026 Iain Bennett
// SPDX-License-Identifier: MIT
// Change log:
//   2026-09-06 - Verify the award replaces lesson content and restart restores it.
//   2026-09-05 - Added complete lesson, restart, camera, calibration, and tuning interaction coverage.
// Full history: docs/CHANGELOG.md and Git history.

import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(0, "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
assert.equal(scripts.length, 5, "expected easter egg, metadata, Academy, tuning, and player scripts");

class FakeClassList {
  constructor() { this.values = new Set(); }
  toggle(name, force) { force ? this.values.add(name) : this.values.delete(name); }
}

class FakeElement {
  constructor(id = "", tagName = "div") {
    this.id = id;
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.options = [];
    this.dataset = {};
    this.style = {};
    this.classList = new FakeClassList();
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.onclick = null;
    this.onchange = null;
    this.oninput = null;
  }
  append(child) {
    this.children.push(child);
    if (this.tagName === "SELECT") {
      if (child.tagName === "OPTGROUP") this.options.push(...child.children);
      else this.options.push(child);
    }
  }
  replaceChildren(...children) { this.children = [...children]; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }
  querySelectorAll(selector) {
    const descendants = [];
    const visit = element => { for (const child of element.children) { descendants.push(child); visit(child); } };
    visit(this);
    if (selector === "input") return descendants.filter(item => item.tagName === "INPUT");
    if (selector === "[data-channel]") return descendants.filter(item => item.dataset.channel);
    return [];
  }
  getContext() {
    return {clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, arc() {}, fill() {}};
  }
}

const elements = new Map();
for (const match of html.matchAll(/<([a-z0-9-]+)[^>]*\sid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/gi)) {
  const [, tag, doubleQuoted, singleQuoted, bare] = match;
  const id = doubleQuoted || singleQuoted || bare;
  elements.set(id, new FakeElement(id, tag));
}
const byId = id => {
  if (!elements.has(id)) elements.set(id, new FakeElement(id));
  return elements.get(id);
};
byId("learn-camera").dataset.src = "/stream";
for (const id of ["achievement", "tune-panel", "tune-thresholds"]) byId(id).hidden = true;

const document = {
  getElementById: byId,
  createElement: tag => new FakeElement("", tag),
};
const window = {addEventListener() {}};
let now = 1000;
let nextTimer = 1;
const timers = new Map();
const setTimeoutFake = (callback, delay = 0) => {
  const id = nextTimer++;
  timers.set(id, {callback, due: now + delay});
  return id;
};
const clearTimeoutFake = id => timers.delete(id);
const advance = async milliseconds => {
  now += milliseconds;
  for (;;) {
    const due = [...timers.entries()].filter(([, timer]) => timer.due <= now).sort((a, b) => a[1].due - b[1].due);
    if (!due.length) break;
    for (const [id, timer] of due) { timers.delete(id); timer.callback(); }
    await Promise.resolve();
  }
};

let sequence = 1;
const baseStatus = () => ({
  sequence: sequence++, detected: true, confidence: .99, calibrated: true,
  vision_state: "active", practice_mode: true, worker_running: true, camera_available: true,
  dpad: {left: false, right: false, up: false, down: false},
  finger_active: {thumb: false, index: false, middle: false, ring: false, pinky: false},
  menu_gesture: {pose: null, recognized: false},
  push_gesture: {active: false, depth: 0, threshold: .34},
  pull_gesture: {active: false, depth: 0, threshold: .34},
  recognition: {roll_left: false, roll_right: false, closed_hand: false, menu_guard: false},
  finger_curls: {}, tuning: {effective: {}}, curl_threshold: .5, hand_landmarks: [],
});
let currentStatus = baseStatus();
let delayedStatus = null;
const requests = [];
const tuningState = {
  active: true, gesture: "index", mode: "gesture", total_phases: 3, completed_phases: 3,
  recording: false, samples: 30, ready: true, stable_ready: true, error: null, revision: 1,
  wizard_step: "problem", problem: null, test: {active: false, cycles: 2, neutral_seconds: 3, passed: true},
  image_quality: {}, diagnostic: {active: false, phase: "idle", index: 0, total: 8, report: null},
  components: ["index"], measurements: {index: .7},
  finger_feedback: {index: {matches: true, expected: "curled"}},
  gestures: {hand_setup: "Set up my hand", start: "Start — Make the V sign", select: "Select — Give a thumbs-up", thumb: "Thumb",
    index: "Index", middle: "Middle", ring: "Ring", pinky: "Pinky", push: "Push", pull: "Pull",
    left: "Left", right: "Right", up: "Up", down: "Down", roll_left: "Roll left", roll_right: "Roll right"},
  effective: {index: {on: .5, off: .35}}, preview: null,
  reach: {available: true, pending: false, custom: true,
    values: {left: .46, right: .21, up: .44, down: .39},
    limits: {left: {min: .05, max: .475}, right: {min: .05, max: .475}, up: {min: .05, max: .475}, down: {min: .05, max: .475}},
    camera_width: 640, camera_height: 480,
    dimensions: {width: 428.8, height: 398.4, aspect: 1.076}},
};
const response = data => ({ok: true, async json() { return structuredClone(data); }});
let playerData={active:'default',generation:0,players:[{id:'default',name:'Player 1'}],progress:{course:1,completed:[],lesson:0},needs_center:false,error:null};
const fetch = async (url, options = {}) => {
  let body = {};
  if (options.body) body = JSON.parse(options.body);
  requests.push({url, body});
  if (url === "/status") {
    if (delayedStatus) return delayedStatus.promise;
    return response(currentStatus);
  }
  if (url === "/api/players") {
    if(body.action==='progress')playerData.progress=structuredClone(body.progress);
    if(body.action==='reset_progress'){playerData.generation++;playerData.progress={course:1,completed:[],lesson:0};}
    return response(playerData);
  }
  if (url === "/api/tuning") {
    tuningState.gesture = body.gesture || tuningState.gesture;
    return response(tuningState);
  }
  return response({});
};

class FakeDate extends Date { static now() { return now; } }
const context = vm.createContext({
  console, document, window, fetch, Date: FakeDate, Math, Number, Object, String, Set,
  JSON, Promise, Error, URL, Blob, structuredClone,
  setTimeout: setTimeoutFake, clearTimeout: clearTimeoutFake, setInterval() { return 0; },
  crypto: {randomUUID: () => "academy-test-session"},
  location: {protocol: "http:", hostname: "localhost"},
  Option: class Option extends FakeElement { constructor(text, value) { super("", "option"); this.textContent = text; this.value = value; } },
  confirm: () => true,
});

vm.runInContext(scripts[0], context, {filename: "rendered-easter-egg.js"});
vm.runInContext(scripts[2], context, {filename: "rendered-academy.js"});
vm.runInContext(scripts[3], context, {filename: "rendered-tuning.js"});
vm.runInContext(scripts[4], context, {filename: "rendered-players.js"});
const settle = async () => { for (let index = 0; index < 8; index++) await Promise.resolve(); };
await settle();

const lesson = () => Number(byId("practice-lessons").dataset.lesson);
assert.equal(lesson(), 1);
assert.equal(byId("previous").disabled, true);

// Every manual navigation click moves exactly once, including Review lessons.
for (let expected = 2; expected <= 16; expected++) {
  byId("next").onclick();
  assert.equal(lesson(), expected);
  assert.equal(byId("practice-lessons").dataset.complete, "false");
}
assert.equal(byId("next").textContent, "Review lessons");
byId("next").onclick();
assert.equal(lesson(), 1);
assert.equal(byId("achievement").hidden, true, "skipping must never award completion");
byId("next").onclick();
byId("previous").onclick();
assert.equal(lesson(), 1);

// A tracker restart may reset its sequence; the Academy must re-arm rather than freeze.
byId("next").onclick();
byId("next").onclick();
// Use a Move Left sample with a reset tracker sequence.
currentStatus = {...baseStatus(), sequence: 0};
currentStatus.dpad.left = true;
await context.update();
await advance(750);
assert.equal(lesson(), 4);
await byId("restart-training").onclick();
await settle();

// A response issued before a click cannot complete or advance the new lesson.
let resolveDelayed;
delayedStatus = {promise: new Promise(resolve => { resolveDelayed = resolve; })};
const staleUpdate = context.update();
byId("next").onclick();
const afterClick = lesson();
resolveDelayed(response({...baseStatus(), detected: true}));
delayedStatus = null;
await staleUpdate;
assert.equal(lesson(), afterClick);
assert.equal(byId("lesson-progress").innerHTML.includes("done"), false);

const passingStatus = number => {
  const state = baseStatus();
  if (number === 3) state.dpad.left = true;
  if (number === 4) state.dpad.right = true;
  if (number === 5) state.dpad.up = true;
  if (number === 6) state.dpad.down = true;
  if (number === 7) state.finger_active.index = true;
  if (number === 8) state.finger_active.thumb = true;
  if (number === 9) state.menu_gesture = {pose: "start", recognized: true};
  if (number === 10) state.menu_gesture = {pose: "select", recognized: true};
  if (number === 11) state.push_gesture.active = true;
  if (number === 12) state.pull_gesture.active = true;
  if (number === 13) state.recognition.roll_left = true;
  if (number === 14) state.recognition.roll_right = true;
  if (number === 15) state.recognition.closed_hand = true;
  if (number === 16) state.recognition.menu_guard = true;
  return state;
};
const completeCurrent = async () => {
  const number = lesson();
  currentStatus = passingStatus(number);
  await context.update();
  if (![3, 4, 5, 6, 9, 10, 11, 12, 13, 14].includes(number)) {
    await advance(650);
    currentStatus = passingStatus(number);
    await context.update();
  }
  await advance(750);
};
const completeCourse = async () => {
  while (byId("practice-lessons").dataset.complete !== "true") await completeCurrent();
};

await byId("restart-training").onclick();
await settle();
await completeCourse();
assert.equal(byId("achievement").hidden, false);
assert.equal(byId("lesson-content").hidden, true, "award must replace the completed lesson");
assert.equal(byId("next").textContent, "Start again");
await byId("restart-training").onclick();
await settle();
assert.equal(lesson(), 1);
assert.equal(byId("achievement").hidden, true);
assert.equal(byId("lesson-progress").innerHTML.includes("done"), false);
assert.equal(byId("lesson-content").hidden, false, "restart must restore lesson content");

await completeCourse();
await byId("next").onclick();
await settle();
assert.equal(lesson(), 1, "lower Start again must reset the course");
assert.equal(byId("achievement").hidden, true);
assert.equal(byId("lesson-progress").innerHTML.includes("done"), false);

// Camera error and recovery are reflected without breaking controls.
currentStatus = {...baseStatus(), vision_state: "error", practice_mode: false, detected: false, camera_available: false};
await context.update();
assert.match(byId("lesson-result").textContent, /Vision unavailable/);
currentStatus = baseStatus();
await context.update();
assert.equal(byId("center").disabled, false);

// Calibration is single-flight even when both UI entry points are used rapidly.
const calibrationsBefore = requests.filter(item => item.url === "/calibrate").length;
byId("center").onclick();
byId("center").onclick();
await settle();
assert.equal(requests.filter(item => item.url === "/calibrate").length, calibrationsBefore + 1);
context.updateCalibration({...baseStatus(), calibrating: true, calibrated: false});
context.updateCalibration({...baseStatus(), calibrating: false, calibrated: true});

// Family wizard and advanced controls all reach mocked APIs without device writes.
byId("tune-switch").checked = true;
await byId("tune-switch").onchange();
await settle();
for (const id of ["problem-setup", "problem-difficult", "problem-accidental", "problem-off-center", "tune-choose", "tune-suggest", "tune-test", "tune-save", "tune-preview", "tune-discard", "tune-reset", "diagnostic-start", "diagnostic-cancel"]) {
  byId(id).onclick();
  await settle();
}
byId("reach-left").value = ".45";
byId("reach-left").oninput();
assert.match(byId("reach-summary").textContent, /pixels/);
byId("reach-save").onclick();
await settle();
byId("reach-reset").onclick();
await settle();
const recordPromise = byId("tune-record").onclick();
await advance(1100);
await advance(1100);
await advance(1100);
await recordPromise;
const diagnosticPromise = byId("diagnostic-record").onclick();
await advance(1100);
await advance(1100);
await advance(1100);
await diagnosticPromise;
byId("tune-calibrate").onclick();
await settle();
context.updateCalibration({...baseStatus(), calibrating: true, calibrated: false});
context.updateCalibration({...baseStatus(), calibrating: false, calibrated: true});
byId("tune-switch").checked = false;
await byId("tune-switch").onchange();
await settle();
const tuningActions = requests.filter(item => item.url === "/api/tuning").map(item => item.body.action);
for (const action of ["begin", "choose_problem", "select", "wizard_record", "suggest", "start_test", "wizard_save", "preview", "wizard_back", "reset", "reach_save", "reach_reset", "diagnostic_begin", "diagnostic_record", "diagnostic_cancel", "end"])
  assert.ok(tuningActions.includes(action), `missing tuning action: ${action}`);

console.log("Glove Academy control harness passed");
