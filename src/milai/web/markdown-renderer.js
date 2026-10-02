import MarkdownIt from "markdown-it";
import { katex } from "@mdit/plugin-katex";

// Model output is untrusted: keep raw HTML disabled and use KaTeX's safe defaults.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })
  .use(katex, { output: "mathml" });

// Persisted spans use private delimiters only inside this renderer. The token
// rules keep their plain text intact, including punctuation and Unicode.
markdown.core.ruler.after("inline", "pronunciation", (state) => {
  if (!state.env.pronunciation) return;
  for (const block of state.tokens) {
    if (block.type !== "inline" || !block.children) continue;
    const children = [];
    for (const token of block.children) {
      if (token.type !== "text") { children.push(token); continue; }
      let cursor = 0;
      for (const match of token.content.matchAll(/\uE000([^\uE001]+)\uE001/g)) {
        const span = state.env.pronunciation.get(match[1]);
        if (!span) continue;
        if (match.index > cursor) {
          const prefix = new state.Token("text", "", 0);
          prefix.content = token.content.slice(cursor, match.index);
          children.push(prefix);
        }
        const phrase = new state.Token("pronunciation", "span", 0);
        phrase.meta = span;
        phrase.content = span.text;
        children.push(phrase);
        cursor = match.index + match[0].length;
      }
      if (cursor < token.content.length) {
        const tail = new state.Token("text", "", 0);
        tail.content = token.content.slice(cursor);
        children.push(tail);
      }
    }
    block.children = children;
  }
});
markdown.renderer.rules.pronunciation = (tokens, index) => {
  const {id, locale} = tokens[index].meta;
  const escape = markdown.utils.escapeHtml;
  return `<span class="pronunciation" role="button" tabindex="0" data-span-id="${escape(id)}" lang="${escape(locale)}" aria-label="Play AI-generated pronunciation: ${escape(tokens[index].content)}">${escape(tokens[index].content)}</span>`;
};

// Code examples retain their plain text and code styling when annotated.
for (const type of ["code_inline", "code_block", "fence"]) {
  const original = markdown.renderer.rules[type];
  markdown.renderer.rules[type] = (tokens, index, options, env, renderer) => {
    if (!env.pronunciation || !tokens[index].content.includes("\uE000")) {
      return original(tokens, index, options, env, renderer);
    }
    let cursor = 0;
    let html = "";
    const source = tokens[index].content;
    for (const match of source.matchAll(/\uE000([^\uE001]+)\uE001/g)) {
      const span = env.pronunciation.get(match[1]);
      if (!span) continue;
      html += markdown.utils.escapeHtml(source.slice(cursor, match.index));
      html += markdown.renderer.rules.pronunciation([{meta: span, content: span.text}], 0);
      cursor = match.index + match[0].length;
    }
    html += markdown.utils.escapeHtml(source.slice(cursor));
    return type === "code_inline" ? `<code>${html}</code>` : `<pre><code>${html}</code></pre>\n`;
  };
}

function pronunciationSource(source, spans) {
  const chars = Array.from(source);
  for (const span of [...spans].sort((a, b) => b.position - a.position)) {
    const length = Array.from(span.text).length;
    if (chars.slice(span.position, span.position + length).join("") !== span.text) continue;
    chars.splice(span.position, length, `\uE000${span.id}\uE001`);
  }
  return chars.join("");
}

export function renderPronunciationText(source, spans = []) {
  // Plain exercise content uses escaped segments rather than Markdown semantics.
  const chars = Array.from(source);
  let cursor = 0;
  let html = "";
  for (const span of [...spans].sort((a, b) => a.position - b.position)) {
    const end = span.position + Array.from(span.text).length;
    if (chars.slice(span.position, end).join("") !== span.text) continue;
    html += markdown.utils.escapeHtml(chars.slice(cursor, span.position).join(""));
    html += markdown.renderer.rules.pronunciation([{meta: span, content: span.text}], 0);
    cursor = end;
  }
  return html + markdown.utils.escapeHtml(chars.slice(cursor).join(""));
}

// Only exercise tasks interpret this marker. Model HTML remains disabled; the
// application replaces these fixed spans with its own form controls.
markdown.core.ruler.after("inline", "exercise_blanks", (state) => {
  if (!state.env.exerciseBlanks) return;
  let number = 0;
  for (const block of state.tokens) {
    if (block.type !== "inline" || !block.children) continue;
    const children = [];
    let linkDepth = 0;
    for (const token of block.children) {
      if (token.type === "link_open") linkDepth++;
      if (token.type === "link_close") linkDepth--;
      if (token.type !== "text" || linkDepth || !token.content.includes("{{blank}}")) {
        children.push(token);
        continue;
      }
      const parts = token.content.split("{{blank}}");
      for (const [index, content] of parts.entries()) {
        if (index) {
          const blank = new state.Token("exercise_blank", "span", 0);
          blank.meta = {number: ++number};
          children.push(blank);
        }
        if (content) {
          const text = new state.Token("text", "", 0);
          text.content = content;
          children.push(text);
        }
      }
    }
    block.children = children;
  }
  state.env.blankCount = number;
});
markdown.renderer.rules.exercise_blank = (tokens, index) =>
  `<span class="exercise-blank" data-blank-number="${tokens[index].meta.number}">____</span>`;

// Numbered tasks without explicit blanks get one app-owned answer area per item.
// Nested lists stay part of the containing prompt, not separate answer fields.
markdown.core.ruler.after("inline", "exercise_items", (state) => {
  if (!state.env.exerciseItems) return;
  let ordered = false;
  let number = 0;
  for (const token of state.tokens) {
    if (token.level === 0) ordered = token.type === "ordered_list_open";
    if (ordered && token.type === "list_item_open" && token.level === 1) {
      token.attrSet("class", "exercise-item");
      token.attrSet("data-item-number", String(++number));
    }
  }
});

export function renderMarkdown(source, spans = []) {
  return markdown.render(pronunciationSource(source, spans), {pronunciation: new Map(spans.map(span => [span.id, span]))});
}

export function renderExerciseMarkdown(source, spans = []) {
  const expected = source.split("{{blank}}").length - 1;
  // Gapped sentences stay silent even if an older payload contains span metadata.
  if (expected) spans = [];
  const env = {pronunciation: new Map(spans.map(span => [span.id, span])), exerciseBlanks: true, exerciseItems: expected === 0, blankCount: 0};
  const html = markdown.render(pronunciationSource(source, spans), env);
  // A marker in code, math or a link must not silently shift answer numbering.
  // Keep such tasks answerable through the ordinary free-text form instead.
  return env.blankCount === expected ? html : markdown.render(source.replaceAll("{{blank}}", "____"));
}
