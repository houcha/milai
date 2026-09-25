// Browser-only state for unfinished work. The server remains the source of truth
// for lesson content, discussion, attempts, and exercise status.
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
            selected: saved.selected || null,
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
