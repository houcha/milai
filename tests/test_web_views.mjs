import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import { createLessonState, MAX_SELECTED_TEXT, readLessonSelection, blankAnswers, parseBlankAnswers, serializeBlankAnswers, MAX_BLANK_ANSWER_LENGTH, parseItemAnswers, serializeItemAnswers, MAX_EXERCISE_ANSWER_LENGTH } from "../src/milai/web/exercise-controller.js";
import { renderExerciseMarkdown } from "../src/milai/web/markdown.bundle.js";

const lesson = {
  id: "older", title: "Subject pronouns", objective: "Choose the right subject pronoun.",
  sections: [{id: "forms", title: "The forms", markdown: "Use **ich** for I."}],
  worked_examples: ["**Ich** singe."], recap: "Use the pronoun that fits the speaker.",
  exercises: [
    {id: "one", title: "Introduce yourself", context: "At a meeting", task: "Write a sentence."},
    {id: "two", title: "Choose a form", context: "", task: "Fill the gap."},
  ],
};
const detail = () => ({lesson, conversation: [], exercise_status: {}});

function typedDetail(type = "translate") {
  const instructions = {choose_form: "Choose the correct form.", complete_sentence: "Fill in the blank.", translate: "Translate into German.", transform: "Rewrite using ihr.", short_response: "Write one sentence in German using haben."};
  const items = [
    {text: ["choose_form", "complete_sentence"].includes(type) ? "Ihr {{blank}} Zeit." : "You have", context: "Several people, informal", ...(type === "choose_form" ? {options: ["hat", "habt", "haben"]} : {})},
    {text: ["choose_form", "complete_sentence"].includes(type) ? "Sie {{blank}} Zeit." : "She has", context: "One woman", ...(type === "choose_form" ? {options: ["hat", "habt", "haben"]} : {})},
  ];
  return {lesson: {...lesson, exercises: [{id: "typed", title: "Practice", task: "Fallback must not render", format: {version: 1, type, instruction: instructions[type], items}}]}, conversation: [], exercise_status: {}};
}

for (const type of ["choose_form", "complete_sentence", "translate", "transform", "short_response"]) {
  test(`typed ${type} renders fixed instructions and saves a mapped submission`, async () => {
    const payload = typedDetail(type);
    let submitted;
    const app = application("#lesson/older", async (path, options) => {
      if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => payload};
      submitted = JSON.parse(options.body);
      payload.exercise_status.typed = {submitted: true, assessments: [{learner_response: submitted.message, item_results: [
        {item_number: 1, correct: true, feedback: ""},
        {item_number: 2, correct: false, feedback: "Use hat for one woman."},
      ]}]};
      return streamResponse([{type: "complete", result: {reply: {text: "Assessed"}}}]);
    });
    app.run(`applySession(${JSON.stringify(sessionPayload())})`);
    await app.run("renderView()");
    const card = app.node("#lesson-exercises").children[0];
    const nodes = app.descendants(card);
    assert.equal(nodes.find(node => node.className === "exercise-instruction").textContent, payload.lesson.exercises[0].format.instruction);
    assert.equal(nodes.some(node => node.textContent.includes("Fallback must not render")), false);
    if (type === "choose_form") {
      const radios = nodes.filter(node => node.tagName === "INPUT");
      assert.equal(radios.length, 6);
      radios[1].listeners.change();
      radios[4].listeners.change();
    } else {
      const fields = nodes.filter(node => node.tagName === (type === "complete_sentence" ? "INPUT" : "TEXTAREA"));
      assert.equal(fields.length, 2);
      fields.forEach((field, index) => {field.value = ["ihr habt", "sie haben"][index]; field.listeners.input();});
    }
    const saved = app.storage.getItem("milai:session:one:lesson:older");
    assert.equal(JSON.parse(saved).answers.typed.length, 2);
    const messages = app.node("#lesson-messages").children;
    await nodes.find(node => node.tagName === "FORM").listeners.submit({preventDefault() {}});
    assert.equal(submitted.action, "answer");
    assert.equal(submitted.exercise_id, "typed");
    assert.deepEqual(parseItemAnswers(submitted.message, 2), type === "choose_form" ? ["2", "2"] : ["ihr habt", "sie haben"]);
    const completed = app.descendants(app.node("#lesson-exercises").children[0]);
    assert.equal(completed.filter(node => ["INPUT", "TEXTAREA", "FORM"].includes(node.tagName)).length, 0);
    assert.equal(completed.filter(node => node.className === "item-feedback").length, 1);
    assert.equal(completed.find(node => node.className === "item-feedback").textContent, "Use hat for one woman.");
    assert.equal(completed.filter(node => node.attributes["aria-label"]?.includes(" — ")).length, 2);
    assert.equal(app.node("#lesson-messages").children, messages);
  });
}

test("typed choice drafts restore on reload and failed answers remain editable", async () => {
  const payload = typedDetail("choose_form");
  const browser = storage();
  const respond = async (path) => path.startsWith("/api/lessons/")
    ? {ok: true, json: async () => payload}
    : {ok: false, json: async () => ({error: "Assessment unavailable"})};
  const first = application("#lesson/older", respond, browser);
  first.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await first.run("renderView()");
  let radios = first.descendants(first.node("#lesson-exercises")).filter(node => node.tagName === "INPUT");
  radios[1].listeners.change();
  radios[3].listeners.change();
  const second = application("#lesson/older", respond, browser);
  second.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await second.run("renderView()");
  radios = second.descendants(second.node("#lesson-exercises")).filter(node => node.tagName === "INPUT");
  assert.equal(radios[1].checked, true);
  assert.equal(radios[3].checked, true);
  const form = second.descendants(second.node("#lesson-exercises")).find(node => node.tagName === "FORM");
  await form.listeners.submit({preventDefault() {}});
  assert.equal(second.node("#lesson-exercises").children[0].querySelector(".exercise-progress").textContent, "Assessment unavailable");
  assert.equal(radios.every(node => !node.disabled), true);
  assert.deepEqual(JSON.parse(browser.getItem("milai:session:one:lesson:older")).answers.typed, ["2", "1"]);
});

test("typed results label answers and reject empty fields locally", async () => {
  const payload = typedDetail();
  payload.lesson.practice_results = [{number: 1, finished: true, correct: 1, total: 2, percentage: 50, scoring: "items"}];
  const app = application("#lesson/older", async () => ({ok: true, json: async () => payload}));
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  assert.ok(app.descendants(app.node("#lesson-results")).some(node => node.textContent === "1 of 2 answers correct on the first submission."));
  const nodes = app.descendants(app.node("#lesson-exercises"));
  await nodes.find(node => node.tagName === "FORM").listeners.submit({preventDefault() {}});
  assert.equal(app.requests.length, 1);
  assert.equal(nodes.find(node => node.className === "exercise-answer-error").hidden, false);
});

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
  const documentListeners = {};
  let selection = null;
  function element(view, tag = "div") {
    const classes = new Set();
    let html = "";
    const item = {
      hidden: false, value: "", textContent: "", scrollTop: 0, scrollHeight: 500,
      get innerHTML() { return html; },
      set innerHTML(value) {
        html = value;
        this.children = [];
        for (const match of value.matchAll(/<span class="exercise-blank" data-blank-number="(\d+)">____<\/span>/g)) {
          const blank = element(null, "span");
          blank.className = "exercise-blank";
          blank.dataset.blankNumber = match[1];
          blank.textContent = "____";
          this.append(blank);
        }
        for (const match of value.matchAll(/<li class="exercise-item" data-item-number="(\d+)">/g)) {
          const entry = element(null, "li");
          entry.className = "exercise-item";
          entry.dataset.itemNumber = match[1];
          this.append(entry);
        }
      },
      dataset: view ? {view} : {}, children: [], style: {}, attributes: {}, listeners: {},
      nodeType: 1, tagName: tag.toUpperCase(),
      get parentElement() { return this.parent ?? null; },
      contains(child) { return this === child || descendants(this).includes(child); },
      closest(selector) {
        if (selector.split(",").some((part) => matches(this, part.trim()))) return this;
        return this.parentElement?.closest(selector) ?? null;
      },
      classList: {
        add(name) { classes.add(name); },
        contains(name) { return classes.has(name); },
        toggle(name, force) { if (force ?? !classes.has(name)) classes.add(name); else classes.delete(name); },
      },
      append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } },
      insertBefore(child, next) {
        child.parent = this;
        if (next) this.children.splice(this.children.indexOf(next), 0, child);
        else this.children.push(child);
      },
      prepend(...children) { for (const child of children) { child.parent = this; this.children.unshift(child); } },
      replaceChildren(...children) { this.children = []; this.append(...children); },
      replaceWith(other) {
        const index = this.parent.children.indexOf(this);
        this.parent.children[index] = other;
        other.parent = this.parent;
      },
      remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); },
      addEventListener(name, handler) { this.listeners[name] = handler; },
      setAttribute(name, value) { this.attributes[name] = value; },
      getAttribute(name) {
        if (name.startsWith("data-")) return this.dataset[dataKey(name)] ?? null;
        return this.attributes[name] ?? null;
      },
      removeAttribute(name) { delete this.attributes[name]; },
      focus() {}, select() {}, showModal() {}, close() {},
      scrollIntoView() { this.scrolled = true; },
      querySelector(selector) { return descendants(this).find((child) => matches(child, selector)) ?? null; },
      querySelectorAll(selector) { return descendants(this).filter((child) => matches(child, selector)); },
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
    if (selector.startsWith("[data-")) return dataKey(selector.slice(1, -1)) in item.dataset;
    return item.tagName?.toLowerCase() === selector;
  }
  function dataKey(name) { return name.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase()); }
  const nodes = new Map();
  for (const [selector, view] of [
    [".chat-panel", "chat"], ["#lesson-view", "lesson"], ["#sessions-panel", "sessions"], ["#skills-panel", "skills"],
  ]) nodes.set(selector, element(view));
  const node = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  };
  for (const selector of ["#brand-sessions-link", "#mobile-sessions-link"]) {
    const language = element(null, "span");
    language.className = "session-nav-language";
    node(selector).append(language);
  }
  node("#lesson-document").dataset.selectionSource = "";
  node("#lesson-reading").append(node("#lesson-document"), node("#lesson-exercises"));
  const context = vm.createContext({
    createLessonState: () => createLessonState(browserStorage), MAX_SELECTED_TEXT, readLessonSelection,
    renderExerciseMarkdown, blankAnswers, parseBlankAnswers, serializeBlankAnswers, MAX_BLANK_ANSWER_LENGTH,
    parseItemAnswers, serializeItemAnswers, MAX_EXERCISE_ANSWER_LENGTH,
    renderMarkdown: (value) => value, sessionStorage: browserStorage,
    TextDecoder, Uint8Array,
    location: new URL(hash, "http://localhost/"),
    window: {addEventListener() {}, getSelection: () => selection},
    fetch: (path, options = {}) => {
      if (path === "/api/bootstrap") return new Promise(() => {});
      requests.push({path, body: options.body ? JSON.parse(options.body) : null});
      return respond(path, options);
    },
    document: {
      addEventListener(name, listener) { documentListeners[name] = listener; },
      querySelector: node,
      getElementById: (id) => [...nodes.values()].flatMap((item) => [item, ...descendants(item)]).find((item) => item.id === id) ?? null,
      querySelectorAll: (selector) => selector === "[data-view]"
        ? [...nodes.values()].filter((item) => item.dataset.view) : [],
      createElement: (tag) => element(null, tag),
    },
  });
  const source = readFileSync(new URL("../src/milai/web/app.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, "");
  vm.runInContext(source, context);
  vm.runInContext("setBusy(false)", context);
  return {
    node, requests, storage: browserStorage, run: (code) => vm.runInContext(code, context), descendants,
    select(start, text, end = start) {
      selection = {
        isCollapsed: !text, rangeCount: 1, toString: () => text,
        getRangeAt: () => ({startContainer: start, endContainer: end}),
        removeAllRanges() { selection = null; },
      };
      documentListeners.selectionchange();
    },
  };
}

function sessionPayload(session = "one") {
  return {
    session, sessions: [{id: session, title: "Daily practice", language: "German"}], conversation: [],
    learning: {lessons: [{id: "older", title: lesson.title}, {id: "newer", title: "Verbs"}],
      active_lesson: {id: "newer"}},
  };
}

test("sidebar highlight follows lesson navigation and returns to the teaching focus in chat", async () => {
  const app = application("#chat", async (path) => ({ok: true, json: async () => ({
    ...detail(), lesson: {...lesson, id: path.includes("newer") ? "newer" : "older"},
  })}));
  const payload = sessionPayload();
  payload.learning.current_focus_lesson_id = "newer";
  app.run(`applySession(${JSON.stringify(payload)})`);
  await app.run("renderView()");
  const assertSelected = (id, ariaCurrent) => {
    const links = app.node("#learning-path").querySelectorAll(".lesson-link");
    for (const link of links) {
      assert.equal(link.parentElement.classList.contains("current"), link.dataset.lessonId === id);
      assert.equal(link.getAttribute("aria-current"), link.dataset.lessonId === id ? ariaCurrent : null);
    }
  };
  assertSelected("newer", "step");
  await app.node("#learning-path").children[0].children[0].listeners.click();
  assert.equal(app.run("lessonData.id"), "older");
  assertSelected("older", "page");
  app.run(`renderLearning(${JSON.stringify(payload.learning)})`);
  assertSelected("older", "page");
  assert.equal(app.run("continuationLessonId()"), "newer");
  await app.node("#learning-path").children[1].children[0].listeners.click();
  assert.equal(app.run("lessonData.id"), "newer");
  assertSelected("newer", "page");
  app.run('location.hash = "#lesson/older"');
  await app.run("renderView()");
  assertSelected("older", "page");
  await app.run('navigate("chat")');
  assertSelected("newer", "step");
});

test("sidebar selects a lesson while it loads and ignores a stale lesson response", async () => {
  const resolveLesson = new Map();
  const app = application("#lesson/older", (path) => new Promise((resolve) => {
    const id = path.includes("newer") ? "newer" : "older";
    resolveLesson.set(id, () => resolve({ok: true, json: async () => ({
      ...detail(), lesson: {...lesson, id},
    })}));
  }));
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  const older = app.run("renderView()");
  const links = app.node("#learning-path").querySelectorAll(".lesson-link");
  assert.equal(links[0].getAttribute("aria-current"), "page");
  assert.equal(links[1].getAttribute("aria-current"), null);
  const newer = app.run('navigate("lesson", "newer")');
  assert.equal(links[0].parentElement.classList.contains("current"), false);
  assert.equal(links[1].parentElement.classList.contains("current"), true);
  resolveLesson.get("newer")();
  await newer;
  resolveLesson.get("older")();
  await older;
  assert.equal(app.run("lessonData.id"), "newer");
  assert.deepEqual(app.node("#learning-path").querySelectorAll(".lesson-link").map(link => link.getAttribute("aria-current")), [null, "page"]);
});

test("language follows the selected session and stays out of lesson titles", async () => {
  const app = application("#lesson/older", async () => ({ok: true, json: async () => detail()}));
  const payload = sessionPayload();
  payload.sessions = [
    {id: "one", title: "Daily practice", language: "German", turns: 2},
    {id: "two", title: "Daily practice", language: "French", turns: 1},
    {id: "empty", title: "New learning session", language: null, turns: 0},
  ];
  app.run(`applySession(${JSON.stringify(payload)})`);
  await app.run("renderView()");
  for (const selector of ["#brand-sessions-link", "#mobile-sessions-link"]) {
    const link = app.node(selector);
    assert.equal(link.querySelector(".session-nav-language").textContent, "German");
    assert.equal(link.attributes["aria-label"], "Sessions · German");
  }
  assert.equal(app.node("#session-label").textContent, "Daily practice");
  assert.equal(app.descendants(app.node("#lesson-document")).find(node => node.tagName === "H1").textContent, "Subject pronouns");
  assert.equal(app.descendants(app.node("#learning-path")).find(node => node.tagName === "BUTTON").textContent, "Subject pronouns");
  const details = app.descendants(app.node("#sessions")).filter(node => node.tagName === "SMALL");
  assert.deepEqual(details.map(node => node.textContent), ["German · 2 exchanges", "French · 1 exchange", "A fresh start"]);
  await app.run('navigate("skills")');
  assert.equal(app.node(".topbar").hidden, false);
  assert.equal(app.node("#brand-sessions-link").querySelector(".session-nav-language").textContent, "German");
  await app.run('navigate("sessions")');
  assert.equal(app.node(".topbar").hidden, true);
  app.run(`applySession(${JSON.stringify({...payload, session: "two", learning: {}})})`);
  await app.run('navigate("chat")');
  assert.equal(app.node(".topbar").hidden, false);
  assert.equal(app.node("#brand-sessions-link").querySelector(".session-nav-language").textContent, "French");
  app.run(`applySession(${JSON.stringify({...payload, session: "empty", learning: {}})})`);
  assert.equal(app.node("#brand-sessions-link").querySelector(".session-nav-language").textContent, "milai");
  assert.equal(app.node("#brand-sessions-link").attributes["aria-label"], "Sessions");
  payload.sessions[2].language = "Italian";
  app.run(`renderSessions(${JSON.stringify(payload.sessions)})`);
  assert.equal(app.node("#brand-sessions-link").querySelector(".session-nav-language").textContent, "Italian");
  assert.equal(app.node("#mobile-sessions-link").querySelector(".session-nav-language").textContent, "Italian");
});

function completedLesson() {
  return {...lesson, practice_results: [{
    set_id: "set-one", number: 1, finished: true, correct: 4, total: 5,
    percentage: 80, scoring: "items", completion_turn_id: "last-answer",
    last_submitted_at: "2026-09-27T12:00:00Z",
    review_at: "2099-01-01T12:00:00Z",
    completion_summary: "You chose the forms correctly. Check the subject in longer sentences.",
  }]};
}

test("lesson cards change from ready to complete in place and stay in their session", async () => {
  const completed = completedLesson();
  const payload = sessionPayload();
  payload.learning.lessons[0] = completed;
  payload.conversation = [
    {role: "user", content: "Teach me", created: "2026-09-27T11:00:00Z"},
    {role: "assistant", content: "Here is a lesson", created: "2026-09-27T11:00:00Z", lesson_cards: [lesson]},
    {role: "user", content: "Continue", created: "2026-09-27T13:00:00Z"},
  ];
  const app = application("#chat", async () => ({ok: true, json: async () => ({...detail(), lesson: completed})}));
  const unfinished = {...payload, learning: {...payload.learning, lessons: [lesson]}};
  app.run(`applySession(${JSON.stringify(unfinished)})`);
  const ready = app.node("#messages").querySelector(".lesson-card");
  assert.equal(ready.children[0].textContent, "Lesson ready");
  const introducingMessage = app.node("#messages").children[1];
  app.run(`renderLearning(${JSON.stringify(payload.learning)})`);
  assert.equal(app.node("#messages").children[1], introducingMessage);
  assert.equal(introducingMessage.querySelector(".lesson-card"), ready);
  assert.equal(ready.children[0].textContent, "Lesson complete");
  app.run(`applySession(${JSON.stringify(payload)})`);
  const messages = app.node("#messages");
  assert.equal(messages.children.length, 3);
  const card = messages.children[1].querySelector(".lesson-card");
  assert.equal(card.className, "lesson-card completed-lesson");
  assert.equal(card.children[2].textContent, lesson.objective);
  assert.equal(messages.querySelectorAll(".lesson-card").length, 1);
  messages.scrollTop = 37;
  const pending = app.run('appendMessage(elements.messages, "assistant", "Working…", {pending: true})');
  messages.scrollTop = 37;
  app.run(`renderLearning(${JSON.stringify(payload.learning)}); syncLessonCards()`);
  assert.equal(messages.children[1].querySelector(".lesson-card"), card);
  assert.equal(messages.children.at(-1), pending);
  assert.equal(messages.scrollTop, 37);
  assert.equal(card.querySelectorAll("button").length, 1);
  assert.equal(card.querySelector("button").textContent, "Revisit lesson");
  await card.querySelector("button").listeners.click();
  assert.equal(app.run("currentRoute.lessonId"), "older");
  app.run(`applySession(${JSON.stringify(payload)})`);
  assert.equal(messages.querySelectorAll(".completed-lesson").length, 1);
  app.run(`applySession(${JSON.stringify(sessionPayload("two"))})`);
  assert.equal(messages.querySelectorAll(".completed-lesson").length, 0);
});

test("one lesson card includes all finished practice sets, including unscored results", () => {
  const payload = sessionPayload();
  const completed = completedLesson();
  completed.practice_results.push(
    {...completed.practice_results[0], set_id: "set-two", number: 2, percentage: null, completion_summary: null},
    {set_id: "set-three", number: 3, finished: false},
  );
  payload.learning.lessons[0] = completed;
  const app = application();
  app.run(`applySession(${JSON.stringify(payload)})`);
  const cards = app.node("#messages").children;
  assert.equal(cards.length, 1);
  assert.equal(cards[0].children[0].textContent, "Practice 2 complete");
  const scores = cards[0].querySelectorAll(".lesson-card-score");
  assert.equal(scores.length, 2);
  assert.equal(scores[0].textContent, "Lesson: 80% correct");
  assert.equal(scores[1].textContent, "Practice 2: Submitted · Accuracy unavailable");
});

test("completed lessons only offer more practice and the chat shortcut preserves drafts on retry", async () => {
  const completed = completedLesson();
  let fail = true;
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({...detail(), lesson: completed})};
    return streamResponse(fail ? [{type: "error", error: "Try later"}] : [{type: "complete", result: {reply: {text: "Next lesson"}, learning: sessionPayload().learning}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const result = app.node("#lesson-results").children[0];
  assert.equal(result.querySelector(".completion-summary").textContent, completed.practice_results[0].completion_summary);
  app.node("#message").value = "My unsent question";
  assert.equal(result.querySelectorAll("button").length, 1);
  assert.equal(result.querySelector("button").textContent, "More practice");
  await app.node("#back-to-conversation").listeners.click();
  const button = app.node("#continue-learning");
  await Promise.all([button.listeners.click(), button.listeners.click()]);
  assert.equal(app.requests.filter(request => request.body?.origin_lesson_id).length, 1);
  assert.equal(app.requests.at(-1).body.origin_lesson_id, "newer");
  assert.equal(app.run("location.hash"), "#chat");
  assert.equal(app.node("#message").value, "My unsent question");
  fail = false;
  await app.node("#notice").children.at(-1).listeners.click();
  assert.equal(app.requests.at(-1).body.origin_lesson_id, "newer");
  assert.equal(app.requests.at(-1).body.lesson_id, undefined);
  assert.equal(app.node("#message").value, "My unsent question");
  assert.equal(app.run("continuationPending"), false);
});

test("chat shortcut continues from current focus and hides when the session has no lessons", async () => {
  const payload = sessionPayload();
  payload.learning.lessons[0] = completedLesson();
  const app = application("#chat", async () => streamResponse([{type: "complete", result: {
    reply: {text: "Next lesson"}, learning: payload.learning,
  }}]));
  app.run(`applySession(${JSON.stringify(payload)})`);
  assert.equal(app.node("#chat-shortcuts").hidden, false);
  await app.node("#continue-learning").listeners.click();
  assert.equal(app.requests.at(-1).body.origin_lesson_id, "newer");
  app.run('applySession({session: "empty", sessions: [], conversation: [], learning: {lessons: []}})');
  assert.equal(app.node("#chat-shortcuts").hidden, true);
  assert.equal(app.node("#continue-learning").disabled, true);
  assert.equal(app.requests.at(-1).body.lesson_id, undefined);
});

test("more practice sends an explicit request, keeps the question and quote, and reveals fresh exercises", async () => {
  const payload = {...detail(), lesson: completedLesson()};
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => payload};
    payload.lesson = {...payload.lesson, exercises: [...payload.lesson.exercises, {id: "fresh", title: "Fresh exercise", task: "Write a new sentence."}]};
    return streamResponse([{type: "complete", result: {reply: {text: "Here is fresh practice", activities: [{id: "fresh", lesson_id: "older"}]}}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  app.node("#lesson-message").value = "Why this form?";
  app.node("#lesson-message").listeners.input();
  app.select(app.node("#lesson-document"), "Use ich");
  const selected = app.run("lessonState().selected");
  const result = app.node("#lesson-results").children[0];
  await result.querySelector(".more-practice").listeners.click();
  const request = app.requests.find(request => request.body?.action === "message").body;
  assert.equal(request.lesson_id, "older");
  assert.equal(request.selected_text, undefined);
  assert.match(request.message, /fresh practice/);
  assert.equal(app.node("#lesson-message").value, "Why this form?");
  assert.deepEqual(app.run("lessonState().selected"), selected);
  assert.equal(app.run("lessonState().tab"), "lesson");
  assert.equal(app.node("#lesson-exercises").children.at(-1).scrolled, true);
});

test("more-practice retry returns to its originating lesson after navigation", async () => {
  let fail = true;
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({...detail(), lesson: {...completedLesson(), id: path.includes("newer") ? "newer" : "older"}})};
    return streamResponse(fail ? [{type: "error", error: "Try later"}] : [{type: "complete", result: {reply: {text: "Fresh practice"}}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  app.node("#lesson-message").value = "Original question";
  app.node("#lesson-message").listeners.input();
  await app.run("morePractice()");
  const retry = app.node("#notice").children.at(-1);
  await app.run('navigate("lesson", "newer")');
  fail = false;
  await retry.listeners.click();
  const requests = app.requests.filter(request => request.body?.action === "message");
  assert.equal(requests.length, 2);
  assert.equal(requests[1].body.lesson_id, "older");
  assert.equal(app.run("currentRoute.lessonId"), "older");
  assert.equal(app.node("#lesson-message").value, "Original question");
});

for (const changedSession of [false, true]) {
  test(`background completion ${changedSession ? "cannot enter another session" : "preserves a pending chat reply and scroll"}`, async () => {
    let finish;
    const completed = completedLesson();
    const completedLearning = {...sessionPayload().learning, lessons: [completed]};
    const app = application("#lesson/older", async (path) => {
      if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({...detail(), lesson: completed})};
      return new Promise(resolve => { finish = () => resolve(streamResponse([{type: "complete", result: {reply: {text: "Saved"}, learning: completedLearning}}])); });
    });
    app.run(`applySession(${JSON.stringify(sessionPayload())})`);
    await app.run("renderView()");
    // Begin with unfinished practice, then receive completion while elsewhere.
    app.run('renderLearning({lessons: []}); renderConversation([])');
    const pendingAnswer = app.run('submitExerciseAnswer("An answer", "one")');
    await app.run('navigate("chat")');
    if (changedSession) app.run(`applySession(${JSON.stringify(sessionPayload("two"))})`);
    const pendingMessage = app.run('appendMessage(elements.messages, "assistant", "Preparing…", {pending: true})');
    app.node("#message").value = "Unsent draft";
    app.node("#messages").scrollTop = 29;
    finish();
    await pendingAnswer;
    assert.equal(app.node("#messages").children.at(-1), pendingMessage);
    assert.equal(app.node("#messages").scrollTop, 29);
    assert.equal(app.node("#message").value, "Unsent draft");
    assert.equal(app.node("#messages").querySelectorAll(".completed-lesson").length, changedSession ? 0 : 1);
  });
}

test("lesson sidebar and main card open stored content directly", async () => {
  const app = application("#chat", async (path) => ({ok: true, json: async () => detail()}));
  app.run(`applySession(${JSON.stringify(sessionPayload())}); renderConversation([{
    role: "assistant", content: "I made a lesson.", lesson_cards: [{id: "older", title: "Subject pronouns"}]
  }]);`);
  const card = app.node("#messages").children[0].children.at(-1);
  await card.children.at(-1).listeners.click();
  assert.equal(app.run("location.hash"), "#lesson/older");
  assert.equal(app.node("#lesson-view").hidden, false);
  assert.equal(app.node("#lesson-document").children[1].textContent, lesson.title);
  assert.equal(app.requests[0].path, "/api/lessons/older?session=one");
  assert.equal(app.node("#learning-path").children[0].children[0].getAttribute("aria-current"), "page");
  assert.equal(app.node("#learning-path").children[1].children[0].getAttribute("aria-current"), null);
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

test("selected quote accompanies a question, survives in history and clears on success", async () => {
  let savedConversation = [];
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({...detail(), conversation: savedConversation})};
    savedConversation = [
      {role: "user", content: "Why ich?", section_id: "forms", selected_text: "Use ich for I.", action: "message"},
      {role: "assistant", content: "Because the speaker is I.", section_id: "forms"},
    ];
    return streamResponse([{type: "stage", text: "Considering the section…"}, {type: "complete", result: {reply: {text: "Because the speaker is I."}}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const section = app.node("#lesson-document").children[3];
  assert.equal(section.children[0].children.length, 1);
  app.select(section.children[1], "Use ich for I.");
  assert.equal(app.node("#selected-reference-label").textContent, "Section: The forms");
  assert.equal(app.node("#selected-reference-quote").textContent, "Use ich for I.");
  assert.equal(app.node("#lesson-layout").dataset.tab, "lesson");
  app.select(section.children[1], "");
  assert.equal(app.node("#selected-reference").hidden, false);
  app.node("#lesson-message").value = "Why ich?";
  await app.run('submitLessonTurn("Why ich?")');
  assert.deepEqual(JSON.parse(JSON.stringify(app.requests[1].body)), {
    session: "one", lesson_id: "older", message: "Why ich?", action: "message", section_id: "forms", selected_text: "Use ich for I.",
  });
  assert.equal(app.node("#lesson-messages").children[0].children[0].children[1].textContent, "About The forms");
  assert.equal(app.node("#lesson-messages").children[0].querySelector(".message-selection").textContent, "Use ich for I.");
  assert.equal(app.node("#selected-reference").hidden, true);
  assert.equal(app.run("lessonState().selected"), null);
  assert.equal(app.node("#lesson-progress").textContent, "Saved to this lesson.");
  assert.equal(app.node("#messages").children[0].className, "welcome");
  await app.run('submitLessonTurn("What else should I remember?")');
  assert.equal(app.requests[3].body.selected_text, undefined);
  assert.equal(app.requests[3].body.section_id, undefined);
});

test("exercise submission ignores an attached quote and completed exercise text remains selectable", async () => {
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
  app.select(app.node("#lesson-document").children[3], "Use ich for I.");
  assert.equal(form.children[0].hidden, false);
  assert.equal(form.children[1].hidden, false);
  assert.equal(form.children[2].children[0].hidden, false);
  form.children[1].value = "Ich bin hier.";
  await form.listeners.submit({preventDefault() {}});
  assert.equal(app.requests[1].body.action, "answer");
  assert.equal(app.requests[1].body.exercise_id, "one");
  assert.equal(app.requests[1].body.lesson_id, "older");
  assert.equal(app.requests[1].body.selected_text, undefined);
  assert.equal(app.requests[1].body.section_id, undefined);
  const refreshed = app.node("#lesson-exercises").children[0];
  assert.equal(refreshed.children[0].children[1].textContent, "Submitted");
  assert.equal(refreshed.querySelector(".exercise-answer-form"), null);
  assert.equal(refreshed.querySelector(".exercise-actions"), null);
  assert.equal(refreshed.querySelector(".exercise-attempt").children[0].textContent, "Your answer: Ich bin hier.");
  assert.equal(refreshed.querySelector(".exercise-attempt").children[1].innerHTML, "Correct.");
  assert.equal(app.run("lessonState().selected.section_id"), "forms");
  app.select(refreshed.querySelector(".exercise-attempt").children[1], "Correct.");
  assert.equal(app.node("#selected-reference-label").textContent, "Exercise: Introduce yourself");
  await app.run('submitLessonTurn("Could you explain why?")');
  assert.equal(app.requests[3].body.action, "message");
  assert.equal(app.requests[3].body.selected_text, "Correct.");
  assert.equal(app.requests[3].body.exercise_id, "one");
});

test("viewing an older lesson does not change the chat shortcut's teaching focus", async () => {
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
  await app.node("#back-to-conversation").listeners.click();
  await app.node("#continue-learning").listeners.click();
  assert.equal(app.requests.at(-1).body.origin_lesson_id, "newer");
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
  first.select(first.node("#lesson-exercises").children[0].children[3], "Write a sentence.");
  first.node("#discussion-tab").listeners.click();
  const second = application("#lesson/older", respond, browser);
  second.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await second.run("renderView()");
  assert.equal(second.node("#lesson-message").value, "unfinished");
  assert.equal(second.node("#lesson-reading").scrollTop, 410);
  assert.equal(second.node("#selected-reference-label").textContent, "Exercise: Introduce yourself");
  assert.equal(second.node("#selected-reference-quote").textContent, "Write a sentence.");
  assert.equal(second.node("#lesson-layout").dataset.tab, "discussion");
  await second.run('manageSession("delete", {session: "one"})');
  assert.equal(createLessonState(browser).get("one", "older").draft, "");
  assert.equal(createLessonState(browser).get("one", "older").selected, null);
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

test("selection replacement, boundaries, removal and length limits", async () => {
  const app = application("#lesson/older", async () => ({ok: true, json: async () => detail()}));
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const section = app.node("#lesson-document").children[3];
  const recap = app.node("#lesson-document").children.at(-1);
  const textNode = {nodeType: 3, parentElement: section.children[1]};
  app.select(textNode, "ch");
  assert.equal(app.node("#selected-reference-label").textContent, "Section: The forms");
  assert.equal(app.node("#selected-reference-quote").textContent, "ch");
  app.select(section.children[1], "ich");
  app.select(section.children[1], "ich through recap", recap);
  assert.equal(app.node("#selected-reference-label").textContent, "Selected lesson text");
  assert.equal(app.run("lessonState().selected.section_id"), undefined);
  assert.equal(app.node("#selected-reference-quote").textContent, "ich through recap");
  app.select(app.node("#lesson-message"), "outside");
  assert.equal(app.node("#selected-reference-quote").textContent, "ich through recap");
  const form = app.node("#lesson-exercises").children[0].children.at(-1);
  app.select(form.children[1], "unfinished answer");
  assert.equal(app.node("#selected-reference-quote").textContent, "ich through recap");
  app.node("#remove-reference").listeners.click();
  assert.equal(app.run("lessonState().selected"), null);
  assert.equal(app.node("#selected-reference").hidden, true);
  app.select(section, "x".repeat(4001));
  assert.match(app.node("#lesson-selection-status").textContent, /shorter passage/);
  assert.equal(app.run("lessonState().selected"), null);
  app.select(section, "😀".repeat(4000));
  assert.equal(app.node("#selected-reference").hidden, false);
  assert.equal(app.requests.length, 1);
});

test("failed discussion keeps the quote and draft for retry", async () => {
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => detail()};
    return streamResponse([{type: "error", error: "Try again"}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  app.select(app.node("#lesson-document").children[3], "ich");
  app.node("#lesson-message").value = "Why?";
  app.node("#lesson-message").listeners.input();
  await app.run('submitLessonTurn("Why?")');
  assert.equal(app.run("lessonState().selected.text"), "ich");
  assert.equal(app.run("lessonState().draft"), "Why?");
  assert.equal(app.node("#selected-reference").hidden, false);
});

test("committed discussion clears its quote even if refreshing the lesson fails", async () => {
  let committed = false;
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) {
      if (committed) throw new Error("Refresh failed");
      return {ok: true, json: async () => detail()};
    }
    committed = true;
    return streamResponse([{type: "complete", result: {reply: {text: "Explanation"}}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  app.select(app.node("#lesson-document").children[3], "ich");
  await app.run('submitLessonTurn("Why?")');
  assert.equal(app.run("lessonState().selected"), null);
  assert.equal(app.node("#selected-reference").hidden, true);
  const user = app.node("#lesson-messages").children.find((child) => child.className === "message user");
  assert.equal(user.querySelector(".message-selection").textContent, "ich");
});

test("inline answers require every blank, restore drafts, survive failure and become text on completion", async () => {
  const browser = storage();
  let submitted = "";
  let fail = true;
  const inlineLesson = {
    ...lesson,
    exercises: [{id: "inline", title: "Replace the subject", context: "Short sentences", task: "Write the subject pronouns.\n\n1. {{blank}} [Ben] sings.\n2. {{blank}} [Mia] sings."}],
  };
  const respond = async (path, options) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({
      lesson: inlineLesson, conversation: [],
      exercise_status: submitted ? {inline: {completed: true, assessments: [{learner_response: submitted, feedback: "", blank_results: [
        {blank_number: 1, correct: true, feedback: ""}, {blank_number: 2, correct: true, feedback: ""},
      ]}]}} : {},
    })};
    if (fail) return streamResponse([{type: "error", error: "Try again"}]);
    submitted = JSON.parse(options.body).message;
    return streamResponse([{type: "complete", result: {reply: {text: "Correct."}}}]);
  };
  const first = application("#lesson/older", respond, browser);
  first.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await first.run("renderView()");
  let card = first.node("#lesson-exercises").children[0];
  assert.equal(card.querySelector("textarea"), null);
  const fields = card.querySelectorAll("input");
  assert.equal(fields.length, 2);
  assert.equal(fields[0].required, true);
  assert.equal(fields[0].getAttribute("form"), card.querySelector("form").id);
  assert.equal(fields[1].getAttribute("aria-label"), "Blank 2 of 2");
  fields[0].value = "er";
  fields[0].listeners.input();
  await card.querySelector("form").listeners.submit({preventDefault() {}});
  assert.match(card.querySelector(".exercise-answer-error").textContent, /every blank/);
  assert.equal(first.requests.length, 1);

  const restored = application("#lesson/older", respond, browser);
  restored.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await restored.run("renderView()");
  card = restored.node("#lesson-exercises").children[0];
  const restoredFields = card.querySelectorAll("input");
  assert.equal(restoredFields[0].value, "er");
  assert.equal(restoredFields[1].value, "");
  restoredFields[1].value = "sie";
  restoredFields[1].listeners.input();
  await card.querySelector("form").listeners.submit({preventDefault() {}});
  assert.equal(card.querySelector(".exercise-progress").textContent, "Try again");
  assert.equal(restoredFields[1].value, "sie");
  assert.equal(restored.run("lessonState().selected"), null);
  fail = false;
  await card.querySelector("form").listeners.submit({preventDefault() {}});
  assert.equal(submitted, "Blank 1: er\nBlank 2: sie");
  assert.equal(restored.requests[2].body.action, "answer");
  assert.equal(restored.requests[2].body.exercise_id, "inline");
  assert.equal(restored.requests[2].body.selected_text, undefined);
  const completed = restored.node("#lesson-exercises").children[0];
  assert.equal(completed.querySelector("input"), null);
  assert.equal(completed.querySelector("form"), null);
  assert.deepEqual(completed.querySelectorAll(".exercise-blank").map((blank) => blank.textContent), ["er", "sie"]);
  assert.ok(completed.querySelectorAll(".exercise-blank").every((blank) => blank.classList.contains("correct")));
  assert.equal(completed.querySelector(".exercise-attempt"), null);
  assert.equal(restored.run('lessonState().answers.inline'), "");
});

test("incorrect inline answers are final and retain their submitted values", async () => {
  const response = "Blank 1: du\nBlank 2: sie";
  const app = application("#lesson/older", async () => ({ok: true, json: async () => ({
    lesson: {...lesson, exercises: [{id: "inline", title: "Pronouns", task: "1. {{blank}} [Ben] sings.\n2. {{blank}} [Mia] sings."}]},
    conversation: [], exercise_status: {inline: {completed: false, assessments: [{learner_response: response, feedback: "", blank_results: [
      {blank_number: 1, correct: false, feedback: "Use **er** for Ben."},
      {blank_number: 2, correct: true, feedback: ""},
    ]}]}},
  })}));
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const card = app.node("#lesson-exercises").children[0];
  assert.equal(card.querySelector("input"), null);
  assert.deepEqual(card.querySelectorAll(".exercise-blank").map((blank) => blank.textContent), ["du", "sie"]);
  assert.equal(card.children[0].children[1].textContent, "Submitted");
  const [wrong, right] = card.querySelectorAll(".exercise-blank");
  assert.ok(wrong.classList.contains("incorrect"));
  assert.ok(right.classList.contains("correct"));
  assert.equal(wrong.getAttribute("aria-label"), "Blank 1: du — Incorrect");
  assert.equal(right.getAttribute("aria-label"), "Blank 2: sie — Correct");
  assert.equal(wrong.children[0].textContent, "✗");
  assert.equal(right.children[0].textContent, "✓");
  const feedback = card.querySelector(".exercise-attempt");
  assert.equal(feedback.children.length, 1);
  assert.equal(feedback.children[0].innerHTML, "**Blank 1:** Use **er** for Ben.");
  assert.equal(wrong.getAttribute("aria-describedby"), feedback.children[0].id);
  assert.equal(app.descendants(card).some((node) => node.textContent.startsWith("Your answer:")), false);
  await app.run('refreshLesson("older")');
  assert.ok(app.node("#lesson-exercises").children[0].querySelectorAll(".exercise-blank")[0].classList.contains("incorrect"));
});

test("legacy inline results remain neutral and preserve feedback without duplicating mapped answers", async () => {
  for (const response of ["Blank 1: du\nBlank 2: sie", "du and sie", "Blank 1: du\nBlank 2: sie\nMore context"]) {
    const app = application("#lesson/older", async () => ({ok: true, json: async () => ({
      lesson: {...lesson, exercises: [{id: "inline", title: "Pronouns", task: "1. {{blank}} [Ben]\n2. {{blank}} [Mia]"}]},
      conversation: [], exercise_status: {inline: {submitted: true, assessments: [{learner_response: response, feedback: "Use er for Ben."}]}},
    })}));
    app.run(`applySession(${JSON.stringify(sessionPayload())})`);
    await app.run("renderView()");
    const card = app.node("#lesson-exercises").children[0];
    assert.ok(card.querySelectorAll(".exercise-blank").every((blank) => !blank.classList.contains("correct") && !blank.classList.contains("incorrect")));
    const feedback = card.querySelector(".exercise-attempt");
    assert.equal(feedback.children.at(-1).innerHTML, "Use er for Ben.");
    const mapped = response === "Blank 1: du\nBlank 2: sie";
    assert.equal(feedback.children.length, mapped ? 1 : 2);
    if (!mapped) assert.equal(feedback.children[0].textContent, `Your answer: ${response}`);
  }
});

test("answer submission leaves discussion alone while pending, after success and on reload", async () => {
  let finish;
  const conversation = [
    {role: "user", turn_id: "question", action: "message", exercise_id: "one", content: "What should I write?"},
    {role: "assistant", turn_id: "question", action: "message", exercise_id: "one", content: "Write a sentence about yourself."},
  ];
  let status = {};
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({...detail(), conversation, exercise_status: status})};
    return new Promise((resolve) => { finish = () => {
      conversation.push(
        {role: "user", turn_id: "answer", action: "answer", exercise_id: "one", content: "Ich bin hier."},
        {role: "assistant", turn_id: "answer", action: "answer", exercise_id: "one", content: "Correct."},
      );
      status = {one: {completed: true, assessments: [{turn_id: "answer", learner_response: "Ich bin hier.", feedback: "Correct."}]}};
      resolve(streamResponse([{type: "stage", text: "Checking…"}, {type: "complete", result: {reply: {text: "Correct."}}}]));
    };});
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const messages = app.node("#lesson-messages");
  messages.scrollTop = 42;
  const before = [...messages.children];
  const pending = app.run('submitLessonTurn("Ich bin hier.", "answer", {exercise_id: "one"})');
  assert.deepEqual(messages.children, before);
  assert.equal(app.node("#lesson-exercises").children[0].querySelector(".exercise-progress").textContent, "Checking your answer…");
  finish();
  await pending;
  assert.equal(messages.children.length, 2);
  assert.equal(messages.children[0].querySelector(".bubble").textContent, "What should I write?");
  assert.equal(messages.scrollTop, 42);
  assert.equal(app.run("lessonConversation.length"), 4);
  const attempts = app.node("#lesson-exercises").children[0].querySelectorAll(".exercise-attempt");
  assert.equal(attempts.length, 1);
  assert.equal(attempts[0].children[0].textContent, "Your answer: Ich bin hier.");
  assert.equal(attempts[0].children[1].innerHTML, "Correct.");
  await app.run('refreshLesson("older")');
  assert.equal(messages.children.length, 2);
  assert.equal(messages.children[0].querySelector(".bubble").textContent, "What should I write?");
});

test("unassessed answer clarification stays on its exercise instead of discussion", async () => {
  const app = application("#lesson/older", async () => ({ok: true, json: async () => ({
    ...detail(), conversation: [
      {role: "user", turn_id: "answer", action: "answer", exercise_id: "one", content: "Perhaps I?"},
      {role: "assistant", turn_id: "answer", action: "answer", exercise_id: "one", content: "Please write a complete sentence."},
    ],
  })}));
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  assert.equal(app.node("#lesson-messages").children.length, 1);
  assert.equal(app.node("#lesson-messages").children[0].className, "discussion-empty");
  const card = app.node("#lesson-exercises").children[0];
  assert.equal(card.children[0].children[1].textContent, "Submitted");
  assert.equal(card.querySelector(".exercise-attempt").children[1].innerHTML, "Please write a complete sentence.");
  assert.equal(card.querySelector("textarea"), null);
});

for (const committed of [false, true]) {
  test(`answer ${committed ? "refresh failure" : "submission failure"} never inserts chat messages`, async () => {
    let submitted = false;
    const app = application("#lesson/older", async (path) => {
      if (path.startsWith("/api/lessons/")) {
        if (submitted && committed) throw new Error("Refresh failed");
        return {ok: true, json: async () => detail()};
      }
      submitted = true;
      return streamResponse(committed
        ? [{type: "complete", result: {reply: {text: "Correct."}}}]
        : [{type: "error", error: "Please retry"}]);
    });
    app.run(`applySession(${JSON.stringify(sessionPayload())})`);
    await app.run("renderView()");
    const before = [...app.node("#lesson-messages").children];
    await app.run('submitLessonTurn("Ich bin hier.", "answer", {exercise_id: "one"})');
    assert.deepEqual(app.node("#lesson-messages").children, before);
    assert.match(app.node("#lesson-exercises").children[0].querySelector(".exercise-progress").textContent,
      committed ? /Saved.*Reopen/ : /Please retry/);
  });
}

test("checking one answer permits editing and submitting another without rebuilding its fields", async () => {
  const finish = new Map();
  const app = application("#lesson/older", async (path, options) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => detail()};
    const {exercise_id} = JSON.parse(options.body);
    return new Promise((resolve) => finish.set(exercise_id, () => resolve(streamResponse([
      {type: "complete", result: {reply: {text: "Try again."}}},
    ]))));
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const cards = app.node("#lesson-exercises").children;
  const otherField = cards[1].querySelector("textarea");
  const first = app.run('submitLessonTurn("First", "answer", {exercise_id: "one"})');
  assert.equal(app.run("busy"), false);
  assert.equal(cards[0].querySelector("textarea").disabled, true);
  assert.equal(cards[0].querySelector("button").disabled, true);
  assert.equal(otherField.disabled, false);
  assert.equal(app.node("#lesson-message").disabled, false);
  otherField.value = "My next answer";
  otherField.listeners.input();
  await app.run('submitLessonTurn("Duplicate", "answer", {exercise_id: "one"})');
  assert.equal(app.requests.filter((request) => request.body?.action === "answer").length, 1);
  app.node("#lesson-message").value = "A question in progress";
  app.node("#lesson-message").listeners.input();
  const second = app.run('submitLessonTurn("Second", "answer", {exercise_id: "two"})');
  finish.get("one")();
  await first;
  assert.equal(app.node("#lesson-exercises").children[1].querySelector("textarea"), otherField);
  assert.equal(otherField.value, "My next answer");
  assert.equal(app.node("#lesson-message").value, "A question in progress");
  const count = app.requests.length;
  await app.run('submitLessonTurn("Retry", "answer", {exercise_id: "one"})');
  assert.equal(app.requests.length, count);
  assert.equal(otherField.disabled, true, "another completion must not unlock a pending answer");
  finish.get("two")();
  await second;
  assert.equal(app.node("#lesson-exercises").children[1].querySelector("textarea"), null);
});

test("background answers survive navigation and update only their original lesson and draft", async () => {
  let finish;
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({
      ...detail(), lesson: {...lesson, id: path.includes("newer") ? "newer" : "older"},
    })};
    return new Promise((resolve) => { finish = () => resolve(streamResponse([
      {type: "complete", result: {reply: {text: "Saved"}}},
    ])); });
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  app.run('updateLessonState({answers: {one: "Old answer"}})');
  const pending = app.run('submitLessonTurn("Old answer", "answer", {exercise_id: "one"})');
  await app.run('navigate("chat")');
  assert.equal(app.run("currentRoute.view"), "chat");
  await app.run('navigate("lesson", "older")');
  assert.equal(app.node("#lesson-exercises").children[0].querySelector("textarea").disabled, true);
  assert.equal(app.node("#lesson-exercises").children[0].querySelector(".exercise-progress").textContent, "Checking your answer…");
  await app.run('navigate("lesson", "newer")');
  app.run('updateLessonState({answers: {one: "New lesson draft"}})');
  const newCard = app.node("#lesson-exercises").children[0];
  finish();
  await pending;
  assert.equal(app.run("lessonData.id"), "newer");
  assert.equal(app.node("#lesson-exercises").children[0], newCard);
  assert.equal(app.run('lessonState().answers.one'), "New lesson draft");
  assert.equal(app.run('savedWork.get(activeSession, "older").answers.one'), "");
});

test("lesson results appear only after a full set and keep earlier practice results", async () => {
  const app = application("#lesson/older", async () => ({ok: true, json: async () => detail()}));
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  const panel = app.node("#lesson-results");
  assert.equal(panel.hidden, true);
  app.run(`lessonData.practice_results = [{number: 1, finished: false, submitted: 1, percentage: null}]; renderLessonResults()`);
  assert.equal(panel.hidden, true);
  app.run(`lessonData.practice_results = [{number: 1, finished: true, submitted: 2, correct: 6, total: 8, percentage: 75, scoring: "parts", review_at: "2099-01-01T12:00:00+00:00"}]; renderLessonResults(); updateLessonResultInPath(lessonData)`);
  assert.equal(panel.hidden, false);
  assert.equal(panel.children[0].querySelector(".lesson-score").textContent, "75% correct");
  assert.match(panel.children[0].children[2].textContent, /6 of 8 answer parts/);
  assert.match(panel.children[0].children.at(-1).textContent, /sooner/);
  assert.match(app.node("#learning-path").children[0].children[0].textContent, /75%/);
  app.run(`lessonData.practice_results.push({number: 2, finished: true, correct: 2, total: 2, percentage: 100, scoring: "parts"}); renderLessonResults(); updateLessonResultInPath(lessonData)`);
  assert.deepEqual(panel.children.map((entry) => entry.querySelector(".lesson-score").textContent), ["75% correct", "100% correct"]);
  assert.match(app.node("#learning-path").children[0].children[0].textContent, /100%/);
});

test("saved answers cannot be sent twice when refreshing the card fails", async () => {
  let sent = false;
  const app = application("#lesson/older", async (path) => {
    if (path.startsWith("/api/lessons/")) {
      if (sent) throw new Error("Read failed");
      return {ok: true, json: async () => detail()};
    }
    sent = true;
    return streamResponse([{type: "complete", result: {reply: {text: "Saved"}}}]);
  });
  app.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await app.run("renderView()");
  await app.run('submitLessonTurn("Answer", "answer", {exercise_id: "one"})');
  const count = app.requests.length;
  await app.run('submitLessonTurn("Correction", "answer", {exercise_id: "one"})');
  assert.equal(app.requests.length, count);
  assert.equal(app.node("#lesson-exercises").children[0].querySelector("button").disabled, true);
});

test("numbered items have expanding answer blanks with one submission and durable drafts", async () => {
  const browser = storage();
  let submitted = "";
  let fail = true;
  const numberedLesson = {...lesson, exercises: [
    {id: "numbered", title: "Build new pairs", task: "Give the form and its meaning.\n\n1. Speak to several friends.\n2. Describe one woman.\n3. Describe several listeners.\n4. Address a stranger formally."},
    ...lesson.exercises,
  ]};
  const respond = async (path, options) => {
    if (path.startsWith("/api/lessons/")) return {ok: true, json: async () => ({
      lesson: numberedLesson, conversation: [], exercise_status: submitted ? {numbered: {submitted: true, assessments: [{learner_response: submitted, feedback: "Use sie haben for the listeners."}]}} : {},
    })};
    if (fail) return streamResponse([{type: "error", error: "Try again"}]);
    submitted = JSON.parse(options.body).message;
    return streamResponse([{type: "complete", result: {reply: {text: "Saved"}}}]);
  };
  const first = application("#lesson/older", respond, browser);
  first.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await first.run("renderView()");
  let card = first.node("#lesson-exercises").children[0];
  const fields = card.querySelectorAll("textarea");
  assert.equal(fields.length, 4);
  assert.equal(card.querySelectorAll("button").length, 1);
  assert.equal(card.querySelectorAll("form").length, 1);
  assert.ok(fields.every((field) => field.parentElement.className === "exercise-item"));
  assert.ok(fields.every((field) => field.getAttribute("form") === card.querySelector("form").id));
  assert.equal(fields[3].getAttribute("aria-label"), "Answer 4 of 4");
  assert.ok(fields.every((field) => field.rows === 1 && field.required));
  fields[0].value = "ihr habt\nyou have";
  fields[0].scrollHeight = 70;
  fields[0].listeners.input();
  assert.equal(fields[0].style.height, "72px");
  first.select(fields[0], "ihr habt");
  assert.equal(first.run("lessonState().selected"), null);
  await card.querySelector("form").listeners.submit({preventDefault() {}});
  assert.match(card.querySelector(".exercise-answer-error").textContent, /every numbered item/);
  assert.equal(first.requests.length, 1);

  const restored = application("#lesson/older", respond, browser);
  restored.run(`applySession(${JSON.stringify(sessionPayload())})`);
  await restored.run("renderView()");
  card = restored.node("#lesson-exercises").children[0];
  const restoredFields = card.querySelectorAll("textarea");
  assert.equal(restoredFields[0].value, "ihr habt\nyou have");
  assert.equal(restoredFields[1].value, "");
  const values = ["ihr habt\nyou have", "sie hat — she has", '<script>bad()</script>\nItem 4: is part of this answer', "Sie haben — you have"];
  restoredFields.forEach((field, index) => {field.value = values[index]; field.listeners.input();});
  await card.querySelector("form").listeners.submit({preventDefault() {}});
  assert.equal(card.querySelector(".exercise-progress").textContent, "Try again");
  assert.deepEqual(restoredFields.map((field) => field.value), values);
  assert.ok(restoredFields.every((field) => !field.disabled));
  const otherField = restored.node("#lesson-exercises").children[1].querySelector("textarea");
  otherField.value = "Another draft";
  otherField.listeners.input();
  fail = false;
  const pending = card.querySelector("form").listeners.submit({preventDefault() {}});
  assert.ok(restoredFields.every((field) => field.disabled));
  assert.equal(otherField.disabled, false);
  await pending;
  assert.deepEqual(parseItemAnswers(submitted, 4), values);
  assert.equal(restored.requests[2].body.action, "answer");
  assert.equal(restored.requests[2].body.exercise_id, "numbered");
  card = restored.node("#lesson-exercises").children[0];
  assert.equal(card.querySelector("textarea"), null);
  assert.equal(card.querySelector("form"), null);
  assert.deepEqual(card.querySelectorAll(".exercise-item-answer").map((answer) => answer.textContent), values);
  assert.equal(card.querySelector("script"), null);
  assert.equal(card.querySelector(".exercise-attempt").children.length, 1);
  assert.equal(restored.node("#lesson-exercises").children[1].querySelector("textarea"), otherField);
  assert.equal(restored.run('lessonState().answers.numbered'), "");
  assert.equal(otherField.value, "Another draft");
  await restored.run('refreshLesson("older")');
  assert.deepEqual(restored.node("#lesson-exercises").children[0].querySelectorAll(".exercise-item-answer").map((answer) => answer.textContent), values);
});

test("older numbered-task drafts and submissions keep their full shared answer", async () => {
  const response = "My answer covers both numbered prompts.";
  const numberedLesson = {...lesson, exercises: [{id: "numbered", title: "Explain", task: "1. First prompt\n2. Second prompt"}]};
  for (const submitted of [false, true]) {
    const app = application("#lesson/older", async () => ({ok: true, json: async () => ({
      lesson: numberedLesson, conversation: [], exercise_status: submitted ? {numbered: {submitted: true, assessments: [{learner_response: response, feedback: "Feedback"}]}} : {},
    })}));
    app.run(`applySession(${JSON.stringify(sessionPayload())}); savedWork.update("one", "older", {answers: {numbered: ${JSON.stringify(response)}}})`);
    await app.run("renderView()");
    const card = app.node("#lesson-exercises").children[0];
    if (submitted) {
      assert.equal(card.querySelector("textarea"), null);
      assert.equal(card.querySelector(".exercise-attempt").children[0].textContent, `Your answer: ${response}`);
    } else {
      assert.equal(card.querySelectorAll("textarea").length, 1);
      assert.equal(card.querySelector("textarea").value, response);
    }
  }
});
