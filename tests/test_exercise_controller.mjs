import assert from "node:assert/strict";
import { test } from "node:test";
import { createLessonState, blankAnswers, serializeBlankAnswers } from "../src/milai/web/exercise-controller.js";

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

test("unfinished work survives reload and stays in its session and lesson", () => {
  const browser = storage();
  const state = createLessonState(browser);
  state.update("session one", "lesson-a", {
    draft: "Why does this change?",
    answers: { exercise: "partial answer" },
    selected: { text: "Write a sentence.", exercise_id: "exercise" },
    readingPosition: 532,
    tab: "discussion",
  });
  state.setMainDraft("session one", "main question");
  const restored = createLessonState(browser);
  assert.deepEqual(restored.get("session one", "lesson-a"), {
    draft: "Why does this change?",
    answers: { exercise: "partial answer" },
    selected: { text: "Write a sentence.", exercise_id: "exercise" },
    readingPosition: 532,
    tab: "discussion",
  });
  assert.equal(restored.mainDraft("session one"), "main question");
  assert.equal(restored.get("session one", "lesson-b").draft, "");
  assert.equal(restored.get("session two", "lesson-a").answers.exercise, undefined);
  assert.equal(restored.get("session two", "lesson-a").selected, null);
});

test("answer updates keep other drafts and deleting a session clears only its records", () => {
  const browser = storage();
  const state = createLessonState(browser);
  state.update("one", "lesson", { answers: { a: "first", b: "second" } });
  state.update("one", "lesson", { answers: { a: "revised" } });
  state.update("two", "lesson", { draft: "keep" });
  assert.deepEqual(state.get("one", "lesson").answers, { a: "revised", b: "second" });
  state.forgetSession("one");
  assert.deepEqual(state.get("one", "lesson").answers, {});
  assert.equal(state.get("two", "lesson").draft, "keep");
});

test("invalid stored state is ignored", () => {
  const browser = storage();
  browser.setItem("milai:session:one:lesson:lesson", "not JSON");
  assert.equal(createLessonState(browser).get("one", "lesson").draft, "");
});

test("blank answers serialize in reading order and restore from drafts or assessments", () => {
  const response = serializeBlankAnswers([" ich ", "a short phrase", "日本語"]);
  assert.equal(response, "Blank 1: ich\nBlank 2: a short phrase\nBlank 3: 日本語");
  assert.deepEqual(blankAnswers(null, response, 3), ["ich", "a short phrase", "日本語"]);
  assert.deepEqual(blankAnswers(["unfinished", ""], response, 3), ["unfinished", "", ""]);
  assert.deepEqual(blankAnswers(null, "An ordinary terminal answer", 2), ["", ""]);
  assert.throws(() => serializeBlankAnswers(["ich", " "]), /every blank/);
  assert.throws(() => serializeBlankAnswers(["x".repeat(201)]), /200 characters/);
  assert.throws(() => serializeBlankAnswers(["ich\nBlank 2: du"]), /single line/);
});

test("inline drafts survive reload without leaking into another exercise or session", () => {
  const browser = storage();
  const state = createLessonState(browser);
  state.update("one", "lesson", {answers: {first: ["ich", ""], second: ["du"]}});
  state.update("one", "lesson", {answers: {first: ["ich", "sie"]}});
  const restored = createLessonState(browser);
  assert.deepEqual(restored.get("one", "lesson").answers, {first: ["ich", "sie"], second: ["du"]});
  assert.deepEqual(restored.get("two", "lesson").answers, {});
  assert.deepEqual(restored.get("one", "another-lesson").answers, {});
});

test("legacy references and invalid quotes are discarded without losing drafts", () => {
  const browser = storage();
  const state = createLessonState(browser);
  for (const selected of [
    {kind: "section", id: "forms"}, {kind: "exercise", id: "one"},
    {text: " "}, {text: "x".repeat(4001)}, {text: "quote", section_id: "forms", exercise_id: "one"},
  ]) {
    state.update("one", "lesson", {draft: "keep", answers: {one: "answer"}, readingPosition: 123, selected});
    const restored = state.get("one", "lesson");
    assert.equal(restored.selected, null);
    assert.equal(restored.draft, "keep");
    assert.equal(restored.answers.one, "answer");
    assert.equal(restored.readingPosition, 123);
  }
});
