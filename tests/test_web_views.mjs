import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import { createExerciseController } from "../src/milai/web/exercise-controller.js";

// Execute the actual app against a minimal DOM, including its initialization and
// session application. Hash changes are explicit so tests cover unchanged hashes.
function application(hash = "#chat", respond = () => new Promise(() => {})) {
  const requests = [];
  function element(view) {
    return {
      hidden: false, value: "", textContent: "", scrollTop: 0,
      dataset: { view }, children: [], style: {},
      attributes: {}, listeners: {},
      classList: { add() {}, toggle() {} },
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      addEventListener(name, handler) { this.listeners[name] = handler; },
      setAttribute(name, value) { this.attributes[name] = value; },
      removeAttribute(name) { delete this.attributes[name]; },
      focus() {}, select() {}, showModal() {}, close() {},
      scrollIntoView() { this.scrolled = true; },
    };
  }
  const nodes = new Map();
  for (const [selector, view] of [
    [".chat-panel", "chat"], ["#sessions-panel", "sessions"], ["#skills-panel", "skills"],
  ]) nodes.set(selector, element(view));
  const node = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  };
  const context = vm.createContext({
    createExerciseController, renderMarkdown: (text) => text,
    location: new URL(hash, "http://localhost/"), window: {
      addEventListener() {}, matchMedia: () => ({matches: false, addEventListener() {}}),
    },
    // Keep bootstrap pending; each test supplies its own session response.
    fetch: (path, options) => {
      if (path === "/api/bootstrap") return new Promise(() => {});
      requests.push({path, body: JSON.parse(options.body)});
      return respond(path, options);
    },
    document: {
      querySelector: node,
      getElementById: (id) => {
        const find = (items) => {
          for (const item of items) {
            if (item.id === id) return item;
            const nested = find(item.children);
            if (nested) return nested;
          }
          return null;
        };
        return find([...nodes.values()]);
      },
      querySelectorAll: (selector) => selector === "[data-view]"
        ? [...nodes.values()].filter((item) => item.dataset.view) : [],
      createElement: () => element(),
    },
  });
  const source = readFileSync(new URL("../src/milai/web/app.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, "");
  vm.runInContext(source, context);
  vm.runInContext("setBusy(false)", context);
  return { node, requests, run: (code) => vm.runInContext(code, context) };
}

for (const view of ["sessions", "skills"]) {
  test(`${view} keeps the conversation and exercise hidden`, () => {
    const app = application(`#${view}`);
    assert.equal(app.node(".chat-panel").hidden, true);
    assert.equal(app.node(".path-rail").hidden, view === "sessions");
    assert.equal(app.node("#exercise-view").hidden, true);
    assert.equal(app.node(`#${view}-panel`).hidden, false);
  });
}

for (const hash of ["", "#unknown", "#map", "#chat"]) {
  test(`conversation fallback shows both panels for ${JSON.stringify(hash)}`, () => {
    const app = application(hash);
    assert.equal(app.node(".chat-panel").hidden, false);
    assert.equal(app.node(".path-rail").hidden, false);
    assert.equal(app.node("#exercise-view").hidden, true);
  });
}

test("exercise content uses the conversation Markdown renderer", () => {
  const app = application();
  app.run('exercise.setSession("one"); openExercise({id: "task", title: "Practice", context: "Use **hören**.", task: "Add endings:\\n1. **ich**\\n2. **du**"});');
  assert.equal(app.node("#exercise-context").innerHTML, "Use **hören**.");
  assert.equal(app.node("#exercise-task").innerHTML, "Add endings:\n1. **ich**\n2. **du**");
});

test("hint click shows progress and renders the returned hint", async () => {
  let resolve;
  const app = application("#chat", () => new Promise((done) => { resolve = done; }));
  app.run('exercise.setSession("one"); openExercise({id: "task", title: "Practice", context: "", task: "Answer"});');
  const request = app.node("#exercise-hint").listeners.click();
  assert.equal(app.requests[0].body.action, "hint");
  assert.equal(app.node("#exercise-status").textContent, "Preparing a hint…");
  assert.equal(app.node("#exercise-hint").disabled, true);
  resolve({ok: true, json: async () => ({
    status: {completed: false}, reply: {text: "Try **-st**.", activities: []},
    sessions: [], learning: {}, topic_anchors: {},
  })});
  await request;
  assert.equal(app.node("#exercise-history").children[0].innerHTML, "<strong>Hint:</strong> Try **-st**.");
  assert.equal(app.node("#exercise-status").textContent, "");
  assert.equal(app.node("#exercise-hint").disabled, false);
});

test("prepared hint appears without a conversation reply", async () => {
  const app = application("#chat", async () => ({ok: true, json: async () => ({
    hint: "Check the ending.", status: {assisted: true, completed: false},
  })}));
  app.run('exercise.setSession("one"); openExercise({id: "task", title: "Practice", context: "", task: "Answer"});');
  const before = app.node("#messages").children.length;
  await app.node("#exercise-hint").listeners.click();
  assert.equal(app.node("#exercise-history").children[0].innerHTML, "<strong>Hint:</strong> Check the ending.");
  assert.equal(app.node("#messages").children.length, before);
});

test("switching sessions from completed practice restores chat without a hash change", () => {
  const app = application();
  app.run(`
    activeSession = "old";
    exercise.setSession("old", {done: {completed: true}});
    openExercise({id: "done", title: "Old exercise", context: "Practice", task: "Answer"});
  `);
  assert.equal(app.node(".chat-panel").hidden, true);
  assert.equal(app.node("#exercise-view").hidden, false);
  app.run(`applySession({
    session: "new", sessions: [{id: "new", title: "New session", turns: 0}],
    conversation: [], learning: {}, exercise_status: {}
  });`);
  assert.equal(app.run("location.hash"), "#chat");
  assert.equal(app.run("exercise.active"), null);
  assert.equal(app.node("#exercise-view").hidden, true);
  assert.equal(app.node(".chat-panel").hidden, false);
  assert.equal(app.node(".path-rail").hidden, false);
  assert.equal(app.node("#session-label").textContent, "New session");
});


test("topic links jump to committed discussion without sending a message", async () => {
  const app = application();
  app.run(`applySession({
    session: "one", sessions: [], exercise_status: {}, topic_anchors: {old: "turn-old"},
    conversation: [{role: "assistant", content: "Earlier explanation", turn_id: "turn-old"}],
    learning: {topics: [{id: "old", name: "Earlier topic"}, {id: "current", name: "Current topic"}], focus: {topic_id: "current"}}
  }); elements.message.value = "unsent draft";`);
  const links = app.node("#learning-path").children.map((item) => item.children[0]);
  assert.equal(links[0].textContent, "Earlier topic");
  assert.equal(links[1].attributes["aria-current"], "step");
  await links[0].listeners.click();
  assert.equal(app.node("#messages").children[0].scrolled, true);
  assert.equal(app.node("#message").value, "unsent draft");
  assert.equal(links[1].attributes["aria-current"], "step");
  assert.equal(app.requests.length, 0);
  await links[1].listeners.click();
  assert.match(app.node("#notice").textContent, /unavailable/);
});

test("visiting Sessions and returning preserves draft and conversation position", async () => {
  const app = application();
  app.node("#message").value = "draft";
  app.node("#messages").scrollTop = 123;
  await app.run('location.hash = "sessions"; renderView()');
  assert.equal(app.node("#session-heading").hidden, true);
  await app.run('location.hash = "chat"; renderView()');
  assert.equal(app.node("#message").value, "draft");
  assert.equal(app.node("#messages").scrollTop, 123);
  assert.equal(app.requests.length, 0);
});

for (const action of ["rename", "delete", "select", "create"]) {
  test(`${action} uses the selected session row and the appropriate destination`, async () => {
    const app = application("#sessions", async () => ({ok: true, json: async () => ({
      session: action === "select" || action === "create" ? "other" : "active",
      sessions: [{id: "active", title: "Active"}, {id: "other", title: "Other"}],
      conversation: [], learning: {}, exercise_status: {}, topic_anchors: {},
    })}));
    app.run(`activeSession = "active"; renderSessions([{id: "active", title: "Active"}, {id: "other", title: "Other"}]);`);
    const row = app.node("#sessions").children[1];
    if (action === "rename" || action === "delete") {
      row.children[1].children[action === "rename" ? 0 : 1].listeners.click();
      assert.equal(app.run("dialogSession"), "other");
      await app.run('manageSession(dialogAction, {session: dialogSession, title: "Updated"})');
    } else await app.run(`manageSession("${action}", {session: "other"})`);
    assert.equal(app.requests[0].body.session, "other");
    assert.equal(app.run("location.hash"), action === "select" || action === "create" ? "#chat" : "#sessions");
  });
}

test("navigation cannot reveal content before review succeeds", async () => {
  let resolve;
  const app = application("#chat", () => new Promise((done) => {resolve = done;}));
  app.run(`exercise.setSession("one"); openExercise({id: "exercise", title: "Task"});`);
  const navigation = app.run('location.hash = "sessions"; renderView()');
  assert.equal(app.node(".path-rail").hidden, true);
  assert.equal(app.node(".chat-panel").hidden, true);
  assert.equal(app.node("#exercise-view").hidden, false);
  assert.equal(app.requests[0].body.action, "review");
  resolve({ok: true, json: async () => ({status: {assisted: true}})});
  await navigation;
  assert.equal(app.node("#sessions-panel").hidden, false);
  assert.equal(app.node("#exercise-view").hidden, true);
});

test("failed review keeps the exercise open and path hidden", async () => {
  const app = application("#chat", async () => ({ok: false, json: async () => ({error: "Review failed"})}));
  app.run('exercise.setSession("one"); openExercise({id: "exercise", title: "Task"});');
  await app.run('location.hash = "skills"; renderView()');
  assert.equal(app.run('location.hash'), '#chat');
  assert.equal(app.node('#exercise-view').hidden, false);
  assert.equal(app.node('.path-rail').hidden, true);
  assert.equal(app.node('.chat-panel').hidden, true);
  assert.equal(app.node('#notice').textContent, 'Review failed');
});

test("renaming from Sessions does not overwrite the saved chat scroll", async () => {
  const app = application("#sessions", async () => ({ok: true, json: async () => ({
    session: "one", sessions: [{id: "one", title: "Updated"}],
    conversation: [], learning: {}, exercise_status: {}, topic_anchors: {},
  })}));
  app.run('activeSession = "one"; scrollPositions.set("one", 321);');
  // Hidden scroll containers may report zero in a real browser.
  app.node('#messages').scrollTop = 0;
  await app.run('manageSession("rename", {session: "one", title: "Updated"})');
  await app.run('location.hash = "chat"; renderView()');
  assert.equal(app.node('#messages').scrollTop, 321);
});
