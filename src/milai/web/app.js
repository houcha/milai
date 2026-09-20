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
  map: document.querySelector("#learning-map"),
  skills: document.querySelector("#skills"),
  skillCount: document.querySelector("#skill-count"),
  newSession: document.querySelector("#new-session"),
};

let busy = false;

const viewNames = { chat: "Conversation", map: "Learning Map", skills: "Skills" };

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

function activityNode(activity) {
  const card = document.createElement("section");
  card.className = `activity-card ${activity.kind}`;
  const label = document.createElement("span");
  label.className = "activity-kind";
  label.textContent = activity.kind === "theory" ? "Theory" : "Exercise";
  const title = document.createElement("h3");
  title.textContent = activity.title;
  card.append(label, title);
  if (activity.kind === "theory") {
    const explanation = document.createElement("p");
    explanation.textContent = activity.explanation;
    card.append(explanation);
    (activity.examples || []).forEach((item) => {
      const example = document.createElement("div");
      example.className = "theory-example";
      const phrase = document.createElement("strong");
      phrase.textContent = item.example;
      const note = document.createElement("span");
      note.textContent = item.explanation;
      example.append(phrase, note);
      card.append(example);
    });
  } else {
    if (activity.context) {
      const context = document.createElement("p");
      context.className = "activity-context";
      context.textContent = activity.context;
      card.append(context);
    }
    const task = document.createElement("p");
    task.className = "activity-task";
    task.textContent = activity.task;
    card.append(task);
  }
  const skills = document.createElement("div");
  skills.className = "activity-skills";
  (activity.skills || []).forEach((skill) => {
    const chip = document.createElement("span");
    chip.textContent = skill.role ? `${skill.name} · ${skill.role}` : skill.name;
    skills.append(chip);
  });
  card.append(skills);
  return card;
}

function messageNode(role, content, pending = false, activities = []) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}${pending ? " pending" : ""}`;
  const label = document.createElement("span");
  label.className = "role";
  label.textContent = role === "user" ? "You" : "Milai";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;
  wrapper.append(label, bubble);
  activities.forEach((activity) => wrapper.append(activityNode(activity)));
  return wrapper;
}

function appendMessage(role, content, pending = false, activities = []) {
  const node = messageNode(role, content, pending, activities);
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
  conversation.forEach((item) => appendMessage(item.role, item.content, false, item.activities || []));
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
  elements.focus.className = "";
  const focus = learning.focus;
  if (focus) {
    const card = document.createElement("div");
    card.className = "focus-card";
    const title = document.createElement("strong");
    const targets = (focus.skills || []).filter((item) => item.role === "target");
    title.textContent = targets.map((item) => item.name).join(", ") || "Current focus";
    const reason = document.createElement("span");
    reason.textContent = text(focus.reason, "Learning in progress");
    card.append(title, reason);
    elements.focus.append(card);
  } else {
    elements.focus.className = "empty-card";
    elements.focus.textContent = "No lesson selected yet.";
  }

  elements.map.replaceChildren();
  const topics = learning.topics || [];
  if (!topics.length) {
    elements.map.className = "empty-card";
    elements.map.textContent = "Your skill graph will appear as Milai learns your goals.";
  } else {
    elements.map.className = "topic-list";
    topics.forEach((topic) => {
      const card = document.createElement("article");
      card.className = "topic-card";
      const title = document.createElement("h3");
      title.textContent = topic.name;
      const purpose = document.createElement("p");
      purpose.textContent = topic.purpose;
      const list = document.createElement("ol");
      list.className = "skill-map";
      (topic.skills || []).forEach((skill) => {
        const row = document.createElement("li");
        const prerequisites = (topic.prerequisites || [])
          .filter((edge) => edge.dependent_id === skill.id)
          .map((edge) => (topic.skills || []).find((item) => item.id === edge.prerequisite_id)?.name)
          .filter(Boolean);
        row.textContent = `${skill.name} · ${skill.role}${prerequisites.length ? ` · after ${prerequisites.join(", ")}` : ""}`;
        list.append(row);
      });
      card.append(title, purpose, list);
      elements.map.append(card);
    });
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
    appendMessage("assistant", payload.reply.text, false, payload.reply.activities || []);
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
