import { renderMarkdown } from "/markdown.bundle.js";
import { createLessonState } from "/exercise-controller.js";

const savedWork = createLessonState();
const elements = {
  composer: document.querySelector("#composer"),
  message: document.querySelector("#message"),
  messages: document.querySelector("#messages"),
  send: document.querySelector("#send"),
  notice: document.querySelector("#notice"),
  session: document.querySelector("#session-label"),
  path: document.querySelector("#learning-path"),
  skills: document.querySelector("#skills"),
  skillCount: document.querySelector("#skill-count"),
  newSession: document.querySelector("#new-session"),
  lessonView: document.querySelector("#lesson-view"),
  lessonDocument: document.querySelector("#lesson-document"),
  lessonExercises: document.querySelector("#lesson-exercises"),
  lessonReading: document.querySelector("#lesson-reading"),
  lessonMessages: document.querySelector("#lesson-messages"),
  lessonMessage: document.querySelector("#lesson-message"),
  lessonProgress: document.querySelector("#lesson-progress"),
};

let activeSession = null;
let sessionItems = [];
let currentRoute = { view: "chat", lessonId: null };
let lessonData = null;
let lessonConversation = [];
let exerciseStatuses = {};
let busy = false;
let routeSequence = 0;
const chatScroll = new Map();

function routeFromHash() {
  const hash = location.hash.slice(1);
  if (hash.startsWith("lesson/")) {
    try {
      const id = decodeURIComponent(hash.slice(7));
      if (id) return { view: "lesson", lessonId: id };
    } catch { /* Invalid links return to the conversation. */ }
  }
  return { view: ["sessions", "skills"].includes(hash) ? hash : "chat", lessonId: null };
}

function routeHash(route) {
  return route.view === "lesson" ? `lesson/${encodeURIComponent(route.lessonId)}` : route.view;
}

function sameRoute(a, b) { return a.view === b.view && a.lessonId === b.lessonId; }

function navigate(view, lessonId = null) {
  location.hash = routeHash({ view, lessonId });
  return renderView();
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

async function streamChat(body, onEvent) {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "Could not start the chat stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line) continue;
      const event = JSON.parse(line);
      if (event.type === "error") throw new Error(event.error);
      onEvent(event);
      if (event.type === "complete") completed = true;
    }
    if (done) break;
  }
  if (!completed) throw new Error("The chat stream ended before the turn was saved");
}

function text(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function lessonCardNode(card) {
  const wrapper = document.createElement("article");
  wrapper.className = "lesson-card";
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Lesson ready";
  const title = document.createElement("h3");
  title.textContent = text(card.title, "Your lesson");
  const objective = document.createElement("p");
  objective.textContent = text(card.objective);
  objective.hidden = !objective.textContent;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Open lesson ↗";
  button.addEventListener("click", () => navigate("lesson", card.id));
  wrapper.append(eyebrow, title, objective, button);
  return wrapper;
}

function activityNode(activity) {
  const wrapper = document.createElement("article");
  wrapper.className = "practice-card";
  const title = document.createElement("strong");
  title.textContent = text(activity.title, "New exercise");
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Open exercise ↗";
  button.addEventListener("click", async () => {
    await navigate("lesson", activity.lesson_id);
    document.getElementById(`lesson-exercise-${activity.id}`)?.scrollIntoView({ block: "start" });
  });
  wrapper.append(title, button);
  return wrapper;
}

function messageNode(role, content, options = {}) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}${options.pending ? " pending" : ""}`;
  if (options.turnId) {
    wrapper.id = `turn-${options.turnId}`;
    wrapper.tabIndex = -1;
  }
  const header = document.createElement("div");
  header.className = "message-header";
  const label = document.createElement("span");
  label.className = "role";
  label.textContent = role === "user" ? "You" : "Milai";
  header.append(label);
  if (options.reference) {
    const reference = document.createElement("span");
    reference.className = "message-reference";
    reference.textContent = options.reference;
    header.append(reference);
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant" && !options.pending) {
    bubble.classList.add("markdown");
    bubble.innerHTML = renderMarkdown(content || "");
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "message-format-toggle";
    toggle.textContent = "View raw";
    toggle.setAttribute("aria-label", "View raw message from Milai");
    toggle.setAttribute("aria-pressed", "false");
    toggle.addEventListener("click", () => {
      const raw = toggle.getAttribute("aria-pressed") !== "true";
      toggle.setAttribute("aria-pressed", String(raw));
      toggle.textContent = raw ? "View rendered" : "View raw";
      toggle.setAttribute("aria-label", raw ? "View rendered message from Milai" : "View raw message from Milai");
      bubble.classList.toggle("markdown", !raw);
      if (raw) bubble.textContent = content;
      else bubble.innerHTML = renderMarkdown(content || "");
    });
    header.append(toggle);
  } else bubble.textContent = content;
  wrapper.append(header, bubble);
  for (const card of options.lessonCards || []) wrapper.append(lessonCardNode(card));
  const cardIds = new Set((options.lessonCards || []).map((card) => card.id));
  for (const activity of options.activities || []) {
    if (activity.lesson_id && !cardIds.has(activity.lesson_id)) wrapper.append(activityNode(activity));
  }
  return wrapper;
}

function appendMessage(container, role, content, options = {}) {
  const node = messageNode(role, content, options);
  container.append(node);
  container.scrollTop = container.scrollHeight;
  return node;
}

function renderConversation(conversation) {
  elements.messages.replaceChildren();
  if (!conversation?.length) {
    const welcome = document.createElement("div");
    welcome.className = "welcome";
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "A language. A world of possibilities.";
    const heading = document.createElement("h2");
    heading.textContent = "What brings you here?";
    const intro = document.createElement("p");
    intro.textContent = "Start with something you love. We’ll find the language in it, together.";
    const suggestions = document.createElement("div");
    suggestions.className = "suggestions";
    for (const [label, message] of [
      ["Choose a language", "Help me get started with a language I want to learn."],
      ["Set a goal", "Help me turn my learning goal into a plan."],
      ["Bring your own material", "I have some material I would like to learn from."],
    ]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${label} ↗`;
      button.addEventListener("click", () => { elements.message.value = message; elements.message.focus(); });
      suggestions.append(button);
    }
    welcome.append(eyebrow, heading, intro, suggestions);
    elements.messages.append(welcome);
    return;
  }
  for (const item of conversation) {
    appendMessage(elements.messages, item.role, item.content, {
      turnId: item.turn_id, lessonCards: item.lesson_cards || [], activities: item.activities || [],
    });
  }
}

function renderLearning(learning = {}) {
  const lessons = learning.lessons || [];
  const focusId = learning.current_focus_lesson_id || learning.current_focus?.id || learning.active_lesson?.id;
  elements.path.replaceChildren();
  document.querySelector("#path-empty").hidden = lessons.length > 0;
  for (const lesson of lessons) {
    const item = document.createElement("li");
    const link = document.createElement("button");
    link.type = "button";
    link.className = "lesson-link";
    link.textContent = lesson.title;
    link.disabled = busy;
    if (lesson.id === focusId) {
      link.setAttribute("aria-current", "step");
      item.classList.add("current");
    }
    link.addEventListener("click", () => navigate("lesson", lesson.id));
    item.append(link);
    elements.path.append(item);
  }
  const skills = learning.skills || [];
  elements.skillCount.textContent = String(skills.length);
  elements.skills.replaceChildren();
  if (!skills.length) {
    const empty = document.createElement("div");
    empty.className = "empty-card";
    empty.textContent = "Evidence from your practice will appear here.";
    elements.skills.append(empty);
  } else for (const skill of skills) {
    const card = document.createElement("article");
    card.className = "skill-card";
    const title = document.createElement("h3");
    title.textContent = skill.name;
    const stats = document.createElement("div");
    stats.className = "skill-stats";
    const progress = skill.progress || {};
    const values = [
      [progress.observations, "observations", ""],
      [progress.independent_since_difficulty, "independent since last difficulty", "positive"],
      [progress.assistance_events, "help events", ""],
      [progress.needs_work, "to revisit", "attention"],
      [progress.minor_errors, "small slips", "attention"],
    ];
    for (const [count, label, className] of values.filter(([count]) => count)) {
      const badge = document.createElement("span");
      badge.className = className;
      badge.textContent = `${count} ${label}`;
      stats.append(badge);
    }
    const mastery = document.createElement("span");
    mastery.className = skill.mastered ? "positive" : "";
    mastery.textContent = skill.mastered ? "Mastered" : "In progress";
    stats.prepend(mastery);
    card.append(title, stats);
    if ((progress.contexts || []).length) {
      const contexts = document.createElement("p");
      contexts.className = "skill-contexts";
      contexts.textContent = `Seen in: ${progress.contexts.join(", ")}`;
      card.append(contexts);
    }
    elements.skills.append(card);
  }
}

function lessonState() { return savedWork.get(activeSession, currentRoute.lessonId); }

function updateLessonState(changes) {
  if (activeSession && currentRoute.lessonId) savedWork.update(activeSession, currentRoute.lessonId, changes);
}

function saveReadingPosition() {
  if (currentRoute.view === "lesson" && lessonData) {
    updateLessonState({ readingPosition: elements.lessonReading.scrollTop });
  }
}

function setLessonTab(tab) {
  document.querySelector("#lesson-layout").dataset.tab = tab;
  document.querySelector("#lesson-tab").setAttribute("aria-selected", String(tab === "lesson"));
  document.querySelector("#discussion-tab").setAttribute("aria-selected", String(tab === "discussion"));
  updateLessonState({ tab });
}

function selectedReferenceLabel(selected) {
  if (!selected) return "";
  const items = selected.kind === "section" ? lessonData?.sections : lessonData?.exercises;
  const item = items?.find((entry) => entry.id === selected.id);
  return item ? `${selected.kind === "section" ? "Section" : "Exercise"}: ${item.title}` : "";
}

function renderSelectedReference() {
  const selected = lessonState().selected;
  const label = selectedReferenceLabel(selected);
  document.querySelector("#selected-reference").hidden = !label;
  document.querySelector("#selected-reference-label").textContent = label;
  if (selected && !label) updateLessonState({ selected: null });
}

function chooseReference(kind, id) {
  updateLessonState({ selected: { kind, id } });
  renderSelectedReference();
  setLessonTab("discussion");
  elements.lessonMessage.focus();
}

function markdownBlock(content, className = "markdown") {
  const block = document.createElement("div");
  block.className = className;
  block.innerHTML = renderMarkdown(content || "");
  return block;
}

function renderLessonDocument() {
  elements.lessonDocument.replaceChildren();
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "Lesson";
  const title = document.createElement("h1");
  title.textContent = lessonData.title;
  const objective = document.createElement("p");
  objective.className = "lesson-objective";
  objective.textContent = text(lessonData.objective);
  elements.lessonDocument.append(eyebrow, title, objective);
  for (const section of lessonData.sections || []) {
    const wrapper = document.createElement("section");
    wrapper.className = "lesson-section";
    wrapper.id = `lesson-section-${section.id}`;
    const heading = document.createElement("div");
    heading.className = "lesson-section-heading";
    const name = document.createElement("h2");
    name.textContent = section.title;
    const ask = document.createElement("button");
    ask.type = "button";
    ask.className = "quiet-button";
    ask.textContent = "Ask about this section";
    ask.addEventListener("click", () => chooseReference("section", section.id));
    heading.append(name, ask);
    wrapper.append(heading, markdownBlock(section.markdown));
    elements.lessonDocument.append(wrapper);
  }
  const examples = lessonData.worked_examples || [];
  if (examples.length) {
    const wrapper = document.createElement("section");
    wrapper.className = "lesson-section";
    const heading = document.createElement("h2");
    heading.textContent = "Worked examples";
    wrapper.append(heading);
    for (const example of Array.isArray(examples) ? examples : [examples]) {
      if (typeof example === "string") wrapper.append(markdownBlock(example));
      else {
        const card = document.createElement("div");
        card.className = "worked-example";
        if (example.title) {
          const name = document.createElement("h3");
          name.textContent = example.title;
          card.append(name);
        }
        card.append(markdownBlock(example.markdown || example.explanation || ""));
        wrapper.append(card);
      }
    }
    elements.lessonDocument.append(wrapper);
  }
  if (lessonData.recap) {
    const wrapper = document.createElement("section");
    wrapper.className = "lesson-section lesson-recap";
    const heading = document.createElement("h2");
    heading.textContent = "Recap";
    wrapper.append(heading, markdownBlock(lessonData.recap));
    elements.lessonDocument.append(wrapper);
  }
}

function renderLessonExercises() {
  elements.lessonExercises.replaceChildren();
  for (const [index, item] of (lessonData.exercises || []).entries()) {
    const status = exerciseStatuses[item.id] || item.status || {};
    const card = document.createElement("article");
    card.className = "lesson-exercise";
    card.id = `lesson-exercise-${item.id}`;
    const meta = document.createElement("div");
    meta.className = "exercise-meta";
    const number = document.createElement("span");
    number.textContent = `Exercise ${index + 1}`;
    const state = document.createElement("span");
    state.className = `exercise-state${status.completed ? " completed" : ""}`;
    state.textContent = status.completed ? "Completed" : status.assessments?.length ? "In progress" : "Ready";
    meta.append(number, state);
    const title = document.createElement("h3");
    title.textContent = text(item.title, `Exercise ${index + 1}`);
    const context = markdownBlock(item.context || "", "markdown exercise-context");
    const task = markdownBlock((item.task || item.prompt || "").replaceAll("\\n", "\n"), "markdown exercise-task");
    card.append(meta, title, context, task);
    const attempts = document.createElement("div");
    attempts.className = "exercise-attempts";
    for (const attempt of status.assessments || []) {
      const entry = document.createElement("div");
      entry.className = "exercise-attempt";
      const answer = document.createElement("p");
      answer.textContent = `Your answer: ${attempt.learner_response || ""}`;
      const feedback = markdownBlock(attempt.feedback || "");
      entry.append(answer, feedback);
      attempts.append(entry);
    }
    card.append(attempts);
    const form = document.createElement("form");
    form.className = "exercise-answer-form";
    const label = document.createElement("label");
    label.textContent = "Your answer";
    label.htmlFor = `answer-${item.id}`;
    const answer = document.createElement("textarea");
    answer.id = `answer-${item.id}`;
    answer.maxLength = 8000;
    answer.rows = 3;
    answer.disabled = Boolean(status.completed);
    answer.value = lessonState().answers[item.id] || "";
    answer.addEventListener("focus", () => {
      updateLessonState({ selected: { kind: "exercise", id: item.id } });
      renderSelectedReference();
    });
    answer.addEventListener("input", () => updateLessonState({ answers: { [item.id]: answer.value } }));
    const actions = document.createElement("div");
    actions.className = "exercise-actions";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = "Submit answer";
    submit.disabled = busy || Boolean(status.completed);
    const ask = document.createElement("button");
    ask.type = "button";
    ask.className = "quiet-button";
    ask.textContent = "Ask about this exercise";
    ask.addEventListener("click", () => chooseReference("exercise", item.id));
    actions.append(submit, ask);
    form.append(label, answer, actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (answer.value.trim()) return submitLessonTurn(answer.value, "answer", { exercise_id: item.id });
    });
    card.append(form);
    elements.lessonExercises.append(card);
  }
}

function discussionReference(turn) {
  if (turn.exercise_id) {
    const item = lessonData?.exercises?.find((entry) => entry.id === turn.exercise_id);
    return `${turn.action === "answer" ? "Answer to" : "About"} ${item?.title || "exercise"}`;
  }
  if (turn.section_id) {
    const item = lessonData?.sections?.find((entry) => entry.id === turn.section_id);
    return `About ${item?.title || "section"}`;
  }
  return "";
}

function renderLessonConversation() {
  elements.lessonMessages.replaceChildren();
  if (!lessonConversation.length) {
    const empty = document.createElement("p");
    empty.className = "discussion-empty";
    empty.textContent = "Ask about the explanation or an exercise whenever you need to.";
    elements.lessonMessages.append(empty);
  }
  for (const turn of lessonConversation) {
    appendMessage(elements.lessonMessages, turn.role, turn.content, {
      turnId: turn.turn_id, reference: discussionReference(turn),
    });
  }
  elements.lessonMessages.scrollTop = elements.lessonMessages.scrollHeight;
}

function renderLesson() {
  renderLessonDocument();
  renderLessonExercises();
  renderLessonConversation();
  const state = lessonState();
  elements.lessonMessage.value = state.draft;
  renderSelectedReference();
  setLessonTab(state.tab);
  elements.lessonReading.scrollTop = state.readingPosition;
  document.title = `${lessonData.title} · Milai`;
}

async function refreshLesson(lessonId, sequence = routeSequence) {
  const session = activeSession;
  const payload = await api(`/api/lessons/${encodeURIComponent(lessonId)}?session=${encodeURIComponent(session)}`);
  if (sequence !== routeSequence || session !== activeSession || currentRoute.lessonId !== lessonId) return;
  lessonData = payload.lesson;
  lessonConversation = payload.conversation || [];
  exerciseStatuses = payload.exercise_status || {};
  renderLesson();
}

async function renderView() {
  const route = routeFromHash();
  if (busy && !sameRoute(route, currentRoute)) {
    location.hash = routeHash(currentRoute);
    return;
  }
  const changed = !sameRoute(route, currentRoute);
  if (changed && currentRoute.view === "lesson") saveReadingPosition();
  if (changed && currentRoute.view === "chat") chatScroll.set(activeSession, elements.messages.scrollTop);
  currentRoute = route;
  if (changed) routeSequence++;
  document.querySelectorAll("[data-view]").forEach((panel) => { panel.hidden = panel.dataset.view !== route.view; });
  document.querySelector(".path-rail").hidden = route.view === "sessions";
  document.querySelector(".app-shell").classList.toggle("wide-view", route.view === "sessions");
  document.querySelector("#session-heading").hidden = route.view === "sessions";
  document.querySelector("#sessions-link").textContent = route.view === "sessions" ? "Sessions" : "← Sessions";
  for (const [id, selected] of [["sessions-link", route.view === "sessions"], ["session-label", route.view === "chat"], ["skills-link", route.view === "skills"]]) {
    const link = document.querySelector(`#${id}`);
    if (selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (route.view === "lesson") {
    if (!activeSession) return;
    if (changed || !lessonData || lessonData.id !== route.lessonId) {
      lessonData = null;
      elements.lessonDocument.textContent = "Opening lesson…";
      elements.lessonExercises.replaceChildren();
      elements.lessonMessages.replaceChildren();
      try { await refreshLesson(route.lessonId, routeSequence); }
      catch (error) { elements.lessonDocument.textContent = "Could not open this lesson."; elements.notice.textContent = error.message; }
    }
  } else {
    document.title = `${{ chat: "Conversation", sessions: "Sessions", skills: "Skills" }[route.view]} · Milai`;
    if (route.view === "chat" && changed) {
      elements.messages.scrollTop = chatScroll.get(activeSession) ?? elements.messages.scrollHeight;
    }
  }
}

function setBusy(value) {
  busy = value;
  elements.send.disabled = value;
  elements.message.disabled = value;
  elements.lessonMessage.disabled = value;
  document.querySelector("#lesson-send").disabled = value;
  for (const selector of ["#new-session, .session-list button, .lesson-link, .suggestions button, .lesson-card button, .exercise-answer-form button, .lesson-section button, .lesson-toolbar button"]) {
    document.querySelectorAll(selector).forEach((button) => { button.disabled = value; });
  }
}

async function sendMainMessage(message, originLessonId = null, preserveDraft = false) {
  if (!message || busy) return;
  const previousDraft = preserveDraft ? elements.message.value : "";
  elements.notice.textContent = "";
  elements.messages.querySelector(".welcome")?.remove();
  const user = appendMessage(elements.messages, "user", message);
  elements.message.value = "";
  savedWork.setMainDraft(activeSession, "");
  const pending = appendMessage(elements.messages, "assistant", "Thinking with your learning history…", { pending: true });
  setBusy(true);
  try {
    const bubble = pending.querySelector(".bubble");
    let replyDraft = "";
    await streamChat({ session: activeSession, message, action: "message", ...(originLessonId ? { origin_lesson_id: originLessonId } : {}) }, (event) => {
      if (event.type === "stage") bubble.textContent = event.text;
      if (event.type === "reply_delta") {
        replyDraft += event.text;
        bubble.textContent = replyDraft;
      }
      if (event.type === "complete") {
        const payload = event.result;
        pending.remove();
        appendMessage(elements.messages, "assistant", payload.reply.text, {
          turnId: payload.reply.turn_id, lessonCards: payload.reply.lesson_cards || [], activities: payload.reply.activities || [],
        });
        renderLearning(payload.learning);
        renderSessions(payload.sessions);
      }
      elements.messages.scrollTop = elements.messages.scrollHeight;
    });
  } catch (error) {
    user.remove();
    pending.remove();
    elements.message.value = preserveDraft ? previousDraft : message;
    savedWork.setMainDraft(activeSession, elements.message.value);
    elements.notice.textContent = error.message;
  } finally {
    if (preserveDraft && !elements.notice.textContent) {
      elements.message.value = previousDraft;
      savedWork.setMainDraft(activeSession, previousDraft);
    }
    setBusy(false);
    if (currentRoute.view === "chat") elements.message.focus();
  }
}

async function submitLessonTurn(message, action = "message", reference = {}) {
  if (!message.trim() || busy || !lessonData) return;
  const lessonId = currentRoute.lessonId;
  const selected = action === "message" ? lessonState().selected : null;
  const context = { ...reference };
  if (selected?.kind === "section") context.section_id = selected.id;
  if (selected?.kind === "exercise") context.exercise_id = selected.id;
  elements.notice.textContent = "";
  const user = appendMessage(elements.lessonMessages, "user", message, {
    pending: true, reference: discussionReference({ ...context, action }),
  });
  const pending = appendMessage(elements.lessonMessages, "assistant", "Working on your lesson…", { pending: true });
  elements.lessonProgress.textContent = action === "answer" ? "Checking your answer…" : "Thinking about your question…";
  setBusy(true);
  try {
    let committedReply = null;
    await streamChat({ session: activeSession, lesson_id: lessonId, message, action, ...context }, (event) => {
      if (event.type === "stage") pending.querySelector(".bubble").textContent = event.text;
      if (event.type === "complete") committedReply = event.result.reply;
      // Structured lesson output is shown only after the complete event commits.
    });
    if (action === "answer") updateLessonState({ answers: { [context.exercise_id]: "" }, selected: { kind: "exercise", id: context.exercise_id } });
    else updateLessonState({ draft: "" });
    try {
      await refreshLesson(lessonId);
      elements.lessonProgress.textContent = "Saved to this lesson.";
    } catch (error) {
      user.className = "message user";
      pending.remove();
      appendMessage(elements.lessonMessages, "assistant", committedReply?.text || "Your reply was saved.", {
        reference: discussionReference({ ...context, action }),
      });
      elements.lessonProgress.textContent = "Saved. Reopen the lesson to refresh exercise status.";
      elements.notice.textContent = error.message;
    }
  } catch (error) {
    user.remove();
    pending.remove();
    elements.lessonProgress.textContent = error.message;
    elements.notice.textContent = error.message;
  } finally { setBusy(false); }
}

function renderSessions(sessions) {
  sessionItems = sessions || sessionItems;
  const list = document.querySelector("#sessions");
  list.replaceChildren();
  sessionItems.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-item";
    button.disabled = busy;
    if (session.id === activeSession) button.setAttribute("aria-current", "true");
    const title = document.createElement("span");
    title.textContent = session.title;
    const detail = document.createElement("small");
    detail.textContent = session.turns ? `${session.turns} ${session.turns === 1 ? "exchange" : "exchanges"}` : "A fresh start";
    button.append(title, detail);
    button.addEventListener("click", () => manageSession("select", { session: session.id }));
    const row = document.createElement("article");
    row.className = "session-row";
    if (session.id === activeSession) row.classList.add("current");
    const actions = document.createElement("div");
    actions.className = "session-actions";
    for (const action of ["rename", "delete"]) {
      const control = document.createElement("button");
      control.type = "button";
      control.className = "quiet-button";
      control.textContent = action === "rename" ? "Rename" : "Delete";
      control.setAttribute("aria-label", `${control.textContent} ${session.title}`);
      control.disabled = busy;
      control.addEventListener("click", () => openSessionDialog(action, session));
      actions.append(control);
    }
    row.append(button, actions);
    list.append(row);
  });
  elements.session.textContent = sessionItems.find((item) => item.id === activeSession)?.title || "New learning session";
}

function applySession(payload) {
  if (activeSession) savedWork.setMainDraft(activeSession, elements.message.value);
  const changed = activeSession !== payload.session;
  activeSession = payload.session;
  if (changed) {
    lessonData = null;
    lessonConversation = [];
    exerciseStatuses = {};
    routeSequence++;
  }
  elements.message.value = savedWork.mainDraft(activeSession);
  renderSessions(payload.sessions);
  renderConversation(payload.conversation);
  elements.messages.scrollTop = chatScroll.get(activeSession) ?? elements.messages.scrollHeight;
  renderLearning(payload.learning);
}

async function manageSession(action, extra = {}) {
  if (busy) return;
  setBusy(true);
  elements.notice.textContent = "";
  try {
    saveReadingPosition();
    if (currentRoute.view === "chat") chatScroll.set(activeSession, elements.messages.scrollTop);
    const payload = await api("/api/session", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ...extra }),
    });
    applySession(payload);
    if (action === "delete") {
      savedWork.forgetSession(extra.session);
      chatScroll.delete(extra.session);
    }
    setBusy(false);
    await navigate(action === "create" || action === "select" ? "chat" : "sessions");
  } catch (error) { elements.notice.textContent = error.message; }
  finally { setBusy(false); }
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMainMessage(elements.message.value.trim());
});
elements.message.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); elements.composer.requestSubmit(); }
});
elements.message.addEventListener("input", () => {
  if (activeSession) savedWork.setMainDraft(activeSession, elements.message.value);
  elements.message.style.height = "auto";
  elements.message.style.height = `${Math.min(elements.message.scrollHeight, 130)}px`;
});
document.querySelector("#lesson-composer").addEventListener("submit", (event) => {
  event.preventDefault();
  submitLessonTurn(elements.lessonMessage.value, "message");
});
elements.lessonMessage.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.querySelector("#lesson-composer").requestSubmit(); }
});
elements.lessonMessage.addEventListener("input", () => updateLessonState({ draft: elements.lessonMessage.value }));
elements.lessonReading.addEventListener("scroll", saveReadingPosition);
document.querySelector("#remove-reference").addEventListener("click", () => { updateLessonState({ selected: null }); renderSelectedReference(); });
document.querySelector("#lesson-tab").addEventListener("click", () => setLessonTab("lesson"));
document.querySelector("#discussion-tab").addEventListener("click", () => setLessonTab("discussion"));
document.querySelector("#back-to-conversation").addEventListener("click", () => navigate("chat"));
document.querySelector("#continue-learning").addEventListener("click", async () => {
  const origin = currentRoute.lessonId;
  await navigate("chat");
  await sendMainMessage("Continue learning from this lesson.", origin, true);
});
elements.newSession.addEventListener("click", () => manageSession("create"));

const dialog = document.querySelector("#session-dialog");
let dialogAction;
let dialogSession;
function openSessionDialog(action, session) {
  if (busy) return;
  dialogAction = action;
  dialogSession = session.id;
  const renaming = action === "rename";
  document.querySelector("#dialog-title").textContent = renaming ? "Rename session" : "Delete session?";
  document.querySelector("#dialog-description").textContent = renaming ? session.title : `Delete “${session.title}” and its conversation, lessons, and skill evidence? This cannot be undone.`;
  document.querySelector("#session-name").hidden = !renaming;
  document.querySelector("#session-name-label").hidden = !renaming;
  document.querySelector("#session-name").required = renaming;
  document.querySelector("#session-name").value = session.title;
  document.querySelector("#dialog-confirm").textContent = renaming ? "Save name" : "Delete session";
  dialog.showModal();
  if (renaming) document.querySelector("#session-name").select();
  else document.querySelector("#dialog-cancel").focus();
}
document.querySelector("#dialog-cancel").addEventListener("click", () => dialog.close());
document.querySelector("#session-dialog-form").addEventListener("submit", (event) => {
  event.preventDefault();
  dialog.close();
  manageSession(dialogAction, { session: dialogSession, title: document.querySelector("#session-name").value });
});

window.addEventListener("hashchange", renderView);
renderView();
async function bootstrap() {
  setBusy(true);
  try { applySession(await api("/api/bootstrap")); }
  catch (error) { elements.notice.textContent = error.message; }
  finally { setBusy(false); await renderView(); }
}
bootstrap();
