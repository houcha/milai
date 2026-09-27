import assert from "node:assert/strict";
import { test } from "node:test";

import { renderMarkdown, renderExerciseMarkdown } from "../src/milai/web/markdown.bundle.js";

test("renders the tutor's numbered lesson, nested bullets, and TeX arrow", () => {
  const source = [
    "1. **Present Tense Verb Conjugation**",
    "In German, verbs change.",
    "",
    "   - **ich** (I) $\\rightarrow$ add **-e**",
    "",
    "2. **Poetic Word Order**",
    "The verb moves.",
  ].join("\n");
  const html = renderMarkdown(source);

  assert.match(html, /<ol>/);
  assert.match(html, /<strong>Present Tense Verb Conjugation<\/strong>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<mo>→<\/mo>/);
  assert.match(html, /Poetic Word Order/);
});

test("escapes model-supplied HTML and unsafe links", () => {
  const html = renderMarkdown(
    '<script>alert(1)</script> [unsafe](javascript:alert(1)) [safe](https://example.com)',
  );

  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /href="https:\/\/example\.com"/);
});

test("renders exercise emphasis and numbered conjugations", () => {
  const html = renderMarkdown("Complete **hören**:\n1. ich höre\n2. du hörst");
  assert.match(html, /<strong>hören<\/strong>/);
  assert.match(html, /<ol>/);
  assert.match(html, /<li>ich höre<\/li>/);
});

test("inline blanks retain ordered lists, context and formatting", () => {
  const html = renderExerciseMarkdown("Replace each subject.\n\n1. {{blank}} [Ben] sings.\n2. **{{blank}}** [Mia] sings.\n3. {{blank}} and {{blank}}.");
  assert.match(html, /<ol>/);
  assert.equal((html.match(/class="exercise-blank"/g) || []).length, 4);
  assert.match(html, /data-blank-number="1">____<\/span> \[Ben\] sings/);
  assert.match(html, /<strong><span class="exercise-blank" data-blank-number="2"/);
  assert.match(html, /data-blank-number="4"/);
  assert.doesNotMatch(html, /<input|<script/);
  assert.match(renderExerciseMarkdown("{{blank}}"), /data-blank-number="1"/);
});

test("blank markers are inert outside exercise prose and model HTML stays escaped", () => {
  assert.doesNotMatch(renderMarkdown("{{blank}}"), /class="exercise-blank"/);
  const html = renderExerciseMarkdown('`{{blank}}` [{{blank}}](https://example.com)\n\n```text\n{{blank}}\n```\n\n<input value="answer" onfocus="alert(1)">\n\n{{blank}}');
  assert.doesNotMatch(html, /class="exercise-blank"|\{\{blank\}\}/);
  assert.doesNotMatch(html, /<input/);
  assert.match(html, /&lt;input/);
});

test("numbered exercises get one answer location per top-level item", () => {
  const source = "Give a form and explain it.\n\n1. First prompt\n   1. Name the form.\n   2. Give its meaning.\n2. **Second** prompt\n\nAnother group:\n\n3. Third prompt";
  const html = renderExerciseMarkdown(source);
  assert.equal((html.match(/class="exercise-item"/g) || []).length, 3);
  assert.match(html, /<li class="exercise-item" data-item-number="1">/);
  assert.match(html, /<li class="exercise-item" data-item-number="3">/);
  assert.match(html, /<li>Name the form\.<\/li>/);
  assert.match(html, /<strong>Second<\/strong>/);
  assert.doesNotMatch(html, /<textarea|<input/);
  assert.doesNotMatch(renderMarkdown(source), /class="exercise-item"/);
});

test("only exercise enumerations gain answer locations, keeping explicit blanks intact", () => {
  for (const source of [
    "Write a paragraph.", "- First\n- Second", "> 1. Quoted\n> 2. Example",
    "```text\n1. Code\n2. Example\n```", "1. {{blank}}\n2. {{blank}}",
    "1. `{{blank}}`\n2. {{blank}}",
    '<li class="exercise-item" data-item-number="1">Fake</li>',
  ]) assert.doesNotMatch(renderExerciseMarkdown(source), /<li class="exercise-item"/);
});
