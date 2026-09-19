const elements = {
  composer: document.querySelector("#composer"),
  message: document.querySelector("#message"),
  messages: document.querySelector("#messages"),
  send: document.querySelector("#send"),
  notice: document.querySelector("#notice"),
  session: document.querySelector("#session-label"),
  title: document.querySelector("#learning-title"),
  subtitle: document.querySelector("#learning-subtitle"),
  focus: document.querySelector("#current-focus"),
  curriculum: document.querySelector("#curriculum"),
  skills: document.querySelector("#skills"),
  skillCount: document.querySelector("#skill-count"),
  newSession: document.querySelector("#new-session"),
};

let busy = false;

const viewNames = { chat: "Conversation", curriculum: "Curriculum", skills: "Skills" };

function renderView() {
  const requested = location.hash.slice(1);
  const view = Object.hasOwn(viewNames, requested) ? requested : "chat";
  document.querySelectorAll("[data-view]").forEach((panel) => {
    panel.hidden = panel.dataset.view !== view;
  });
  document.querySelector("#current-view").textContent = viewNames[view];
  document.querySelector("#view-menu").open = false;
  document.querySelectorAll(".view-links a").forEach((link) => {
    if (link.hash === `#${view}`) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  document.title = `${viewNames[view]} · Milai`;
}

window.addEventListener("hashchange", renderView);
document.querySelectorAll(".view-links a").forEach((link) => {
  link.addEventListener("click", () => {
    document.querySelector("#view-menu").open = false;
    document.querySelector("#view-menu summary").focus();
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.querySelector("#view-menu").open) {
    document.querySelector("#view-menu").open = false;
    document.querySelector("#view-menu summary").focus();
  }
});
renderView();

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function messageNode(role, content, pending = false) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}${pending ? " pending" : ""}`;
  const label = document.createElement("span");
  label.className = "role";
  label.textContent = role === "user" ? "You" : "Milai";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;
  wrapper.append(label, bubble);
  return wrapper;
}

function appendMessage(role, content, pending = false) {
  const node = messageNode(role, content, pending);
  elements.messages.append(node);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return node;
}

function renderConversation(conversation) {
  elements.messages.replaceChildren();
  if (!conversation.length) {
    appendMessage(
      "assistant",
      "What language would you like to learn, and what would you like to do with it?",
    );
    return;
  }
  conversation.forEach((item) => appendMessage(item.role, item.content));
}

function text(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function renderLearning(learning) {
  const profile = learning.profile || {};
  const language = text(profile.target_language);
  const goal = text(profile.goals);
  elements.title.textContent = language ? `Your ${language} path` : "Building your learning path";
  elements.subtitle.textContent = goal || "Tell Milai what you want to use the language for.";

  elements.focus.replaceChildren();
  if (learning.current_lesson) {
    const card = document.createElement("div");
    card.className = "focus-card";
    const title = document.createElement("strong");
    title.textContent = learning.current_lesson.title;
    const objective = document.createElement("span");
    objective.textContent = learning.current_lesson.objective || "Current lesson";
    card.append(title, objective);
    elements.focus.append(card);
  } else if (learning.current_focus) {
    const card = document.createElement("div");
    card.className = "focus-card";
    const title = document.createElement("strong");
    title.textContent = text(learning.current_focus.skill, "Current activity");
    const task = document.createElement("span");
    task.textContent = text(learning.current_focus.task, "Practice in progress");
    card.append(title, task);
    elements.focus.append(card);
  } else {
    elements.focus.className = "empty-card";
    elements.focus.textContent = "No lesson selected yet.";
  }

  elements.curriculum.replaceChildren();
  const curriculum = learning.curriculum;
  if (!curriculum) {
    elements.curriculum.className = "empty-card";
    elements.curriculum.textContent = "Your roadmap will appear as Milai learns your goals.";
  } else {
    elements.curriculum.className = "";
    const title = document.createElement("h3");
    title.className = "curriculum-title";
    title.textContent = text(curriculum.title, "Your roadmap");
    const list = document.createElement("ol");
    list.className = "curriculum-list";
    (curriculum.outline || []).forEach((item) => {
      const row = document.createElement("li");
      row.textContent = item;
      list.append(row);
    });
    elements.curriculum.append(title, list);
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
      const values = [
        [skill.attempts, "attempts", ""],
        [skill.independent_successes, "independent", "positive"],
        [skill.assisted_successes, "with help", "positive"],
        [skill.needs_work, "to revisit", "attention"],
      ];
      values.filter(([count]) => count).forEach(([count, label, className]) => {
        const badge = document.createElement("span");
        badge.className = className;
        badge.textContent = `${count} ${label}`;
        stats.append(badge);
      });
      card.append(title, stats);
      elements.skills.append(card);
    });
  }
}

function setBusy(value) {
  busy = value;
  elements.send.disabled = value;
  elements.message.disabled = value;
}

async function bootstrap() {
  try {
    const payload = await api("/api/bootstrap");
    elements.session.textContent = `session ${payload.session}`;
    renderConversation(payload.conversation);
    renderLearning(payload.learning);
  } catch (error) {
    elements.notice.textContent = error.message;
  }
}

elements.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.message.value.trim();
  if (!message || busy) return;
  elements.notice.textContent = "";
  appendMessage("user", message);
  elements.message.value = "";
  const pending = appendMessage("assistant", "Thinking with your learning history…", true);
  setBusy(true);
  try {
    const payload = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    pending.remove();
    appendMessage("assistant", payload.reply);
    renderLearning(payload.learning);
  } catch (error) {
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

elements.newSession.addEventListener("click", async () => {
  if (busy) return;
  setBusy(true);
  elements.notice.textContent = "";
  try {
    const payload = await api("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    elements.session.textContent = `session ${payload.session}`;
    renderConversation(payload.conversation);
    renderLearning(payload.learning);
    location.hash = "chat";
  } catch (error) {
    elements.notice.textContent = error.message;
  } finally {
    setBusy(false);
  }
});

bootstrap();
