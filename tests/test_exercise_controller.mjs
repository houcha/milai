import assert from "node:assert/strict";
import { test } from "node:test";
import { createLessonState } from "../src/milai/web/exercise-controller.js";

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
    selected: { kind: "exercise", id: "exercise" },
    readingPosition: 532,
    tab: "discussion",
  });
  state.setMainDraft("session one", "main question");
  const restored = createLessonState(browser);
  assert.deepEqual(restored.get("session one", "lesson-a"), {
    draft: "Why does this change?",
    answers: { exercise: "partial answer" },
    selected: { kind: "exercise", id: "exercise" },
    readingPosition: 532,
    tab: "discussion",
  });
  assert.equal(restored.mainDraft("session one"), "main question");
  assert.equal(restored.get("session one", "lesson-b").draft, "");
  assert.equal(restored.get("session two", "lesson-a").answers.exercise, undefined);
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
