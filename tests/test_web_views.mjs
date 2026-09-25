import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import { createLessonState } from "../src/milai/web/exercise-controller.js";

const lesson = {
  id: "older", title: "German · Subject pronouns", objective: "Choose the right subject pronoun.",
  sections: [{id: "forms", title: "The forms", markdown: "Use **ich** for I."}],
  worked_examples: ["**Ich** singe."], recap: "Use the pronoun that fits the speaker.",
  exercises: [
    {id: "one", title: "Introduce yourself", context: "At a meeting", task: "Write a sentence."},
    {id: "two", title: "Choose a form", context: "", task: "Fill the gap."},
  ],
};
const detail = () => ({lesson, conversation: [], exercise_status: {}});

function storage() {
  const values = new Map();
  return {
    get length() { return values.size; },
    key(index) { return [...values.keys()][index] ?? null; },
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, value); },
    removeItem(key) { values.delete(key); },
  };
}

function streamResponse(events) {
  const encoder = new TextEncoder();
  let consumed = false;
  return {
    ok: true,
    body: {getReader: () => ({read: async () => {
      if (consumed) return {done: true};
      consumed = true;
      return {done: false, value: encoder.encode(events.map((event) => JSON.stringify(event)).join("\n") + "\n")};
    }})},
  };
}

function application(hash = "#chat", respond = () => new Promise(() => {}), browserStorage = storage()) {
  const requests = [];
  function element(view) {
    const classes = new Set();
    const item = {
      hidden: false, value: "", textContent: "", innerHTML: "", scrollTop: 0, scrollHeight: 500,
      dataset: view ? {view} : {}, children: [], style: {}, attributes: {}, listeners: {},
      classList: {
        add(name) { classes.add(name); },
        toggle(name, force) { if (force ?? !classes.has(name)) classes.add(name); else classes.delete(name); },
      },
      append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } },
      prepend(...children) { for (const child of children) { child.parent = this; this.children.unshift(child); } },
      replaceChildren(...children) { this.children = []; this.append(...children); },
      remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); },
      addEventListener(name, handler) { this.listeners[name] = handler; },
      setAttribute(name, value) { this.attributes[name] = value; },
      getAttribute(name) { return this.attributes[name] ?? null; },
      removeAttribute(name) { delete this.attributes[name]; },
      focus() {}, select() {}, showModal() {}, close() {},
      scrollIntoView() { this.scrolled = true; },
      querySelector(selector) { return descendants(this).find((child) => matches(child, selector)) ?? null; },
      requestSubmit() { this.listeners.submit?.({preventDefault() {}}); },
    };
    return item;
  }
  function descendants(parent) {
    return parent.children.flatMap((child) => [child, ...descendants(child)]);
  }
  function matches(item, selector) {
    if (selector.startsWith(".")) return item.className?.split(" ").includes(selector.slice(1));
    if (selector.startsWith("#")) return item.id === selector.slice(1);
    return false;
  }
  const nodes = new Map();
  for (const [selector, view] of [
    [".chat-panel", "chat"], ["#lesson-view", "lesson"], ["#sessions-panel", "sessions"], ["#skills-panel", "skills"],
  ]) nodes.set(selector, element(view));
  const node = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  };
  const context = vm.createContext({
    createLessonState, renderMarkdown: (value) => value, sessionStorage: browserStorage,
    TextDecoder, Uint8Array,
    location: new URL(hash, "http://localhost/"),
    window: {addEventListener() {}},
    fetch: (path, options = {}) => {
      if (path === "/api/bootstrap") return new Promise(() => {});
      requests.push({path, body: options.body ? JSON.parse(options.body) : null});
      return respond(path, options);
    },
    document: {
      querySelector: node,
      getElementById: (id) => [...nodes.values()].flatMap((item) => [item, ...descendants(item)]).find((item) => item.id === id) ?? null,
      querySelectorAll: (selector) => selector === "[data-view]"
        ? [...nodes.values()].filter((item) => item.dataset.view) : [],
      createElement: () => element(),
    },
  });
  const source = readFileSync(new URL("../src/milai/web/app.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, "");
  vm.runInContext(source, context);
  vm.runInContext("setBusy(false)", context);
  return {node, requests, storage: browserStorage, run: (code) => vm.runInContext(code, context), descendants};
}

function sessionPayload(session = "one") {
  return {
    session, sessions: [{id: session, title: "German practice"}], conversation: [],
    learning: {lessons: [{id: "older", title: lesson.title}, {id: "newer", title: "German · Verbs"}],
      active_lesson: {id: "newer"}},
  };
}

test("lesson sidebar and main card open stored content directly", async () => {
  const app = application("#chat", async (path) => ({ok: true, json: async () => detail()}));
  app.run(`applySession(${JSON.stringify(sessionPayload())}); renderConversation([{
    role: "assistant", content: "I made a lesson.", lesson_cards: [{id: "older", title: "German · Subject pronouns"}]
  }]);`);
  const card = app.node("#messages").children[0].children.at(-1);
  await card.children.at(-1).listeners.click();
  assert.equal(app.run("location.hash"), "#lesson/older");
  assert.equal(app.node("#lesson-view").hidden, false);
  assert.equal(app.node("#lesson-document").children[1].textContent, lesson.title);
  assert.equal(app.requests[0].path, "/api/lessons/older?session=one");
  assert.equal(app.node("#learning-path").children[1].children[0].attributes["aria-current"], "step");
  await app.node("#learning-path").children[0].children[0].listeners.click();
  assert.equal(app.requests.length, 1);
});

test("new practice in main chat opens its owning lesson exercise", async () => {
  const app = application("#chat", async () => ({ok: true, json: async () => detail()}));
  app.run(`applySession(${JSON.stringify(sessionPayload())}); renderConversation([{
    role: "assistant", content: "Here is another exercise.",
    activities: [{id: "two", lesson_id: "older", title: "Choose a form"}]
  }]);`);
  const card = app.node("#messages").children[0].children.at(-1);
  await card.children[1].listeners.click();
  assert.equal(app.run("location.hash"), "#lesson/older");
  assert.equal(app.node("#lesson-exercises").children[1].scrolled, true);
});

test("section question sends its reference and answer stays in the lesson", async () => {
  let savedConversation = [];
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({...detail(), conversation: savedConversation})};
    savedConversation = [
      {role: "user", content: "Why ich?", section_id: "forms", action: "message"},
      {role: "assistant", content: "Because the speaker is I.", section_id: "forms"},
    ];
    return streamResponse([{type: "stage", text: "Considering the section…"}, {type: "complete", result: {reply: {text: "Because the speaker is I."}}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const section = app.node("#lesson-document").children[3];
  section.children[0].children[1].listeners.click();
  assert.equal(app.node("#selected-reference-label").textContent, "Section: The forms");
  assert.equal(app.node("#lesson-layout").dataset.tab, "discussion");
  app.node("#lesson-message").value = "Why ich?";
  await app.run('submitLessonTurn("Why ich?")');
  assert.deepEqual(JSON.parse(JSON.stringify(app.requests[1].body)), {
    session: "one", lesson_id: "older", message: "Why ich?", action: "message", section_id: "forms",
  });
  assert.equal(app.node("#lesson-messages").children[0].children[0].children[1].textContent, "About The forms");
  assert.equal(app.node("#lesson-progress").textContent, "Saved to this lesson.");
  assert.equal(app.node("#messages").children[0].className, "welcome");
});

test("exercise submission uses answer action and a completed exercise remains discussable", async () => {
  let answered = false;
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({
      ...detail(), exercise_status: answered ? {one: {completed: true, assessments: [{learner_response: "Ich bin hier.", feedback: "Correct."}]}} : {},
    })};
    answered = true;
    return streamResponse([{type: "stage", text: "Checking your answer…"}, {type: "complete", result: {reply: {text: "Correct."}}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const exercise = app.node("#lesson-exercises").children[0];
  const form = exercise.children.at(-1);
  form.children[1].value = "Ich bin hier.";
  await form.listeners.submit({preventDefault() {}});
  assert.equal(app.requests[1].body.action, "answer");
  assert.equal(app.requests[1].body.exercise_id, "one");
  assert.equal(app.requests[1].body.lesson_id, "older");
  const refreshed = app.node("#lesson-exercises").children[0];
  assert.equal(refreshed.children[0].children[1].textContent, "Completed");
  assert.equal(refreshed.children.at(-1).children[1].disabled, true);
  assert.equal(refreshed.children.at(-1).children[2].children[0].disabled, true);
  refreshed.children.at(-1).children[2].children[1].listeners.click();
  assert.equal(app.node("#selected-reference-label").textContent, "Exercise: Introduce yourself");
});

test("back navigation and continue learning preserve the originating lesson", async () => {
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => detail()};
    return streamResponse([{type: "complete", result: {reply: {text: "Next step", lesson_cards: []}, learning: {lessons: []}, sessions: []}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  await app.node("#back-to-conversation").listeners.click();
  assert.equal(app.run("location.hash"), "#chat");
  assert.equal(app.requests.length, 1);
  app.node("#message").value = "Unsent main question";
  await app.run('navigate("lesson", "older")');
  await app.node("#continue-learning").listeners.click();
  assert.equal(app.requests.at(-1).body.origin_lesson_id, "older");
  assert.equal(app.requests.at(-1).body.lesson_id, undefined);
  assert.equal(app.run("location.hash"), "#chat");
  assert.equal(app.node("#message").value, "Unsent main question");
});

test("reload restores draft, selected exercise, reading position and tab; deletion clears them", async () => {
  const browser = storage();
  const respond = async (path) => ({ok: true, json: async () => path.startsWith("/api/lessons/") ? detail() : sessionPayload("two")});
  const first = application("#lesson/older", respond, browser);
  first.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await first.run("renderView()");
  first.node("#lesson-message").value = "unfinished";
  first.node("#lesson-message").listeners.input();
  first.node("#lesson-reading").scrollTop = 410;
  first.node("#lesson-reading").listeners.scroll();
  first.node("#lesson-exercises").children[0].children.at(-1).children[2].children[1].listeners.click();
  const second = application("#lesson/older", respond, browser);
  second.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await second.run("renderView()");
  assert.equal(second.node("#lesson-message").value, "unfinished");
  assert.equal(second.node("#lesson-reading").scrollTop, 410);
  assert.equal(second.node("#selected-reference-label").textContent, "Exercise: Introduce yourself");
  assert.equal(second.node("#lesson-layout").dataset.tab, "discussion");
  await second.run('manageSession("delete", {session: "one"})');
  assert.equal(createLessonState(browser).get("one", "older").draft, "");
});

test("session switching changes the lesson scope without recording an attempt", async () => {
  const app = application("#lesson/older", async (path) => ({ok: true, json: async () => path.startsWith("/api/lessons/") ? detail() : sessionPayload("other")}));
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  await app.run('manageSession("select", {session: "other"})');
  assert.equal(app.run("location.hash"), "#chat");
  assert.equal(app.requests.filter((request) => request.path === "/api/chat/stream").length, 0);
  assert.equal(app.node("#lesson-view").hidden, true);
});
