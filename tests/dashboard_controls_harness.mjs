// Exercise every rendered Dashboard control and its important recovery paths.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(0, "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
assert.equal(scripts.length, 4, "expected shared, metadata, Dashboard, and player scripts");

class FakeClassList { toggle() {} }
class FakeElement {
  constructor(id = "", tagName = "div") {
    this.id = id; this.tagName = tagName.toUpperCase(); this.hidden = false;
    this.disabled = false; this.checked = false; this.value = ""; this.textContent = "";
    this.innerHTML = ""; this.style = {}; this.dataset = {}; this.className = "";
    this.classList = new FakeClassList(); this.attributes = new Map(); this.children = [];
    this.options = []; this.onclick = null; this.onchange = null; this.onload = null;
    this.onerror = null; this.srcAssignments = 0;
  }
  set src(value) { this.attributes.set("src", String(value)); this.srcAssignments++; }
  get src() { return this.attributes.get("src") || ""; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }
}

const elements = new Map();
for (const match of html.matchAll(/<([a-z0-9-]+)[^>]*\sid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/gi)) {
  const id = match[2] || match[3] || match[4];
  elements.set(id, new FakeElement(id, match[1]));
}
const get = id => {
  if (!elements.has(id)) elements.set(id, new FakeElement(id));
  return elements.get(id);
};
get("camera").dataset.src = "/stream";

let now = 1000;
class FakeDate extends Date { static now() { return now; } }
const listeners = new Map();
const storage = new Map();
const calls = [];
const alerts = [];
let confirmAnswer = false;
let profileReply = "confirmed";
let controllerReply = "delivered";
let shutdownReply = "success";
let failGames = false;
let failStatus = false;
let calibrationDeferred = null;
let playerState = {
  active: "iain", generation: 1, players: [{id: "iain", name: "Iain"}, {id: "scott", name: "Scott"}],
  progress: {course: 1, completed: [], lesson: 0}, needs_center: false, error: null,
};
const status = {
  vision_state: "active", worker_running: true, camera_available: true, detected: true,
  confidence: .9, active_profile: "program_1", configured_profile: "program_1",
  profile_source: "Dashboard", game: "", game_session_active: false,
  connection_configured: true, controller_enabled: false, controller_context_active: false,
  controller_request_pending: false, calibrated: true, receiver_available: true,
  player: playerState, rapid_fire: {a: false, b: false, default_a: false, default_b: false},
};
const response = (data = {}, ok = true) => ({ok, async json() { return structuredClone(data); }});
async function fetch(path, options = {}) {
  const body = options.body ? JSON.parse(options.body) : {};
  calls.push({path, body, options});
  if (path.startsWith("/status")) {
    if (failStatus) throw Error("offline");
    return response(status);
  }
  if (path === "/api/practice") return response({});
  if (path === "/api/players") {
    if (body.action === "select") {
      playerState = {...playerState, active: body.id, generation: playerState.generation + 1};
      status.player = playerState;
    }
    return response(playerState);
  }
  if (path === "/calibrate") {
    if (calibrationDeferred) return calibrationDeferred.promise;
    return response({});
  }
  if (path === "/api/profile") {
    if (profileReply === "failure") return response({error: "Profile service unavailable."}, false);
    return response({active_profile: profileReply === "confirmed" ? body.profile : status.active_profile});
  }
  if (path === "/api/controller") {
    if (controllerReply === "failure") return response({error: "Controller request failed."}, false);
    return response({controller_enabled: body.enabled, pending: controllerReply === "pending"});
  }
  if (path === "/api/system/shutdown") {
    if (shutdownReply === "failure") return response({error: "Shutdown helper unavailable."}, false);
    return response({accepted: true});
  }
  if (path === "/api/games") {
    if (failGames) return response({error: "Registry service unavailable."}, false);
    return response({document: JSON.stringify({games: {"Super Mario Bros. (USA).nes": "program_12"}}), revision: "one"});
  }
  if (path === "/api/rapid-fire") return response({accepted: true});
  return response({});
}

const document = {hidden: false, getElementById: get, createElement: tag => new FakeElement("", tag)};
const window = {
  addEventListener(name, callback) {
    if (!listeners.has(name)) listeners.set(name, []);
    listeners.get(name).push(callback);
  },
  dispatchEvent(event) { for (const callback of listeners.get(event.type) || []) callback(event); },
  updateEasterEgg() {},
};
const context = vm.createContext({
  console, document, window, fetch, Date: FakeDate, Math, Number, Object, String, JSON,
  Promise, Error, Set, structuredClone, Event: class { constructor(type) { this.type = type; } },
  Option: class Option extends FakeElement { constructor(text, value) { super("", "option"); this.textContent = text; this.value = value; } },
  localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value)},
  setInterval() { return 0; }, setTimeout(callback) { callback(); return 0; }, clearTimeout() {},
  confirm: () => confirmAnswer, alert: message => alerts.push(message),
});
for (const [index, script] of scripts.entries()) vm.runInContext(script, context, {filename: `dashboard-${index}.js`});
const settle = async () => { for (let index = 0; index < 10; index++) await Promise.resolve(); };
await settle();
await context.update();
await settle();

const expectedButtons = ["center", "controller-toggle", "shutdown-system", "rapid-save", "rapid-defaults"];
const renderedButtons = [...html.matchAll(/<button\b[^>]*\bid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/gi)]
  .map(match => match[1] || match[2] || match[3]).sort();
assert.deepEqual(renderedButtons, [...expectedButtons].sort(), "rendered Dashboard button inventory changed");
for (const id of expectedButtons) assert.equal(typeof get(id).onclick, "function", `${id} has no click handler`);
for (const id of ["player-select", "profile-selector", "show-statistics", "rapid-a", "rapid-b"])
  assert.equal(typeof get(id).onchange, "function", `${id} has no change handler`);
for (const href of ["/setup", "/help/gameplay"])
  assert.match(html, new RegExp(`href=(?:["']?)${href.replace("/", "\\/")}`), `missing ${href} link`);
assert.ok(calls.some(call => call.path === "/api/practice" && call.body.reset && call.body.enabled === false),
  "Dashboard did not clear practice mode on entry");

// Centring is single-flight and recovers from completion.
let resolveCalibration;
calibrationDeferred = {promise: new Promise(resolve => { resolveCalibration = resolve; })};
const calibrationsBefore = calls.filter(call => call.path === "/calibrate").length;
const firstCenter = get("center").onclick();
get("center").onclick();
assert.equal(calls.filter(call => call.path === "/calibrate").length, calibrationsBefore + 1);
resolveCalibration(response({}));
await firstCenter;
calibrationDeferred = null;

// Confirmed, failed, and unconfirmed profile changes all release the selector.
get("profile-selector").value = "program_2";
profileReply = "confirmed";
await get("profile-selector").onchange();
assert.equal(get("profile-selector").disabled, false);
get("profile-selector").value = "program_3";
profileReply = "failure";
await get("profile-selector").onchange();
assert.equal(get("profile-selector").disabled, false);
assert.match(get("dashboard-notice").textContent, /Profile service unavailable/);
get("profile-selector").value = "program_4";
profileReply = "unconfirmed";
await get("profile-selector").onchange();
assert.equal(get("profile-selector").disabled, true);
now += 10001;
await context.update();
assert.equal(get("profile-selector").disabled, false);
assert.match(get("dashboard-notice").textContent, /not confirmed/);

// Controller requests report pending delivery and recover after failure.
controllerReply = "pending";
await get("controller-toggle").onclick();
assert.match(get("dashboard-notice").textContent, /Waiting for the tracker/);
controllerReply = "failure";
await get("controller-toggle").onclick();
assert.equal(get("controller-toggle").disabled, false);
assert.match(get("dashboard-notice").textContent, /Controller request failed/);

// Player and statistics controls reach their maintained handlers.
get("player-select").value = "scott";
await get("player-select").onchange();
assert.equal(playerState.active, "scott");
get("show-statistics").checked = true;
get("show-statistics").onchange();
assert.equal(storage.get("virtualglove.showStatistics"), "true");

// Stream failures retry no faster than once per second.
const image = get("camera");
image.onerror();
const assignments = image.srcAssignments;
context.cameraDisplay(status, false, false);
context.cameraDisplay(status, false, false);
assert.equal(image.srcAssignments, assignments);
now += 1000;
context.cameraDisplay(status, false, false);
assert.equal(image.srcAssignments, assignments + 1);

// A registry outage remains visible and is not hammered on every status poll.
status.game = "Super Mario Bros. (USA).nes";
status.game_session_active = true;
failGames = true;
await context.update();
await settle();
assert.match(get("rapid-notice").textContent, /Registry service unavailable.*Retrying/);
const failedReads = calls.filter(call => call.path === "/api/games").length;
await context.update();
await settle();
assert.equal(calls.filter(call => call.path === "/api/games").length, failedReads);

// Shutdown cancellation is inert; failure restores its button; success locks it.
confirmAnswer = false;
await get("shutdown-system").onclick();
const shutdownsBefore = calls.filter(call => call.path === "/api/system/shutdown").length;
assert.equal(shutdownsBefore, 0);
confirmAnswer = true;
shutdownReply = "failure";
await get("shutdown-system").onclick();
assert.equal(get("shutdown-system").disabled, false);
assert.match(alerts.at(-1), /Shutdown helper unavailable/);
shutdownReply = "success";
await get("shutdown-system").onclick();
assert.equal(get("shutdown-system").disabled, true);
assert.equal(get("system").textContent, "Shutting down safely");

failStatus = true;
await context.update();
assert.equal(get("system").textContent, "Dashboard disconnected");

console.log("Dashboard control harness passed");
