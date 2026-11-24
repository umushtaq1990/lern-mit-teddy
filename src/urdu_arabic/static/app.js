let currentLesson = null;
let currentPartIndex = 0;
let currentSentenceIndex = -1;
let currentQuestionId = null;
let mediaRecorder = null;
let recordedChunks = [];

// Populated from GET /api/languages -- the frontend has no hardcoded
// language list, so a new language the backend registry gains shows up
// here automatically.
let languages = [];
let currentLanguage = (() => {
  try {
    return localStorage.getItem("urdu_arabic_language") || "ur";
  } catch {
    return "ur";
  }
})();

const loginView = document.getElementById("login-view");
const lessonsView = document.getElementById("lessons-view");
const slideView = document.getElementById("slide-view");

// Small set of inline icons (no image-generation tool available) that pop in
// per concept for visual variety/engagement.
const ICONS = [
  '<svg viewBox="0 0 24 24" fill="none" stroke="#0B6E4F" stroke-width="1.5"><path d="M4 4h10a2 2 0 0 1 2 2v14H6a2 2 0 0 1-2-2V4z"/><path d="M16 4h4v16h-4"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 7v5l3 3"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#E07A5F" stroke-width="1.5"><path d="M12 2l2.6 6.9L22 10l-5.5 4.8L18 22l-6-3.6L6 22l1.5-7.2L2 10l7.4-1.1z"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#0B6E4F" stroke-width="1.5"><path d="M12 2a7 7 0 0 0-4 12.7V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.3A7 7 0 0 0 12 2z"/><path d="M10 21h4"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
];

async function api(path, options = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...options });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

function show(view) {
  loginView.hidden = view !== "login";
  lessonsView.hidden = view !== "lessons";
  slideView.hidden = view !== "slide";
}

function applyLanguage(language) {
  const meta = languages.find((l) => l.code === language) || languages[0];
  if (!meta) return;
  currentLanguage = meta.code;
  try {
    localStorage.setItem("urdu_arabic_language", currentLanguage);
  } catch {
    // ignore (private browsing, etc.) -- just a per-viewer convenience
  }
  document.documentElement.lang = meta.code;
  document.documentElement.dir = meta.dir;
  document.querySelectorAll("#language-picker button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.code === meta.code);
  });
}

async function loadLanguages() {
  const data = await api("/api/languages");
  languages = data.languages;
  const picker = document.getElementById("language-picker");
  picker.innerHTML = "";
  languages.forEach((lang) => {
    const btn = document.createElement("button");
    btn.className = "lang-btn";
    btn.dataset.code = lang.code;
    btn.textContent = lang.label;
    btn.addEventListener("click", () => {
      applyLanguage(lang.code);
      if (!slideView.hidden) {
        renderPart();
      } else if (!lessonsView.hidden) {
        showLessons();
      }
    });
    picker.appendChild(btn);
  });
  applyLanguage(currentLanguage);
}

async function checkLogin() {
  await loadLanguages();
  const data = await api("/api/me");
  if (data.user) {
    showLessons();
  }
}

document.getElementById("request-otp-btn").addEventListener("click", async () => {
  const identifier = document.getElementById("login-identifier").value.trim();
  if (!identifier) return;
  await api("/api/auth/request-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier }),
  });
  document.getElementById("otp-box").hidden = false;
});

document.getElementById("verify-otp-btn").addEventListener("click", async () => {
  const identifier = document.getElementById("login-identifier").value.trim();
  const code = document.getElementById("otp-code").value.trim();
  await api("/api/auth/verify-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifier, code }),
  });
  showLessons();
});

async function showLessons() {
  show("lessons");
  const data = await api("/api/lessons");
  const list = document.getElementById("lessons-list");
  list.innerHTML = "";
  data.lessons.forEach((lesson) => {
    const row = document.createElement("div");
    row.className = "lesson-row";

    const header = document.createElement("div");
    header.className = "lesson-header";

    const title = lesson.title[currentLanguage] || lesson.title.ur;

    const titleBtn = document.createElement("button");
    titleBtn.className = "lesson-item";
    titleBtn.textContent = `${title} — ${lesson.part_count}`;
    titleBtn.addEventListener("click", () => openLesson(lesson.id));

    const toggleBtn = document.createElement("button");
    toggleBtn.className = "lesson-toggle";
    toggleBtn.textContent = "+";

    header.appendChild(titleBtn);
    header.appendChild(toggleBtn);

    const subList = document.createElement("div");
    subList.className = "lesson-parts";
    subList.hidden = true;
    (lesson.parts || []).forEach((part, index) => {
      const partTitle = part.title[currentLanguage] || part.title.ur;
      const partBtn = document.createElement("button");
      partBtn.className = "lesson-part-item";
      partBtn.textContent = `${index + 1}. ${partTitle}`;
      partBtn.addEventListener("click", () => openLesson(lesson.id, index));
      subList.appendChild(partBtn);
    });

    toggleBtn.addEventListener("click", () => {
      subList.hidden = !subList.hidden;
      toggleBtn.textContent = subList.hidden ? "+" : "−";
    });

    row.appendChild(header);
    row.appendChild(subList);
    list.appendChild(row);
  });
  if (data.lessons.length === 0) {
    list.textContent = "ابھی کوئی سبق تیار نہیں ہے۔";
  }
}

document.getElementById("back-to-lessons-btn").addEventListener("click", () => {
  pauseAudio();
  showLessons();
});

async function openLesson(lessonId, partIndex = 0) {
  currentLesson = await api(`/api/lessons/${lessonId}`);
  currentPartIndex = partIndex;
  show("slide");
  renderPart();
}

function pauseAudio() {
  const audio = document.getElementById("part-audio");
  audio.pause();
  audio.currentTime = 0;
}

function renderPart() {
  const part = currentLesson.parts[currentPartIndex];
  const narration = part.narration[currentLanguage] || part.narration.ur;
  currentSentenceIndex = -1;
  currentQuestionId = null;

  const lessonTitle = currentLesson.title[currentLanguage] || currentLesson.title.ur;
  document.getElementById("slide-progress").textContent =
    `${lessonTitle} — ${currentPartIndex + 1} / ${currentLesson.parts.length}`;
  document.getElementById("part-arabic").textContent = part.arabic_example || "";
  document.getElementById("part-title").textContent = part.title[currentLanguage] || part.title.ur;

  const icon = document.getElementById("slide-icon");
  icon.innerHTML = ICONS[currentPartIndex % ICONS.length];
  icon.classList.remove("visible");
  requestAnimationFrame(() => icon.classList.add("visible"));

  const sentenceEl = document.getElementById("sentence-text");
  sentenceEl.textContent = "";
  sentenceEl.classList.remove("visible");

  document.getElementById("question-box").hidden = true;
  document.getElementById("question-text-display").textContent =
    part.question[currentLanguage] || part.question.ur;
  document.getElementById("question-answer").value = "";
  document.getElementById("answer-status").textContent = "";
  document.getElementById("answer-reveal").hidden = true;
  document.getElementById("next-part-btn").hidden = true;
  recordedChunks = [];

  const audio = document.getElementById("part-audio");
  audio.src = narration.audio_url;
  audio.currentTime = 0;

  const playBtn = document.getElementById("play-btn");
  playBtn.hidden = false;
  playBtn.textContent = "▶";
}

document.getElementById("play-btn").addEventListener("click", () => {
  const audio = document.getElementById("part-audio");
  audio.play();
  document.getElementById("play-btn").hidden = true;
});

// Pop in / pop out each sentence exactly in sync with its real narration
// timing (Edge TTS SentenceBoundary offsets baked in by
// generate_concept_slides.py), not a guessed interval.
document.getElementById("part-audio").addEventListener("timeupdate", (e) => {
  const part = currentLesson.parts[currentPartIndex];
  const narration = part.narration[currentLanguage] || part.narration.ur;
  const t = e.target.currentTime;
  const idx = narration.sentences.findIndex((s) => t >= s.start && t < s.end);
  if (idx !== -1 && idx !== currentSentenceIndex) {
    currentSentenceIndex = idx;
    const sentenceEl = document.getElementById("sentence-text");
    sentenceEl.classList.remove("visible");
    setTimeout(() => {
      sentenceEl.textContent = narration.sentences[idx].text;
      requestAnimationFrame(() => sentenceEl.classList.add("visible"));
    }, 150);
  }
});

document.getElementById("part-audio").addEventListener("ended", () => {
  document.getElementById("question-box").hidden = false;
});

document.getElementById("record-btn").addEventListener("click", async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recordedChunks = [];
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (e) => recordedChunks.push(e.data);
  mediaRecorder.start();
  document.getElementById("record-btn").hidden = true;
  document.getElementById("stop-record-btn").hidden = false;
});

document.getElementById("stop-record-btn").addEventListener("click", () => {
  mediaRecorder.stop();
  document.getElementById("record-btn").hidden = false;
  document.getElementById("stop-record-btn").hidden = true;
});

document.getElementById("submit-answer-btn").addEventListener("click", async () => {
  const text = document.getElementById("question-answer").value.trim();
  const statusEl = document.getElementById("answer-status");
  const part = currentLesson.parts[currentPartIndex];

  const params = new URLSearchParams({
    lesson_id: currentLesson.id,
    part_id: part.id,
    language: currentLanguage,
  });
  if (text) params.set("text", text);

  const formData = new FormData();
  if (!text && recordedChunks.length) {
    const blob = new Blob(recordedChunks, { type: "audio/webm" });
    formData.append("audio", blob, "answer.webm");
  }

  statusEl.textContent = "بھیجا جا رہا ہے...";
  const res = await fetch(`/api/questions?${params.toString()}`, {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  if (!res.ok) {
    statusEl.textContent = "خرابی: جواب نہیں بھیجا جا سکا";
    return;
  }
  const { id } = await res.json();
  currentQuestionId = id;
  statusEl.textContent = "آپ کے جواب کا جائزہ لیا جا رہا ہے...";
  pollAnswer(id);
});

document.getElementById("skip-btn").addEventListener("click", () => {
  advancePart();
});

document.getElementById("next-part-btn").addEventListener("click", () => {
  advancePart();
});

function advancePart() {
  pauseAudio();
  if (currentPartIndex < currentLesson.parts.length - 1) {
    currentPartIndex += 1;
    renderPart();
  } else {
    document.getElementById("slide-card").innerHTML = "<p>یہ سبق مکمل ہوگیا!</p>";
    document.getElementById("question-box").hidden = true;
  }
}

function pollAnswer(id) {
  const statusEl = document.getElementById("answer-status");
  const reveal = document.getElementById("answer-reveal");
  const interval = setInterval(async () => {
    if (id !== currentQuestionId) {
      clearInterval(interval);
      return;
    }
    const data = await api(`/api/questions/${id}`);
    if (data.status === "answered") {
      clearInterval(interval);
      statusEl.textContent = "";
      reveal.hidden = false;
      document.getElementById("answer-reveal-text").textContent = data.answer_text;
      if (data.answer_audio_url) {
        document.getElementById("answer-reveal-audio").src = data.answer_audio_url;
      }
      document.getElementById("next-part-btn").hidden = false;
    } else if (data.status === "failed") {
      clearInterval(interval);
      statusEl.textContent = "معذرت، جائزہ مکمل نہیں ہو سکا۔";
      document.getElementById("next-part-btn").hidden = false;
    }
  }, 3000);
}

checkLogin();
