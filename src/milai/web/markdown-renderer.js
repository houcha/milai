import MarkdownIt from "markdown-it";
import { katex } from "@mdit/plugin-katex";

// Model output is untrusted: keep raw HTML disabled and use KaTeX's safe defaults.
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })
  .use(katex, { output: "mathml" });

export function renderMarkdown(source) {
  return markdown.render(source);
}
