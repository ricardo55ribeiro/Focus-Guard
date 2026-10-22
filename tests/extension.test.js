const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const extensionDir = path.join(__dirname, "../extension");
const background = readFileSync(path.join(extensionDir, "background.js"), "utf8");

function browserHarness(url = "https://example.org/study") {
  const requests = [];
  const updates = [];
  const storage = {};
  const tab = { id: 7, url, title: "Study" };
  const event = () => ({ addListener() {} });
  const context = vm.createContext({
    fetch: async (address, options) => {
      requests.push({ address, options });
      return { json: async () => ({ action: "block", reason: "test" }) };
    },
    chrome: {
      tabs: {
        query: (_, callback) => callback([tab]),
        update: (id, data) => updates.push({ id, data }),
        onActivated: event(),
        onUpdated: event(),
      },
      runtime: {
        onInstalled: event(),
        getURL: (file) => `chrome-extension://test/${file}`,
      },
      storage: { local: { set: (data, callback) => { Object.assign(storage, data); callback(); } } },
    },
  });
  vm.runInContext(background, context);
  return { requests, updates, storage };
}

test("normal active tab reaches only localhost and preserves block-page data", async () => {
  const h = browserHarness();
  await new Promise(setImmediate);
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].address, "http://localhost:9001");
  assert.equal(h.requests[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(h.requests[0].options.body), { url: "https://example.org/study", title: "Study" });
  assert.equal(h.storage.blockedTabUrl, "https://example.org/study");
  assert.equal(h.updates[0].id, 7);
  assert.equal(h.updates[0].data.url, "chrome-extension://test/blocking.html");
});

test("internal browser and extension pages are not transmitted", async () => {
  for (const url of ["about:config", "chrome://settings", "chrome-extension://test/blocking.html", "moz-extension://test/page"]) {
    const h = browserHarness(url);
    await new Promise(setImmediate);
    assert.equal(h.requests.length, 0);
    assert.equal(h.updates.length, 0);
  }
});

test("block page renders hostile titles as text and keeps allow/close actions", async () => {
  const elements = Object.fromEntries(["blockedUrl", "blockReason", "allowButton", "closeButton"].map(id => [id, {
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    set innerHTML(_) { throw new Error("Untrusted HTML rendering"); },
  }]));
  const title = '<img src=x onerror="alert(1)">';
  let request;
  let closed;
  let wentBack = false;
  const context = vm.createContext({
    document: { addEventListener: (_, cb) => cb(), getElementById: id => elements[id] },
    window: { history: { back: () => { wentBack = true; } } },
    fetch: async (url, options) => { request = { url, options }; return { ok: true }; },
    chrome: {
      storage: { local: { get: (_, callback) => callback({ blockedTabUrl: "https://example.org", blockReason: title }) } },
      tabs: { query: (_, callback) => callback([{ id: 7 }]), remove: id => { closed = id; } },
    },
  });
  vm.runInContext(readFileSync(path.join(extensionDir, "blocking.js"), "utf8"), context);
  assert.equal(elements.blockReason.textContent, title);
  elements.allowButton.listeners.click();
  await new Promise(setImmediate);
  assert.equal(request.url, "http://localhost:9001/allow");
  assert.equal(JSON.parse(request.options.body).url, "https://example.org");
  assert.equal(wentBack, true);
  elements.closeButton.listeners.click();
  assert.equal(closed, 7);
});

test("extension permissions allow local communication without access to all sites", () => {
  const manifest = JSON.parse(readFileSync(path.join(extensionDir, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.host_permissions, ["http://localhost/*"]);
  assert.deepEqual(manifest.permissions, ["tabs", "storage"]);
  assert.ok(manifest.background.scripts.includes("background.js"));
  assert.equal(manifest.background.service_worker, "background.js");
});
