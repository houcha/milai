// Browser-only state for unfinished work. The server remains the source of truth
// for lesson content, discussion, attempts, and exercise status.
export const MAX_SELECTED_TEXT = 4000;
export const MAX_BLANK_ANSWER_LENGTH = 200;
export const MAX_EXERCISE_ANSWER_LENGTH = 8000;

export function parseBlankAnswers(response, count) {
  const lines = (response || "").split("\n");
  if (!count || lines.length !== count) return null;
  const values = [];
  for (const [index, line] of lines.entries()) {
    const prefix = `Blank ${index + 1}: `;
    if (!line.startsWith(prefix)) return null;
    values.push(line.slice(prefix.length));
  }
  return values;
}

export function blankAnswers(draft, response, count) {
  if (Array.isArray(draft)) {
    return Array.from({length: count}, (_, index) => typeof draft[index] === "string" ? draft[index] : "");
  }
  return parseBlankAnswers(response, count) || Array(count).fill("");
}

export function serializeBlankAnswers(values) {
  if (!values.length || values.some((value) => !value.trim())) throw new Error("Fill in every blank before submitting.");
  if (values.some((value) => value.length > MAX_BLANK_ANSWER_LENGTH || /[\r\n]/.test(value))) {
    throw new Error("Each blank accepts a single line of up to 200 characters.");
  }
  return values.map((value, index) => `Blank ${index + 1}: ${value.trim()}`).join("\n");
}

// JSON quoting keeps multiline answers (including text like "Item 2:") intact
// in one labelled submission without inventing boundaries inside learner text.
export function serializeItemAnswers(values) {
  if (!values.length || values.some((value) => !value.trim())) throw new Error("Answer every numbered item before submitting.");
  const response = values.map((value, index) => `Item ${index + 1}: ${JSON.stringify(value.trim())}`).join("\n");
  if (response.length > MAX_EXERCISE_ANSWER_LENGTH) throw new Error("Keep the combined answers within 8,000 characters.");
  return response;
}

export function parseItemAnswers(response, count) {
  const lines = (response || "").split("\n");
  if (!count || lines.length !== count) return null;
  try {
    return lines.map((line, index) => {
      const prefix = `Item ${index + 1}: `;
      if (!line.startsWith(prefix)) throw new Error("Unmapped answer");
      const value = JSON.parse(line.slice(prefix.length));
      if (typeof value !== "string") throw new Error("Invalid answer");
      return value;
    });
  } catch { return null; }
}

function savedSelection(value) {
  if (!value || typeof value.text !== "string" || !value.text.trim()
      || [...value.text].length > MAX_SELECTED_TEXT) return null;
  if (value.section_id && value.exercise_id) return null;
  return {
    text: value.text,
    ...(typeof value.section_id === "string" ? { section_id: value.section_id } : {}),
    ...(typeof value.exercise_id === "string" ? { exercise_id: value.exercise_id } : {}),
  };
}

export function readLessonSelection(selection, root) {
  if (!selection || selection.isCollapsed || selection.rangeCount !== 1) return null;
  const range = selection.getRangeAt(0);
  const element = (node) => node.nodeType === 1 ? node : node.parentElement;
  const start = element(range.startContainer);
  const end = element(range.endContainer);
  const allowed = (node) => node && root.contains(node)
    && node.closest("[data-selection-source]")
    && !node.closest("button, input, textarea, form, [contenteditable]");
  if (!allowed(start) || !allowed(end)) return null;
  const text = selection.toString().trim();
  if (!text) return null;
  const reference = {};
  for (const [attribute, key] of [["data-section-id", "section_id"], ["data-exercise-id", "exercise_id"]]) {
    const owner = start.closest(`[${attribute}]`);
    if (owner && owner === end.closest(`[${attribute}]`)) reference[key] = owner.getAttribute(attribute);
  }
  return { text, ...reference };
}

export function createLessonState(storage = globalThis.sessionStorage) {
  const prefix = "milai:session:";
  const memory = new Map();
  const base = (session) => `${prefix}${encodeURIComponent(session)}:`;
  const lessonKey = (session, lesson) => `${base(session)}lesson:${encodeURIComponent(lesson)}`;
  const mainKey = (session) => `${base(session)}main-draft`;
  const read = (key) => {
    try { return storage.getItem(key); }
    catch { return memory.get(key) ?? null; }
  };
  const write = (key, value) => {
    memory.set(key, value);
    try { storage.setItem(key, value); } catch { /* Private browsing can restrict storage. */ }
  };
  const remove = (key) => {
    memory.delete(key);
    try { storage.removeItem(key); } catch { /* Keep the in-memory state usable. */ }
  };
  return {
    get(session, lesson) {
      try {
        const saved = JSON.parse(read(lessonKey(session, lesson)) || "{}");
        if (saved && typeof saved === "object") {
          return {
            draft: typeof saved.draft === "string" ? saved.draft : "",
            answers: saved.answers && typeof saved.answers === "object" ? saved.answers : {},
            selected: savedSelection(saved.selected),
            readingPosition: Number.isFinite(saved.readingPosition) ? saved.readingPosition : 0,
            tab: saved.tab === "discussion" ? "discussion" : "lesson",
          };
        }
      } catch { /* Ignore a damaged browser record. */ }
      return { draft: "", answers: {}, selected: null, readingPosition: 0, tab: "lesson" };
    },
    update(session, lesson, changes) {
      const previous = this.get(session, lesson);
      const next = { ...previous, ...changes };
      if (changes.answers) next.answers = { ...previous.answers, ...changes.answers };
      write(lessonKey(session, lesson), JSON.stringify(next));
      return next;
    },
    mainDraft(session) { return read(mainKey(session)) || ""; },
    setMainDraft(session, draft) { write(mainKey(session), draft); },
    forgetSession(session) {
      const start = base(session);
      for (const key of memory.keys()) if (key.startsWith(start)) remove(key);
      try {
        const keys = [];
        for (let index = 0; index < storage.length; index++) {
          const key = storage.key(index);
          if (key?.startsWith(start)) keys.push(key);
        }
        keys.forEach(remove);
      } catch { /* Storage may be unavailable. */ }
    },
  };
}
