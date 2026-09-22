import assert from "node:assert/strict";
import { test } from "node:test";

import { renderMarkdown } from "../src/milai/web/markdown.bundle.js";

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
