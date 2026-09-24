import assert from "node:assert/strict";
import { test } from "node:test";
import { createExerciseController } from "../src/milai/web/exercise-controller.js";

test("drafts and answer status stay with their session and exercise", async () => {
  const calls = [];
  const controller = createExerciseController(async (body) => {
    calls.push(body);
    return { status: { assessments: [{id: "attempt"}], completed: false } };
  });
  controller.setSession("one");
  controller.open({ id: "exercise-a" });
  controller.setDraft("my answer");
  await controller.answer("my answer");
  controller.close();
  controller.open({ id: "exercise-a" });
  assert.equal(controller.draft, "my answer");
  assert.equal(controller.status.assessments.length, 1);
  assert.equal(controller.canContinue, true);
  controller.setSession("two");
  controller.open({ id: "exercise-a" });
  assert.equal(controller.draft, "");
  assert.deepEqual(calls[0], {
    session: "one", exercise_id: "exercise-a", action: "answer", text: "my answer",
  });
});

test("failed answer preserves draft and a pending request cannot duplicate", async () => {
  let reject;
  let calls = 0;
  const controller = createExerciseController(() => {
    calls++;
    return new Promise((_, fail) => { reject = fail; });
  });
  controller.setSession("one");
  controller.open({ id: "exercise-a" });
  controller.setDraft("exact answer  ");
  const first = controller.answer(controller.draft);
  assert.equal(await controller.answer(controller.draft), null);
  reject(new Error("network"));
  await assert.rejects(first);
  assert.equal(calls, 1);
  assert.equal(controller.draft, "exact answer  ");
  assert.equal(controller.canContinue, false);
});
