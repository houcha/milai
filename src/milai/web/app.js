import { renderMarkdown } from "/markdown.bundle.js";
import { createExerciseController } from "/exercise-controller.js";

const exercise = createExerciseController((body) => api("/api/exercise", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
}));
const exerciseView = document.querySelector("#exercise-view");
const exerciseAnswer = document.querySelector("#exercise-answer");
let conversationScroll = 0;
let topicAnchors = {};
let currentView = "chat";
const scrollPositions = new Map();

function renderExercise() {
  const item = exercise.active;
  const requested = location.hash.slice(1);
  const inConversation = !Object.hasOwn(viewNames, requested) || requested === "chat";
  const practicing = Boolean(item) && inConversation;
  exerciseView.hidden = !practicing;
  document.querySelector(".chat-panel").hidden = !inConversation || practicing;
  document.querySelector(".path-rail").hidden = practicing || requested === "sessions";
  document.querySelector(".app-shell").classList.toggle("wide-view", practicing || requested === "sessions");
  if (!practicing) return;
  document.querySelector("#exercise-title").textContent = item.title;
  document.querySelector("#exercise-context").innerHTML = renderMarkdown(item.context || "");
  document.querySelector("#exercise-task").innerHTML = renderMarkdown((item.task || "").replaceAll("\\n", "\n"));
  const status = exercise.status;
  const history = document.querySelector("#exercise-history");
  history.replaceChildren();
  for (const attempt of status.assessments || []) {
    for (const [label, value] of [["Your answer", attempt.learner_response], ["Milai", attempt.feedback]]) {
      const entry = document.createElement("div");
      if (label === "Milai") {
        entry.className = "markdown";
        entry.innerHTML = `<strong>${label}:</strong> ${renderMarkdown(value || "")}`;
      } else entry.textContent = `${label}: ${value}`;
      history.append(entry);
    }
  }
  exerciseAnswer.value = exercise.draft;
  document.querySelector("#exercise-form").hidden = Boolean(status.completed);
  document.querySelector("#exercise-continue").hidden = !exercise.canContinue;
  document.querySelector("#exercise-submit").disabled = exercise.pending;
}

function openExercise(item) {
  conversationScroll = elements.messages.scrollTop;
  exercise.open(item);
  document.querySelector("#exercise-status").textContent = "";
  location.hash = "chat";
  renderView();
  exerciseAnswer.focus();
}

function closeExercise() {
  exercise.setDraft(exerciseAnswer.value);
  exercise.close();
  renderView();
  elements.messages.scrollTop = conversationScroll;
  elements.message.focus();
}

async function submitExercise() {
  if (busy || exercise.pending) return;
  const item = exercise.active;
  if (!item) return;
  const answer = exerciseAnswer.value;
  exercise.setDraft(answer);
  elements.notice.textContent = "";
  const statusMessage = document.querySelector("#exercise-status");
  statusMessage.textContent = "Checking your answer…";
  setBusy(true);
  try {
    const result = await exercise.answer(answer);
    if (!result) return;
    if (result.reply) {
      appendMessage("user", answer);
      appendMessage("assistant", result.reply.text, false, result.reply.activities || [], result.reply.turn_id);
      topicAnchors = result.topic_anchors || {};
      renderSessions(result.sessions);
      renderLearning(result.learning);
    }
    renderExercise();
    statusMessage.textContent = "";
    if (!exercise.status.completed) exerciseAnswer.focus();
  } catch (error) {
    exerciseAnswer.value = answer;
    statusMessage.textContent = error.message;
    elements.notice.textContent = error.message;
  } finally { setBusy(false); }
}

document.querySelector("#exercise-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (exerciseAnswer.value.trim()) submitExercise();
});
exerciseAnswer.addEventListener("input", () => exercise.setDraft(exerciseAnswer.value));
document.querySelector("#exercise-continue").addEventListener("click", closeExercise);

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
};

let busy = false;
let activeSession = null;
let sessionItems = [];
const drafts = new Map();

const viewNames = { chat: "Conversation", sessions: "Sessions", skills: "Skills" };

function leaveExercise() {
  if (!exercise.active) return;
  if (!exercise.canContinue) {
    const message = "Submit an answer before continuing.";
    document.querySelector("#exercise-status").textContent = message;
    throw new Error(message);
  }
  exercise.setDraft(exerciseAnswer.value);
  exercise.close();
  elements.messages.scrollTop = conversationScroll;
}

async function renderView() {
  const requested = location.hash.slice(1);
  const view = Object.hasOwn(viewNames, requested) ? requested : "chat";
  if (view !== currentView && busy) {
    location.hash = currentView;
    return;
  }
  if (exercise.active && view !== "chat") {
    setBusy(true);
    try { leaveExercise(); }
    catch (error) {
      elements.notice.textContent = error.message;
      location.hash = "chat";
      return;
    } finally { setBusy(false); }
  }
  if (currentView === "chat" && view !== "chat") {
    scrollPositions.set(activeSession, elements.messages.scrollTop);
  }
  const previousView = currentView;
  currentView = view;
  if (requested !== view) location.hash = view;
  document.querySelectorAll("[data-view]").forEach((panel) => {
    panel.hidden = panel.dataset.view !== view;
  });
  document.querySelector("#session-heading").hidden = view === "sessions";
  document.querySelector("#sessions-link").textContent = view === "sessions" ? "Sessions" : "← Sessions";
  for (const [id, selected] of [["sessions-link", view === "sessions"], ["session-label", view === "chat"], ["skills-link", view === "skills"]]) {
    const link = document.querySelector(`#${id}`);
    if (selected) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.title = `${viewNames[view]} · Milai`;
  renderExercise();
  if (view === "chat" && previousView !== "chat") {
    elements.messages.scrollTop = scrollPositions.get(activeSession) ?? elements.messages.scrollHeight;
  }
}

async function jumpToTopic(topicId) {
  if (busy) return;
  setBusy(true);
  try { leaveExercise(); }
  catch (error) { elements.notice.textContent = error.message; return; }
  finally { setBusy(false); }
  location.hash = "chat";
  await renderView();
  const turnId = topicAnchors[topicId];
  const target = turnId && document.getElementById(`turn-${turnId}`);
  if (!target) {
    elements.notice.textContent = "The original discussion for this topic is unavailable.";
    return;
  }
  elements.notice.textContent = "";
  target.scrollIntoView({ block: "start" });
  target.focus({ preventScroll: true });
}

window.addEventListener("hashchange", renderView);
renderView();

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function activityNode(activity) {
  const start = document.createElement("button");
  start.type = "button";
  start.className = "exercise-launch";
  start.textContent = "Start exercise";
  start.addEventListener("click", () => openExercise(activity));
  return start;
}

function messageNode(role, content, pending = false, activities = [], turnId = null) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}${pending ? " pending" : ""}`;
  if (role === "assistant" && turnId) {
    wrapper.id = `turn-${turnId}`;
    wrapper.tabIndex = -1;
  }
  const label = document.createElement("span");
  label.className = "role";
  label.textContent = role === "user" ? "You" : "Milai";
  const header = document.createElement("div");
  header.className = "message-header";
  header.append(label);
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant" && !pending) {
    bubble.classList.add("markdown");
    bubble.innerHTML = renderMarkdown(content);
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
      toggle.setAttribute(
        "aria-label",
        raw ? "View rendered message from Milai" : "View raw message from Milai",
      );
      bubble.classList.toggle("markdown", !raw);
      if (raw) bubble.textContent = content;
      else bubble.innerHTML = renderMarkdown(content);
    });
    header.append(toggle);
  } else {
    bubble.textContent = content;
  }
  wrapper.append(header, bubble);
  activities.forEach((activity) => wrapper.append(activityNode(activity)));
  return wrapper;
}

function appendMessage(role, content, pending = false, activities = [], turnId = null) {
  const node = messageNode(role, content, pending, activities, turnId);
  elements.messages.append(node);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return node;
}

function renderConversation(conversation) {
  elements.messages.replaceChildren();
  if (!conversation.length) {
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
      button.textContent = label + " ↗";
      button.addEventListener("click", () => { elements.message.value = message; elements.message.focus(); });
      suggestions.append(button);
    }
    welcome.append(eyebrow, heading, intro, suggestions);
    elements.messages.append(welcome);
    return;
  }
  conversation.forEach((item) => appendMessage(item.role, item.content, false, item.activities || [], item.turn_id));
}

function text(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function renderLearning(learning) {
  const topics = learning.topics || [];
  elements.path.replaceChildren();
  document.querySelector("#path-empty").hidden = topics.length > 0;
  for (const topic of topics) {
    const item = document.createElement("li");
    const link = document.createElement("button");
    link.type = "button";
    link.className = "topic-link";
    link.textContent = topic.name;
    link.disabled = busy;
    if (topic.id === learning.focus?.topic_id) {
      link.setAttribute("aria-current", "step");
      item.classList.add("current");
    }
    link.addEventListener("click", () => jumpToTopic(topic.id));
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
  } else {
    skills.forEach((skill) => {
      const card = document.createElement("article");
      card.className = "skill-card";
      const title = document.createElement("h3");
      title.textContent = skill.name;
      const stats = document.createElement("div");
      stats.className = "skill-stats";
      const progress = skill.progress || {};
      const values = [
        [progress.observations, "observations", ""],
        [progress.independent_successes, "independent", "positive"],
        [progress.assistance_events, "help events", ""],
        [progress.needs_work, "to revisit", "attention"],
      ];
      values.filter(([count]) => count).forEach(([count, label, className]) => {
        const badge = document.createElement("span");
        badge.className = className;
        badge.textContent = `${count} ${label}`;
        stats.append(badge);
      });
      card.append(title, stats);
      if ((progress.contexts || []).length) {
        const contexts = document.createElement("p");
        contexts.className = "skill-contexts";
        contexts.textContent = `Seen in: ${progress.contexts.join(", ")}`;
        card.append(contexts);
      }
      elements.skills.append(card);
    });
  }
}

function setBusy(value) {
  busy = value;
  elements.send.disabled = value;
  elements.message.disabled = value;
  for (const selector of ["#exercise-submit", "#exercise-continue"]) {
    document.querySelector(selector).disabled = value;
  }
  document.querySelectorAll("#new-session, .session-list button, .topic-link, .suggestions button, .exercise-launch").forEach((button) => { button.disabled = value; });
}

async function bootstrap() {
  setBusy(true);
  try {
    const payload = await api("/api/bootstrap");
    applySession(payload);
  } catch (error) {
    elements.notice.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

elements.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.message.value.trim();
  if (!message || busy) return;
  elements.notice.textContent = "";
  elements.messages.querySelector(".welcome")?.remove();
  appendMessage("user", message);
  elements.message.value = "";
  const pending = appendMessage("assistant", "Thinking with your learning history…", true);
  setBusy(true);
  try {
    const payload = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session: activeSession }),
    });
    pending.remove();
    appendMessage("assistant", payload.reply.text, false, payload.reply.activities || [], payload.reply.turn_id);
    topicAnchors = payload.topic_anchors || {};
    renderLearning(payload.learning);
    exercise.setStatuses(payload.exercise_status || {});
    renderSessions(payload.sessions);
  } catch (error) {
    elements.message.value = message;
    pending.previousElementSibling?.remove();
    pending.remove();
    elements.notice.textContent = error.message;
  } finally {
    setBusy(false);
    if (!elements.message.closest("[data-view]").hidden) elements.message.focus();
  }
});

elements.message.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});

elements.message.addEventListener("input", () => {
  elements.message.style.height = "auto";
  elements.message.style.height = `${Math.min(elements.message.scrollHeight, 130)}px`;
});

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
  if (activeSession) drafts.set(activeSession, elements.message.value);
  activeSession = payload.session;
  topicAnchors = payload.topic_anchors || {};
  exercise.setSession(activeSession, payload.exercise_status || {});
  elements.message.value = drafts.get(activeSession) || "";
  renderSessions(payload.sessions);
  renderConversation(payload.conversation);
  elements.messages.scrollTop = scrollPositions.get(activeSession) ?? elements.messages.scrollHeight;
  renderLearning(payload.learning);
  renderView();
}

async function manageSession(action, extra = {}) {
  if (busy) return;
  setBusy(true);
  elements.notice.textContent = "";
  try {
    leaveExercise();
    if (currentView === "chat") scrollPositions.set(activeSession, elements.messages.scrollTop);
    const payload = await api("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, ...extra }),
    });
    applySession(payload);
    if (action === "delete") drafts.delete(extra.session);
    if (action === "delete") exercise.forgetSession(extra.session);
    if (action === "delete") scrollPositions.delete(extra.session);
    setBusy(false);
    location.hash = action === "create" || action === "select" ? "chat" : "sessions";
    await renderView();
  } catch (error) {
    elements.notice.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

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
  document.querySelector("#dialog-description").textContent = renaming ? session.title : `Delete “${session.title}” and its conversation, topics, and skill evidence? This cannot be undone.`;
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
bootstrap();
