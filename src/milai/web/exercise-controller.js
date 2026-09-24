export function createExerciseController(request) {
  const drafts = new Map();
  let session = null;
  let exercise = null;
  let statuses = {};
  const answered = new Set();
  let pending = false;
  const key = () => `${session}:${exercise?.id}`;
  return {
    get active() { return exercise; },
    get session() { return session; },
    get pending() { return pending; },
    get status() { return exercise ? statuses[exercise.id] || {} : {}; },
    get canContinue() { return exercise ? answered.has(key()) || Boolean(this.status.assessments?.length || this.status.completed) : false; },
    get draft() { return exercise ? drafts.get(key()) || "" : ""; },
    setDraft(value) { if (exercise) drafts.set(key(), value); },
    setSession(id, nextStatuses = {}) {
      session = id;
      exercise = null;
      statuses = nextStatuses;
    },
    setStatuses(nextStatuses) { statuses = nextStatuses; },
    open(item) { exercise = item; },
    close() { exercise = null; },
    async answer(text) {
      if (!exercise || pending) return null;
      const selected = exercise.id;
      const selectedSession = session;
      pending = true;
      try {
        const result = await request({session: selectedSession, exercise_id: selected, action: "answer", text});
        if (session === selectedSession) {
          statuses[selected] = result.status;
          if (result.reply) answered.add(`${selectedSession}:${selected}`);
          if (result.reply?.assessments?.length) drafts.delete(`${selectedSession}:${selected}`);
        }
        return result;
      } finally { pending = false; }
    },
    forgetSession(id) {
      for (const key of drafts.keys()) if (key.startsWith(`${id}:`)) drafts.delete(key);
      for (const key of answered) if (key.startsWith(`${id}:`)) answered.delete(key);
    },
  };
}
