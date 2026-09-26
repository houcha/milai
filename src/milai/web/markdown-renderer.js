import MarkdownIt from "markdown-it";
import { katex } from "@mdit/plugin-katex";

// Model output is untrusted: keep raw HTML disabled and use KaTeX's safe defaults.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })
  .use(katex, { output: "mathml" });

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

export function renderMarkdown(source) {
  return markdown.render(source);
}

export function renderExerciseMarkdown(source) {
  const env = {exerciseBlanks: true, blankCount: 0};
  const html = markdown.render(source, env);
  const expected = source.split("{{blank}}").length - 1;
  // A marker in code, math or a link must not silently shift answer numbering.
  // Keep such tasks answerable through the ordinary free-text form instead.
  return env.blankCount === expected ? html : markdown.render(source.replaceAll("{{blank}}", "____"));
}
