// Audio is requested only by an explicit click or keyboard activation.
export function createPronunciationController({ fetchClip, createAudio = (url) => new Audio(url),
  createURL = (blob) => URL.createObjectURL(blob), revokeURL = (url) => URL.revokeObjectURL(url) }) {
  const clips = new Map();
  let sequence = 0;
  let audio = null;
  let selected = null;
  const state = (control, value, message = "") => {
    control.dataset.state = value;
    control.dataset.message = message;
    control.setAttribute("aria-busy", String(value === "loading"));
    control.setAttribute("aria-label", `${value === "error" ? "Retry" : "Play"} AI-generated pronunciation: ${control.textContent}${message ? `. ${message}` : ""}`);
    control.title = message || "Play AI-generated pronunciation";
  };
  function stop() {
    sequence++;
    if (audio) { audio.pause(); audio.currentTime = 0; audio = null; }
    if (selected) state(selected, "ready");
    selected = null;
  }
  async function play(control, scope) {
    stop();
    selected = control;
    const ticket = sequence;
    const key = JSON.stringify([scope.session, scope.lesson_id, control.dataset.spanId]);
    let clip = clips.get(key);
    try {
      if (!clip) {
        state(control, "loading");
        clip = fetchClip({...scope, span_id: control.dataset.spanId}).then(createURL);
        clips.set(key, clip);
        clip.catch(() => { if (clips.get(key) === clip) clips.delete(key); });
      }
      const url = await clip;
      if (ticket !== sequence) return;
      audio = createAudio(url);
      const playing = audio;
      audio.onerror = () => {
        if (ticket !== sequence) return;
        playing.pause(); audio = null;
        state(control, "error", "Could not play. Click again to retry.");
      };
      audio.onended = () => { if (ticket === sequence) { state(control, "ready"); audio = null; } };
      state(control, "playing");
      await playing.play();
      if (ticket !== sequence) { playing.pause(); return; }
    } catch (error) {
      if (ticket !== sequence) return;
      if (audio) { audio.pause(); audio = null; }
      state(control, "error", error?.name === "NotAllowedError"
        ? "Audio ready. Click again to play." : "Could not play. Click again to retry.");
    }
  }
  function bind(root, scope) {
    for (const control of root.querySelectorAll(".pronunciation")) {
      state(control, "ready");
      control.addEventListener("click", () => {
        // Dragging across the text must remain a selection, not a playback action.
        if (globalThis.getSelection?.()?.isCollapsed === false) return;
        void play(control, scope);
      });
      control.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          void play(control, scope);
        }
      });
    }
  }
  async function close() {
    stop();
    for (const clip of clips.values()) { try { revokeURL(await clip); } catch { /* failed fetch */ } }
    clips.clear();
  }
  return { play, stop, bind, close };
}
