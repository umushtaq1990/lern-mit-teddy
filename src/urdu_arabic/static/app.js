let currentLesson = null;
let currentPartIndex = 0;
let currentSentenceIndex = -1;
let mediaRecorder = null;
let recordedChunks = [];
let currentUser = null;
let allLessons = [];

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
const historyView = document.getElementById("history-view");

// Small set of inline icons (no image-generation tool available) that pop in
// per concept for visual variety/engagement. Used as a fallback when no
// keyword below matches the concept's title.
const ICONS = [
  '<svg viewBox="0 0 24 24" fill="none" stroke="#0B6E4F" stroke-width="1.5"><path d="M4 4h10a2 2 0 0 1 2 2v14H6a2 2 0 0 1-2-2V4z"/><path d="M16 4h4v16h-4"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 7v5l3 3"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#E07A5F" stroke-width="1.5"><path d="M12 2l2.6 6.9L22 10l-5.5 4.8L18 22l-6-3.6L6 22l1.5-7.2L2 10l7.4-1.1z"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#0B6E4F" stroke-width="1.5"><path d="M12 2a7 7 0 0 0-4 12.7V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.3A7 7 0 0 0 12 2z"/><path d="M10 21h4"/></svg>',
  '<svg viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
];

// Keyword-matched icons so the slide's picture relates to the concept being
// taught (plurals, verbs, questions, ...) instead of just cycling through a
// fixed set -- still hand-drawn SVG, no image-generation tool available, but
// picked by topic rather than by position.
const TOPIC_ICONS = {
  plural: '<svg viewBox="0 0 24 24" fill="none" stroke="#0B6E4F" stroke-width="1.5"><circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><path d="M3 20c0-3 2.2-5 5-5s5 2 5 5"/><path d="M11 20c0-3 2.2-5 5-5s5 2 5 5"/></svg>',
  verb: '<svg viewBox="0 0 24 24" fill="none" stroke="#E07A5F" stroke-width="1.5"><path d="M13 3L4 14h7l-1 7 9-11h-7l1-7z"/></svg>',
  question: '<svg viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5"><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-.6.6-1.5 1-1.5 2.5"/><circle cx="12" cy="17.5" r="0.6" fill="#D4A017"/><circle cx="12" cy="12" r="10"/></svg>',
  yesno: '<svg viewBox="0 0 24 24" fill="none" stroke="#0B6E4F" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M7.5 12.5l2.5 2.5 6-6"/></svg>',
  animal: '<svg viewBox="0 0 24 24" fill="none" stroke="#E07A5F" stroke-width="1.5"><circle cx="12" cy="14" r="3.2"/><circle cx="7" cy="8" r="1.6"/><circle cx="17" cy="8" r="1.6"/><circle cx="5" cy="13" r="1.4"/><circle cx="19" cy="13" r="1.4"/></svg>',
  house: '<svg viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5"><path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg>',
  person: '<svg viewBox="0 0 24 24" fill="none" stroke="#0B6E4F" stroke-width="1.5"><circle cx="12" cy="7" r="3.5"/><path d="M4.5 20c0-4 3.3-6.5 7.5-6.5s7.5 2.5 7.5 6.5"/></svg>',
  letter: '<svg viewBox="0 0 24 24" fill="none" stroke="#E07A5F" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M7 9h10M7 12.5h6"/></svg>',
  number: '<svg viewBox="0 0 24 24" fill="none" stroke="#D4A017" stroke-width="1.5"><path d="M5 9h14M5 15h14M9 4L7 20M17 4l-2 16"/></svg>',
};

const TOPIC_KEYWORDS = [
  [["plural", "جمع"], "plural"],
  [["verb", "conjugat", "tense", "فعل", "صرف"], "verb"],
  [["question", "asking", "سوال"], "question"],
  [["yes", "no,", " no ", "نعم", "لا"], "yesno"],
  [["animal", "جانور"], "animal"],
  [["house", "door", "key", "household", "گھر"], "house"],
  [["people", "men", "teacher", "student", "boy", "لوگوں"], "person"],
  [["letter", "alphabet", "hamza", "'ayn", "pronunciation", "ہمز"], "letter"],
  [["number", "عدد"], "number"],
];

function pickIcon(part) {
  const haystack = `${part.title.en || ""} ${part.title.ur || ""}`.toLowerCase();
  for (const [keywords, category] of TOPIC_KEYWORDS) {
    if (keywords.some((kw) => haystack.includes(kw))) {
      return TOPIC_ICONS[category];
    }
  }
  return null;
}

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
  historyView.hidden = view !== "history";
}

// Static UI chrome (not lesson content) -- also language-keyed, so a new
// language added to the backend registry needs an entry here too for the
// chrome to be fully translated (lesson content itself needs no code change).
const UI_STRINGS = {
  ur: {
    brand: "لسان",
    appTitle: "لسان — اردو میں عربی سیکھیں",
    loginPrompt: "اپنا فون نمبر یا ای میل درج کریں",
    sendCode: "کوڈ بھیجیں",
    enterCode: "کوڈ درج کریں (سرور لاگ میں دیکھیں)",
    verify: "تصدیق کریں",
    welcomeHeading: "اسباق",
    welcomeText: "بائیں پینل سے کوئی سبق یا موضوع منتخب کریں۔",
    loggedInAs: "لاگ ان بطور:",
    logout: "لاگ آؤٹ",
    backToLessons: "&larr; اسباق کی فہرست",
    chatHeading: "چیٹ",
    examplesHeading: "مثالیں",
    feedbackLabel: "کیا یہ مفید تھا؟",
    chatPlaceholder: "کچھ بھی لکھیں یا پوچھیں...",
    record: "&#127908; ریکارڈ کریں",
    stopRecord: "&#9209; روکیں",
    send: "بھیجیں",
    nextPart: "اگلا تصور &larr;",
    noLessons: "ابھی کوئی سبق تیار نہیں ہے۔",
    lessonComplete: "یہ سبق مکمل ہوگیا!",
    sending: "بھیجا جا رہا ہے...",
    reviewing: "آپ کے جواب کا جائزہ لیا جا رہا ہے...",
    sendError: "خرابی: جواب نہیں بھیجا جا سکا",
    reviewError: "معذرت، جائزہ مکمل نہیں ہو سکا۔",
    about: "تعارف",
    contact: "رابطہ کریں",
    aboutTitle: "لسان کے بارے میں",
    aboutBody:
      "لسان اردو بولنے والوں کے لیے عربی سیکھنے کا ایک آسان اور مؤثر پلیٹ فارم ہے۔ " +
      "(یہ ابتدائی متن ہے، بعد میں حسبِ ضرورت تبدیل کیا جا سکتا ہے۔)",
    contactTitle: "ہم سے رابطہ کریں",
    contactBody:
      "سوالات یا رائے کے لیے ہمیں ای میل کریں: " +
      '<a href="mailto:contact@example.com">contact@example.com</a>' +
      " (یہ ایک نمونہ پتہ ہے، بعد میں تبدیل کریں۔)",
    historyNav: "گفتگو کی تاریخ",
    historyHeading: "آپ کی گفتگو کی تاریخ",
    noHistory: "ابھی کوئی سوال نہیں پوچھا گیا۔",
  },
  en: {
    brand: "Lisan",
    appTitle: "Lisan — Learn Arabic in English",
    loginPrompt: "Enter your phone number or email",
    sendCode: "Send code",
    enterCode: "Enter the code (check the server log)",
    verify: "Verify",
    welcomeHeading: "Lessons",
    welcomeText: "Select a lesson or topic from the left panel.",
    loggedInAs: "Logged in as:",
    logout: "Logout",
    backToLessons: "&larr; Lessons list",
    chatHeading: "Chat",
    examplesHeading: "Examples",
    feedbackLabel: "Was this helpful?",
    chatPlaceholder: "Type anything, or ask a question...",
    record: "&#127908; Record",
    stopRecord: "&#9209; Stop",
    send: "Send",
    nextPart: "Next concept &rarr;",
    noLessons: "No lessons are ready yet.",
    lessonComplete: "Lesson complete!",
    sending: "Sending...",
    reviewing: "Reviewing your answer...",
    sendError: "Error: could not send your answer",
    reviewError: "Sorry, the review could not be completed.",
    about: "About",
    contact: "Contact Us",
    aboutTitle: "About Lisan",
    aboutBody:
      "Lisan is a simple, effective platform for Urdu speakers to learn Arabic. " +
      "(This is placeholder text -- edit it to whatever you'd like later.)",
    contactTitle: "Contact Us",
    contactBody:
      "For questions or feedback, email us at " +
      '<a href="mailto:contact@example.com">contact@example.com</a>' +
      " (this is a placeholder address -- replace it later).",
    historyNav: "Chat History",
    historyHeading: "Your Chat History",
    noHistory: "You haven't asked any questions yet.",
  },
};

function t(key) {
  const table = UI_STRINGS[currentLanguage] || UI_STRINGS[DEFAULT_LANG];
  return (table && table[key]) || UI_STRINGS[DEFAULT_LANG][key] || key;
}

const DEFAULT_LANG = "ur";

function applyUiStrings() {
  document.title = t("appTitle");
  document.getElementById("brand").textContent = t("brand");
  document.querySelector("#login-view h1").textContent = t("appTitle");
  document.querySelector("#login-view > p").textContent = t("loginPrompt");
  document.getElementById("request-otp-btn").textContent = t("sendCode");
  document.querySelector("#otp-box p").textContent = t("enterCode");
  document.getElementById("verify-otp-btn").textContent = t("verify");
  document.querySelector("#lessons-view h2").textContent = t("welcomeHeading");
  document.getElementById("lessons-welcome-text").textContent = t("welcomeText");
  document.getElementById("logout-btn").textContent = t("logout");
  document.getElementById("back-to-lessons-btn").title = t("backToLessons").replace(/&larr;\s*/, "");
  document.getElementById("chat-heading").textContent = t("chatHeading");
  document.getElementById("chat-fab-label").textContent = t("chatHeading");
  document.getElementById("feedback-label").textContent = t("feedbackLabel");
  document.getElementById("question-answer").placeholder = t("chatPlaceholder");
  document.getElementById("record-btn").innerHTML = t("record");
  document.getElementById("stop-record-btn").innerHTML = t("stopRecord");
  document.getElementById("submit-answer-btn").textContent = t("send");
  document.getElementById("next-part-btn").innerHTML = t("nextPart");
  document.getElementById("about-link").textContent = t("about");
  document.getElementById("contact-link").textContent = t("contact");
  document.getElementById("sidebar-history-btn").textContent = t("historyNav");
  document.getElementById("history-heading").textContent = t("historyHeading");
  updateUserInfo();
  renderSidebarNav();
}

function updateUserInfo() {
  const el = document.getElementById("user-identifier");
  if (el) {
    el.textContent = currentUser ? `${t("loggedInAs")} ${currentUser.identifier}` : "";
  }
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
  applyUiStrings();
  if (currentUser) {
    logClientEvent("language_switched", null, null, { language: meta.code });
  }
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
      } else if (!historyView.hidden) {
        showHistory();
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
    currentUser = data.user;
    await loadLessons();
    showSidebar();
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
  const me = await api("/api/me");
  currentUser = me.user;
  await loadLessons();
  showSidebar();
  showLessons();
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  currentUser = null;
  allLessons = [];
  currentLesson = null;
  pauseAudio();
  closeSidebarDrawer();
  document.getElementById("sidebar").hidden = true;
  document.getElementById("sidebar-toggle-btn").hidden = true;
  document.getElementById("login-identifier").value = "";
  document.getElementById("otp-code").value = "";
  document.getElementById("otp-box").hidden = true;
  show("login");
});

function showSidebar() {
  document.getElementById("sidebar").hidden = false;
  document.getElementById("sidebar-toggle-btn").hidden = false;
  updateUserInfo();
}

function openSidebarDrawer() {
  document.getElementById("sidebar").classList.add("open");
  document.getElementById("sidebar-backdrop").classList.add("visible");
}

function closeSidebarDrawer() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebar-backdrop").classList.remove("visible");
}

document.getElementById("sidebar-backdrop").addEventListener("click", closeSidebarDrawer);

// The header's hamburger button does double duty: it slides the topics
// drawer in on narrow screens (where the sidebar is off-canvas) and, on any
// screen size, opens the About/Contact Us dropdown right under it.
const sidebarToggleBtn = document.getElementById("sidebar-toggle-btn");
const moreMenuDropdown = document.getElementById("more-menu-dropdown");

sidebarToggleBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const sidebar = document.getElementById("sidebar");
  if (sidebar.classList.contains("open")) {
    closeSidebarDrawer();
  } else {
    openSidebarDrawer();
  }
  moreMenuDropdown.hidden = !moreMenuDropdown.hidden;
});

document.addEventListener("click", (e) => {
  if (!moreMenuDropdown.hidden && !document.getElementById("more-menu").contains(e.target)) {
    moreMenuDropdown.hidden = true;
  }
});

function openInfoModal(titleKey, bodyKey) {
  moreMenuDropdown.hidden = true;
  document.getElementById("info-modal-title").textContent = t(titleKey);
  document.getElementById("info-modal-body").innerHTML = t(bodyKey);
  document.getElementById("info-modal-backdrop").hidden = false;
}

function closeInfoModal() {
  document.getElementById("info-modal-backdrop").hidden = true;
}

document.getElementById("about-link").addEventListener("click", () => openInfoModal("aboutTitle", "aboutBody"));
document.getElementById("contact-link").addEventListener("click", () => openInfoModal("contactTitle", "contactBody"));
document.getElementById("info-modal-close").addEventListener("click", closeInfoModal);
document.getElementById("info-modal-backdrop").addEventListener("click", (e) => {
  if (e.target.id === "info-modal-backdrop") closeInfoModal();
});

async function loadLessons() {
  const data = await api("/api/lessons");
  allLessons = data.lessons;
  renderSidebarNav();
}

// Persistent left-panel nav: every topic (lesson) and its subtopics (parts),
// foldable, with direct links -- lives in the sidebar so it's reachable from
// any view, not just the lessons list.
function renderSidebarNav() {
  const nav = document.getElementById("sidebar-nav");
  if (!nav) return;
  nav.innerHTML = "";
  if (allLessons.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sidebar-empty";
    empty.textContent = t("noLessons");
    nav.appendChild(empty);
    return;
  }
  allLessons.forEach((lesson) => {
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
    nav.appendChild(row);
  });
}

function showLessons() {
  show("lessons");
}

document.getElementById("sidebar-history-btn").addEventListener("click", () => {
  closeSidebarDrawer();
  showHistory();
});

// Shared bubble-pair builder: one past (or in-flight) exchange, rendered the
// same way whether it's the full cross-lesson Chat History view or the
// current concept's inline chat. `q` can be a real /api/questions row or a
// synthetic "pending" one for an optimistic just-sent message.
// Like/dislike for one specific chat answer -- distinct from the lesson-
// level thumbs-up/down in #feedback-row, which rates the whole concept,
// not an individual reply.
function buildAnswerRatingRow(questionId, currentRating) {
  const row = document.createElement("div");
  row.className = "answer-rating-row";

  const rate = async (rating, upBtn, downBtn) => {
    try {
      await api(`/api/questions/${questionId}/rate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating }),
      });
      upBtn.classList.toggle("active", rating === "up");
      downBtn.classList.toggle("active", rating === "down");
      logClientEvent("chat_answer_rated", null, null, { question_id: questionId, rating });
    } catch {
      // Best-effort -- a failed rating click shouldn't interrupt reading the answer.
    }
  };

  const upBtn = document.createElement("button");
  upBtn.className = "answer-rating-btn" + (currentRating === "up" ? " active" : "");
  upBtn.setAttribute("aria-label", "like this answer");
  upBtn.innerHTML = "&#128077;";

  const downBtn = document.createElement("button");
  downBtn.className = "answer-rating-btn" + (currentRating === "down" ? " active" : "");
  downBtn.setAttribute("aria-label", "dislike this answer");
  downBtn.innerHTML = "&#128078;";

  upBtn.addEventListener("click", () => rate("up", upBtn, downBtn));
  downBtn.addEventListener("click", () => rate("down", upBtn, downBtn));

  row.appendChild(upBtn);
  row.appendChild(downBtn);
  return row;
}

function buildChatEntry(q, { showMeta = true } = {}) {
  const entry = document.createElement("div");
  entry.className = "chat-entry";

  if (showMeta) {
    const lesson = allLessons.find((l) => l.id === q.lesson_id);
    const lessonTitle = lesson ? (lesson.title[q.language] || lesson.title.ur) : q.lesson_id;
    const part = lesson && lesson.parts ? lesson.parts.find((p) => p.id === q.part_id) : null;
    const partTitle = part ? (part.title[q.language] || part.title.ur) : q.part_id;
    const meta = document.createElement("p");
    meta.className = "chat-meta";
    meta.textContent = `${lessonTitle} — ${partTitle}`;
    entry.appendChild(meta);
  }

  const qBubble = document.createElement("div");
  qBubble.className = "chat-bubble chat-bubble-user";
  if (q.question_text) {
    const p = document.createElement("p");
    p.textContent = q.question_text;
    qBubble.appendChild(p);
  }
  if (q.question_audio_url) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = q.question_audio_url;
    qBubble.appendChild(audio);
  }
  entry.appendChild(qBubble);

  const aBubble = document.createElement("div");
  aBubble.className = "chat-bubble chat-bubble-answer";
  const p = document.createElement("p");
  if (q.status === "answered") {
    p.textContent = q.answer_text || "";
    aBubble.appendChild(p);
    if (q.answer_audio_url) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = q.answer_audio_url;
      aBubble.appendChild(audio);
    }
    if (q.id) {
      aBubble.appendChild(buildAnswerRatingRow(q.id, q.rating));
    }
  } else if (q.status === "failed") {
    p.textContent = t("reviewError");
    aBubble.appendChild(p);
  } else {
    p.textContent = t("reviewing");
    aBubble.appendChild(p);
  }
  entry.appendChild(aBubble);

  return entry;
}

// Chat-history view: every past question (text and/or recorded audio) and
// its answer (text and/or synthesized audio), reusing rows already saved by
// /api/questions -- nothing new to persist, just a way to browse it.
async function showHistory() {
  show("history");
  const data = await api("/api/questions");
  const list = document.getElementById("history-list");
  list.innerHTML = "";

  if (data.questions.length === 0) {
    const empty = document.createElement("p");
    empty.className = "sidebar-empty";
    empty.textContent = t("noHistory");
    list.appendChild(empty);
    return;
  }

  data.questions.forEach((q) => list.appendChild(buildChatEntry(q)));
}

document.getElementById("back-to-lessons-btn").addEventListener("click", () => {
  pauseAudio();
  showLessons();
});

// Fire-and-forget behavioral event log -- used for signals only the
// frontend observes (login/logout, questions and feedback are logged
// server-side at their own endpoints instead).
function logClientEvent(eventType, lessonId = null, partId = null, metadata = null) {
  api("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_type: eventType, lesson_id: lessonId, part_id: partId, language: currentLanguage, metadata }),
  }).catch(() => {});
}

async function openLesson(lessonId, partIndex = 0) {
  closeSidebarDrawer();
  currentLesson = await api(`/api/lessons/${lessonId}`);
  currentPartIndex = partIndex;
  show("slide");
  logClientEvent("lesson_opened", lessonId);
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

  const lessonTitle = currentLesson.title[currentLanguage] || currentLesson.title.ur;
  document.getElementById("slide-progress").textContent =
    `${lessonTitle} — ${currentPartIndex + 1} / ${currentLesson.parts.length}`;
  document.getElementById("part-arabic").textContent = part.arabic_example || "";
  document.getElementById("part-title").textContent = part.title[currentLanguage] || part.title.ur;

  // A "comparison" concept (today: nahw vs sarf) replaces the single fading
  // narration sentence with a static two-column table of its own worked
  // examples (each with its own audio) -- so the whole-part summary
  // arabic_example clip (and its now-hidden arabic-row text) is redundant
  // there, and must be skipped entirely, not just visually hidden: leaving
  // it wired up meant it kept auto-playing after the narration ended,
  // reading a word out loud with no matching text visible anywhere.
  const isComparison = part.layout === "comparison" && !!part.comparison;
  const isCategoryVocab = !!(part.categories && part.categories.length);

  const exampleBtn = document.getElementById("example-play-btn");
  const exampleAudio = document.getElementById("example-audio");
  if (part.example_audio_url && !isComparison) {
    exampleAudio.src = part.example_audio_url;
    exampleBtn.hidden = false;
  } else {
    exampleAudio.removeAttribute("src");
    exampleBtn.hidden = true;
  }

  // A generated illustration (part.image_url) takes priority when present;
  // the hand-drawn keyword-matched icon is the fallback for concepts that
  // don't have one yet (generation is being rolled out lecture by lecture).
  const slideImage = document.getElementById("slide-image");
  const icon = document.getElementById("slide-icon");
  if (part.image_url) {
    icon.hidden = true;
    icon.classList.remove("visible");
    slideImage.hidden = false;
    slideImage.classList.remove("visible");
    slideImage.src = part.image_url;
    slideImage.onload = () => requestAnimationFrame(() => slideImage.classList.add("visible"));
  } else {
    slideImage.hidden = true;
    slideImage.classList.remove("visible");
    icon.hidden = false;
    icon.innerHTML = pickIcon(part) || ICONS[currentPartIndex % ICONS.length];
    icon.classList.remove("visible");
    requestAnimationFrame(() => icon.classList.add("visible"));
  }

  const sentenceEl = document.getElementById("sentence-text");
  sentenceEl.textContent = "";
  sentenceEl.classList.remove("visible");

  // The chat panel is a floating, LinkedIn-style popup now: it exists and
  // loads its content for every slide, but starts closed each time (the
  // chat-fab button toggles it open) rather than always sitting open
  // inline, taking up space whether or not the learner wants it right now.
  const chatBox = document.getElementById("question-box");
  chatBox.hidden = false;
  chatBox.classList.remove("open");
  document.getElementById("chat-fab").hidden = false;
  document.getElementById("question-answer").value = "";
  document.getElementById("answer-status").textContent = "";
  document.getElementById("part-chat-list").innerHTML = "";
  recordedChunks = [];

  loadPartChat(currentLesson.id, part.id);
  loadFeedbackState(currentLesson.id, part.id);
  logClientEvent("part_viewed", currentLesson.id, part.id);

  const audio = document.getElementById("part-audio");
  audio.src = narration.audio_url;
  audio.currentTime = 0;

  document.getElementById("play-btn").textContent = "▶";
  const seekEl = document.getElementById("player-seek");
  seekEl.value = 0;
  seekEl.disabled = true;
  document.getElementById("player-time").textContent = "0:00 / 0:00";

  document.getElementById("slide-card").classList.toggle("comparison-layout", isComparison);
  document.getElementById("slide-card").classList.toggle("categories-layout", isCategoryVocab);
  document.getElementById("arabic-row").hidden = isComparison;
  document.getElementById("sentence-box").hidden = isComparison;
  document.getElementById("comparison-section").hidden = !isComparison;

  if (isComparison) {
    renderComparison(part);
    document.getElementById("examples-section").hidden = true;
  } else {
    renderExamples(part);
  }
}

// Compact, horizontal layout: a small picture beside the Arabic text (the
// text sits to its reading-direction side automatically, since direction
// is inherited from <html dir>, not hardcoded left/right), with
// transliteration + translation stacked underneath -- sized to fit several
// per row rather than one large card per example.
function buildExampleCard(example, badgeLabel) {
  const card = document.createElement("div");
  card.className = "example-card";

  if (badgeLabel !== undefined) {
    const badge = document.createElement("span");
    badge.className = "example-badge";
    badge.textContent = String(badgeLabel);
    card.appendChild(badge);
  }

  if (example.image_url) {
    const img = document.createElement("img");
    img.className = "example-image";
    img.src = example.image_url;
    img.alt = "";
    card.appendChild(img);
  }

  const textWrap = document.createElement("div");
  textWrap.className = "example-text";

  const arabicRow = document.createElement("div");
  arabicRow.className = "example-arabic-row";

  const arabicP = document.createElement("p");
  arabicP.className = "example-arabic";
  arabicP.textContent = example.arabic;
  arabicRow.appendChild(arabicP);

  const ruleText = example.rule && (example.rule[currentLanguage] || example.rule.ur);
  let ruleEl = null;
  if (ruleText) {
    ruleEl = document.createElement("p");
    ruleEl.className = "example-rule";
    ruleEl.textContent = ruleText;
    ruleEl.hidden = true;
  }

  if (example.audio_url || ruleEl) {
    const playExampleBtn = document.createElement("button");
    playExampleBtn.className = "example-play-btn";
    playExampleBtn.setAttribute("aria-label", "play example");
    playExampleBtn.innerHTML = "&#128264;";
    const exampleAudioEl = example.audio_url ? new Audio(example.audio_url) : null;
    // Clicking the speaker both plays the pronunciation and reveals *why*
    // the word takes this form -- the grammar rule being demonstrated --
    // instead of leaving the learner to infer it from the translation alone.
    playExampleBtn.addEventListener("click", () => {
      if (exampleAudioEl) {
        exampleAudioEl.currentTime = 0;
        exampleAudioEl.play();
        logClientEvent("example_played", currentLesson.id, currentLesson.parts[currentPartIndex].id, {
          example_id: example.id,
        });
      }
      if (ruleEl) {
        ruleEl.hidden = !ruleEl.hidden;
        playExampleBtn.classList.toggle("active", !ruleEl.hidden);
        if (!ruleEl.hidden) {
          logClientEvent("rule_revealed", currentLesson.id, currentLesson.parts[currentPartIndex].id, {
            example_id: example.id,
          });
        }
      }
    });
    arabicRow.appendChild(playExampleBtn);
  }
  textWrap.appendChild(arabicRow);

  if (example.transliteration) {
    const translit = document.createElement("p");
    translit.className = "example-translit";
    translit.textContent = example.transliteration;
    textWrap.appendChild(translit);
  }

  const translation = document.createElement("p");
  translation.className = "example-translation";
  translation.textContent =
    (example.translation && (example.translation[currentLanguage] || example.translation.ur)) || "";
  textWrap.appendChild(translation);

  if (ruleEl) {
    textWrap.appendChild(ruleEl);
  }

  card.appendChild(textWrap);
  return card;
}

// Several worked examples per concept (Arabic phrase + transliteration +
// translation), each with its own slow Arabic pronunciation and its own
// generated picture -- shown immediately, not gated behind the narration.
function renderExamples(part) {
  const section = document.getElementById("examples-section");
  const list = document.getElementById("examples-list");
  const toggleBtn = document.getElementById("examples-toggle-btn");
  const categoryTabsEl = document.getElementById("examples-category-tabs");
  list.innerHTML = "";
  categoryTabsEl.innerHTML = "";
  categoryTabsEl.hidden = true;

  if (!part.examples || !part.examples.length) {
    section.hidden = true;
    return;
  }

  // A vocabulary slide (part.categories set): all examples are available at
  // once, grouped into picker buttons (Animals / Home / ...) instead of a
  // voice-synced reveal or a single flat list -- the learner switches
  // sections themselves rather than listening for a narration cue.
  if (part.categories && part.categories.length) {
    section.hidden = false;
    section.classList.remove("collapsed");
    toggleBtn.hidden = true;
    renderCategorizedExamples(part, part.categories[0].id);
    return;
  }

  if (part.sync && part.sync.length) {
    // Voice-synced reveal (same idea as the comparison layout's word
    // groups): every card exists but starts "pending" (hidden), and
    // handleExampleSync un-hides each one exactly when the narration
    // reaches the sentence that explains it -- no manual expand/collapse,
    // since the whole point is that it appears on its own as you listen.
    section.hidden = false;
    section.classList.remove("collapsed");
    toggleBtn.hidden = true;
    part.examples.forEach((example, index) => {
      const card = buildExampleCard(example, index + 1);
      card.id = `example-card-${example.id}`;
      card.classList.add("pending");
      list.appendChild(card);
    });
    return;
  }

  // Fallback for a part with examples but no sync data yet: the older
  // collapsed-toggle list, everything available immediately once expanded.
  section.hidden = false;
  section.classList.add("collapsed");
  toggleBtn.hidden = false;
  document.getElementById("examples-toggle-label").textContent =
    `${part.examples.length} ${t("examplesHeading")}`;
  part.examples.forEach((example, index) => {
    list.appendChild(buildExampleCard(example, index + 1));
  });
}

// Renders the category picker buttons (once) and the word list for
// whichever category is currently selected -- re-run on every tab click,
// but the tabs themselves are only (re)built here too so switching
// category doesn't need its own separate code path.
function renderCategorizedExamples(part, activeCategoryId) {
  const list = document.getElementById("examples-list");
  const categoryTabsEl = document.getElementById("examples-category-tabs");
  list.innerHTML = "";
  categoryTabsEl.innerHTML = "";
  categoryTabsEl.hidden = false;

  part.categories.forEach((category) => {
    const tab = document.createElement("button");
    tab.className = "category-tab" + (category.id === activeCategoryId ? " active" : "");
    tab.textContent = (category.label && (category.label[currentLanguage] || category.label.ur)) || category.id;
    tab.addEventListener("click", () => renderCategorizedExamples(part, category.id));
    categoryTabsEl.appendChild(tab);
  });

  part.examples
    .filter((example) => example.category === activeCategoryId)
    .forEach((example) => list.appendChild(buildExampleCard(example)));
}

// Mirrors handleComparisonSync/syncComparisonToTime, but for an ordinary
// (non-comparison) part's flat examples list: part.sync[i] = {example_id}
// reveals that one card when sentence i plays.
function handleExampleSync(part, sentenceIndex) {
  const step = part.sync && part.sync[sentenceIndex];
  if (!step || !step.example_id) return;
  const cardEl = document.getElementById(`example-card-${step.example_id}`);
  if (cardEl) {
    cardEl.classList.remove("pending");
    cardEl.classList.add("revealed");
  }
}

function syncExamplesToTime(part, narration, currentTime) {
  document.querySelectorAll("#examples-list .example-card").forEach((el) => {
    el.classList.add("pending");
    el.classList.remove("revealed");
  });
  const sentences = narration.sentences;
  let idx = sentences.findIndex((s) => currentTime >= s.start && currentTime < s.end);
  if (idx === -1 && sentences.length && currentTime >= sentences[sentences.length - 1].end) {
    idx = sentences.length - 1;
  }
  for (let i = 0; i <= idx; i++) {
    handleExampleSync(part, i);
  }
}

// A two-column "A vs B" comparison table: each column pulls its own subset
// of the concept's examples by id, so the same authored examples back both
// the collapsed-list view (for ordinary concepts) and this table view (for
// comparison concepts).
//
// Word-based grouping normally lives at the top, shared by both columns
// (part.comparison.groups[g].columns[columnId] -> example ids) -- e.g. one
// "kitab" tab and one "bayt" tab that each, when selected, swap BOTH the
// Nahw and the Sarf column to that word's examples together. A column can
// still define its own independent tabs instead (part.comparison.columns[i]
// .groups) for a concept where the two sides don't share a vocabulary axis,
// or a flat example_ids list when no grouping is needed at all.
// Drives the comparison layout's reveal-as-the-narration-speaks behavior.
// part.comparison.sync is a list parallel to the narration's sentence list
// (same index == same sentence): each entry names which column's caption
// should show that sentence's text, and optionally which word-group block
// to reveal in that column at that moment -- so every point and every
// example pops in exactly when the voice actually talks about it, instead
// of all at once or on a blind timer.
// Recomputes the comparison layout's whole reveal state (every caption,
// every example block) as a pure function of the current playback time,
// rather than trusting incremental history -- so dragging the seek slider
// backward un-reveals examples the narration hasn't reached yet, and
// jumping forward catches up and reveals everything it should have, not
// just whatever the single sentence at the drop point happens to mention.
function syncComparisonToTime(part, narration, currentTime) {
  document.querySelectorAll(".comparison-group-block").forEach((el) => {
    el.classList.add("pending");
    el.classList.remove("revealed");
  });
  document.querySelectorAll(".comparison-col-points").forEach((el) => {
    el.hidden = true;
    el.innerHTML = "";
  });
  // Reset any case-tab columns (e.g. Nahw's فاعل/زبر/زیر) back to empty
  // before replaying -- otherwise seeking backward past the point where
  // the narration first reaches this column would leave its menu built
  // and visible, when it shouldn't exist yet at that point in time.
  (part.comparison.columns || []).forEach((column, columnIndex) => {
    if (!column.case_tabs || !column.case_tabs.length) return;
    const tabsEl = document.getElementById(`comparison-col-${columnIndex}-tabs`);
    const itemsEl = document.getElementById(`comparison-col-${columnIndex}-items`);
    if (tabsEl) {
      tabsEl.innerHTML = "";
      tabsEl.hidden = true;
    }
    if (itemsEl) itemsEl.innerHTML = "";
  });

  const sentences = narration.sentences;
  let idx = sentences.findIndex((s) => currentTime >= s.start && currentTime < s.end);
  if (idx === -1 && sentences.length && currentTime >= sentences[sentences.length - 1].end) {
    idx = sentences.length - 1;
  }
  for (let i = 0; i <= idx; i++) {
    handleComparisonSync(part, i, narration);
  }
}

// Builds a column's case-tab menu (e.g. Nahw's فاعل/زبر/زیر) the first
// time the narration actually reaches it, selecting `activeTabId` (or the
// first tab if not given). Safe to call again later -- it's a no-op once
// the tabs already exist, so handleComparisonSync can call it on every
// sync step for this column without rebuilding repeatedly.
function buildCaseTabs(column, columnIndex, activeTabId) {
  const tabsEl = document.getElementById(`comparison-col-${columnIndex}-tabs`);
  if (tabsEl.childElementCount > 0) return;

  const activeIndex = Math.max(
    0,
    column.case_tabs.findIndex((tab) => tab.id === activeTabId)
  );
  tabsEl.hidden = false;
  column.case_tabs.forEach((tab, tabIndex) => {
    const tabBtn = document.createElement("button");
    tabBtn.className = "comparison-tab" + (tabIndex === activeIndex ? " active" : "");
    tabBtn.textContent = (tab.label && (tab.label[currentLanguage] || tab.label.ur)) || tab.id;
    tabBtn.addEventListener("click", () => {
      tabsEl.querySelectorAll(".comparison-tab").forEach((b) => b.classList.remove("active"));
      tabBtn.classList.add("active");
      showColumnExamples(columnIndex, tab.example_ids);
      logClientEvent("case_tab_selected", currentLesson.id, currentLesson.parts[currentPartIndex].id, {
        column_id: column.id,
        tab_id: tab.id,
      });
    });
    tabsEl.appendChild(tabBtn);
  });
  showColumnExamples(columnIndex, column.case_tabs[activeIndex].example_ids);
}

function handleComparisonSync(part, sentenceIndex, narration) {
  const sync = part.comparison && part.comparison.sync;
  const step = sync && sync[sentenceIndex];
  if (!step) return;

  const columns = part.comparison.columns || [];
  const columnIndex = columns.findIndex((column) => column.id === step.column_id);
  if (columnIndex === -1) return;
  const column = columns[columnIndex];

  const captionEl = document.getElementById(`comparison-col-${columnIndex}-points`);
  if (captionEl) {
    const sentence = narration.sentences[sentenceIndex];
    captionEl.innerHTML = "";
    captionEl.hidden = false;
    const p = document.createElement("p");
    p.className = "comparison-col-point";
    p.textContent = (sentence && sentence.text) || "";
    captionEl.appendChild(p);
  }

  // A case-tab column (e.g. Nahw's فاعل/زبر/زیر) stays empty until the
  // narration actually reaches it -- buildCaseTabs builds the menu the
  // first time any sync step touches this column (whether or not that
  // step names a specific case), then later steps just switch the active
  // tab, by reusing the same click handler the user would use manually.
  // The fixed-size menu still tracks the voice; it just never needs to
  // grow taller, or appear, before the voice gets there.
  if (column.case_tabs) {
    const tabsEl = document.getElementById(`comparison-col-${columnIndex}-tabs`);
    if (tabsEl && tabsEl.childElementCount === 0) {
      buildCaseTabs(column, columnIndex, step.case_tab_id);
    } else if (step.case_tab_id) {
      const tabButtons = tabsEl ? Array.from(tabsEl.querySelectorAll(".comparison-tab")) : [];
      const tabIndex = column.case_tabs.findIndex((tab) => tab.id === step.case_tab_id);
      if (tabIndex !== -1 && tabButtons[tabIndex]) {
        tabButtons[tabIndex].click();
      }
    }
  }

  if (step.group_id) {
    const groupEl = document.getElementById(`comparison-col-${columnIndex}-group-${step.group_id}`);
    if (groupEl) {
      groupEl.classList.remove("pending");
      groupEl.classList.add("revealed");
    }
  }
}

// Populated fresh at the top of each renderComparison call; read by
// showColumnExamples, which buildCaseTabs (module scope, called lazily
// from handleComparisonSync) also needs access to.
let comparisonExampleById = {};

function showColumnExamples(columnIndex, exampleIds) {
  const itemsEl = document.getElementById(`comparison-col-${columnIndex}-items`);
  itemsEl.innerHTML = "";
  (exampleIds || []).forEach((id) => {
    const example = comparisonExampleById[id];
    if (example) itemsEl.appendChild(buildExampleCard(example));
  });
}

function renderComparison(part) {
  comparisonExampleById = Object.fromEntries((part.examples || []).map((example) => [example.id, example]));
  const comparison = part.comparison || {};
  const columns = comparison.columns || [];
  const sharedGroups = comparison.groups;
  const sharedTabsEl = document.getElementById("comparison-shared-tabs");
  sharedTabsEl.innerHTML = "";
  sharedTabsEl.hidden = true;

  const hintEl = document.getElementById("comparison-hint");
  const hint = comparison.hint && (comparison.hint[currentLanguage] || comparison.hint.ur);
  hintEl.textContent = hint || "";
  hintEl.hidden = !hint;

  columns.forEach((column, columnIndex) => {
    const labelEl = document.getElementById(`comparison-col-${columnIndex}-label`);
    const descEl = document.getElementById(`comparison-col-${columnIndex}-desc`);
    const pointsEl = document.getElementById(`comparison-col-${columnIndex}-points`);
    const tabsEl = document.getElementById(`comparison-col-${columnIndex}-tabs`);
    tabsEl.innerHTML = "";
    tabsEl.hidden = true;
    pointsEl.innerHTML = "";
    pointsEl.hidden = true;
    labelEl.textContent = (column.label && (column.label[currentLanguage] || column.label.ur)) || "";
    const description =
      column.description && (column.description[currentLanguage] || column.description.ur);
    descEl.textContent = description || "";
    descEl.hidden = !description;
  });

  columns.forEach((column, columnIndex) => {
    const tabsEl = document.getElementById(`comparison-col-${columnIndex}-tabs`);

    // A column with its own case_tabs (today: Nahw's فاعل/زبر/زیر) shows a
    // fixed, small set of examples at a time -- selectable from a menu --
    // instead of stacking every word's every case underneath each other
    // and growing the slide taller as more cases get added. This is
    // independent of the word-grouped sync reveal below (used by Sarf).
    //
    // The menu itself stays empty until the narration first reaches this
    // column (see buildCaseTabs, called lazily from handleComparisonSync)
    // -- so nothing shows up before the voice has actually introduced it,
    // even though the container's size never changes once it does.
    if (column.case_tabs && column.case_tabs.length) {
      return;
    }

    // Otherwise, if this column participates in the shared word groups
    // (today: Sarf), stack each word's example(s) under its own label,
    // starting "pending" (hidden) -- the narration timeupdate handler
    // reveals each one (handleComparisonSync) exactly when the voice
    // reaches the sentence that explains it, via part.comparison.sync.
    if (sharedGroups && sharedGroups.length) {
      const itemsEl = document.getElementById(`comparison-col-${columnIndex}-items`);
      itemsEl.innerHTML = "";
      sharedGroups.forEach((group) => {
        const exampleIds = group.columns && group.columns[column.id];
        if (!exampleIds || !exampleIds.length) return;
        const groupBlock = document.createElement("div");
        groupBlock.className = "comparison-group-block pending";
        groupBlock.id = `comparison-col-${columnIndex}-group-${group.id}`;
        const groupLabel = document.createElement("p");
        groupLabel.className = "comparison-group-label";
        groupLabel.textContent = (group.label && (group.label[currentLanguage] || group.label.ur)) || group.id;
        groupBlock.appendChild(groupLabel);
        exampleIds.forEach((id) => {
          const example = exampleById[id];
          if (example) groupBlock.appendChild(buildExampleCard(example));
        });
        itemsEl.appendChild(groupBlock);
      });
      return;
    }

    // Plain flat fallback: no grouping of any kind for this column.
    if (column.groups && column.groups.length) {
      tabsEl.hidden = false;
      column.groups.forEach((group, groupIndex) => {
        const tab = document.createElement("button");
        tab.className = "comparison-tab" + (groupIndex === 0 ? " active" : "");
        tab.textContent = (group.label && (group.label[currentLanguage] || group.label.ur)) || group.id;
        tab.addEventListener("click", () => {
          tabsEl.querySelectorAll(".comparison-tab").forEach((b) => b.classList.remove("active"));
          tab.classList.add("active");
          showColumnExamples(columnIndex, group.example_ids);
        });
        tabsEl.appendChild(tab);
      });
      showColumnExamples(columnIndex, column.groups[0].example_ids);
    } else {
      showColumnExamples(columnIndex, column.example_ids);
    }
  });
}

// The question text is no longer shown separately -- the narration audio
// itself poses the question, and this chat is where the learner responds
// (or asks anything else).
async function loadPartChat(lessonId, partId) {
  const list = document.getElementById("part-chat-list");
  list.innerHTML = "";
  const data = await api(
    `/api/questions?lesson_id=${encodeURIComponent(lessonId)}&part_id=${encodeURIComponent(partId)}`
  );
  data.questions.forEach((q) => list.appendChild(buildChatEntry(q, { showMeta: false })));
  list.scrollTop = list.scrollHeight;
}

async function loadFeedbackState(lessonId, partId) {
  const data = await api(
    `/api/feedback?lesson_id=${encodeURIComponent(lessonId)}&part_id=${encodeURIComponent(partId)}`
  );
  document.getElementById("thumbs-up-btn").classList.toggle("active", data.rating === "up");
  document.getElementById("thumbs-down-btn").classList.toggle("active", data.rating === "down");
}

document.querySelectorAll(".feedback-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const part = currentLesson.parts[currentPartIndex];
    const rating = btn.dataset.rating;
    await api("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lesson_id: currentLesson.id, part_id: part.id, rating }),
    });
    document.getElementById("thumbs-up-btn").classList.toggle("active", rating === "up");
    document.getElementById("thumbs-down-btn").classList.toggle("active", rating === "down");
  });
});

function formatTime(seconds) {
  if (!isFinite(seconds) || seconds < 0) seconds = 0;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

// A real play/pause toggle + seek slider (like a video player), instead of
// a one-shot "play" button with no way to pause or jump back once started.
document.getElementById("play-btn").addEventListener("click", () => {
  const audio = document.getElementById("part-audio");
  if (audio.paused) {
    audio.play();
    logClientEvent("audio_played", currentLesson.id, currentLesson.parts[currentPartIndex].id);
  } else {
    audio.pause();
    logClientEvent("audio_paused", currentLesson.id, currentLesson.parts[currentPartIndex].id, {
      at_seconds: Math.round(audio.currentTime),
    });
  }
});

document.getElementById("part-audio").addEventListener("play", () => {
  document.getElementById("play-btn").textContent = "❚❚";
});

document.getElementById("part-audio").addEventListener("pause", () => {
  document.getElementById("play-btn").textContent = "▶";
});

document.getElementById("part-audio").addEventListener("loadedmetadata", (e) => {
  document.getElementById("player-seek").disabled = false;
  document.getElementById("player-time").textContent = `0:00 / ${formatTime(e.target.duration)}`;
});

let seekDragging = false;

document.getElementById("part-audio").addEventListener("timeupdate", (e) => {
  if (seekDragging) return;
  const { currentTime, duration } = e.target;
  if (isFinite(duration) && duration > 0) {
    document.getElementById("player-seek").value = Math.round((currentTime / duration) * 1000);
  }
  document.getElementById("player-time").textContent = `${formatTime(currentTime)} / ${formatTime(duration)}`;
});

document.getElementById("player-seek").addEventListener("input", () => {
  seekDragging = true;
});

document.getElementById("player-seek").addEventListener("change", (e) => {
  const audio = document.getElementById("part-audio");
  if (isFinite(audio.duration) && audio.duration > 0) {
    audio.currentTime = (e.target.value / 1000) * audio.duration;
    logClientEvent("audio_seeked", currentLesson.id, currentLesson.parts[currentPartIndex].id, {
      to_seconds: Math.round(audio.currentTime),
    });
  }
  seekDragging = false;
});

// Pop in / pop out each sentence exactly in sync with its real narration
// timing (Edge TTS SentenceBoundary offsets baked in by
// generate_concept_slides.py), not a guessed interval.
function showSentenceText(narration, idx) {
  const sentenceEl = document.getElementById("sentence-text");
  sentenceEl.classList.remove("visible");
  setTimeout(() => {
    sentenceEl.textContent = narration.sentences[idx].text;
    requestAnimationFrame(() => sentenceEl.classList.add("visible"));
  }, 150);
}

document.getElementById("part-audio").addEventListener("timeupdate", (e) => {
  const part = currentLesson.parts[currentPartIndex];
  const narration = part.narration[currentLanguage] || part.narration.ur;
  const t = e.target.currentTime;
  const idx = narration.sentences.findIndex((s) => t >= s.start && t < s.end);
  if (idx === -1 || idx === currentSentenceIndex) return;
  currentSentenceIndex = idx;

  if (part.layout === "comparison" && part.comparison) {
    handleComparisonSync(part, idx, narration);
    return;
  }

  if (part.sync && part.sync.length) {
    handleExampleSync(part, idx);
  }

  showSentenceText(narration, idx);
});

// Seeking (dragging the slider, or any other jump) doesn't fire a smooth
// run through every intervening timeupdate tick, so it needs its own
// handler to fully resync the screen to wherever the cursor landed --
// otherwise scrubbing backward leaves examples revealed that the
// narration hasn't actually reached yet, and the displayed state drifts
// out of sync with the actual audio position.
document.getElementById("part-audio").addEventListener("seeked", (e) => {
  const part = currentLesson.parts[currentPartIndex];
  const narration = part.narration[currentLanguage] || part.narration.ur;
  const t = e.target.currentTime;
  const idx = narration.sentences.findIndex((s) => t >= s.start && t < s.end);
  currentSentenceIndex = idx;

  if (part.layout === "comparison" && part.comparison) {
    syncComparisonToTime(part, narration, t);
    return;
  }

  if (part.sync && part.sync.length) {
    syncExamplesToTime(part, narration, t);
  }

  if (idx !== -1) showSentenceText(narration, idx);
});

document.getElementById("example-play-btn").addEventListener("click", () => {
  document.getElementById("example-audio").play();
});

document.getElementById("examples-toggle-btn").addEventListener("click", () => {
  document.getElementById("examples-section").classList.toggle("collapsed");
});

// Hearing the Arabic example correctly shouldn't depend on noticing the
// small speaker button -- once the narration finishes, automatically play
// the Arabic-voiced example once as part of the normal lecture flow.
document.getElementById("part-audio").addEventListener("ended", () => {
  if (!document.getElementById("example-play-btn").hidden) {
    const exampleAudio = document.getElementById("example-audio");
    exampleAudio.currentTime = 0;
    exampleAudio.play();
  }
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
  const textInput = document.getElementById("question-answer");
  const text = textInput.value.trim();
  const statusEl = document.getElementById("answer-status");
  const part = currentLesson.parts[currentPartIndex];

  if (!text && !recordedChunks.length) return;

  const params = new URLSearchParams({
    lesson_id: currentLesson.id,
    part_id: part.id,
    language: currentLanguage,
  });
  if (text) params.set("text", text);

  const formData = new FormData();
  let audioBlob = null;
  if (!text && recordedChunks.length) {
    audioBlob = new Blob(recordedChunks, { type: "audio/webm" });
    formData.append("audio", audioBlob, "answer.webm");
  }

  statusEl.textContent = t("sending");
  const res = await fetch(`/api/questions?${params.toString()}`, {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  if (!res.ok) {
    statusEl.textContent = t("sendError");
    return;
  }
  const { id } = await res.json();
  statusEl.textContent = "";
  textInput.value = "";
  recordedChunks = [];

  const list = document.getElementById("part-chat-list");
  const audioUrl = audioBlob ? URL.createObjectURL(audioBlob) : null;
  const entry = buildChatEntry(
    { question_text: text || null, question_audio_url: audioUrl, status: "pending" },
    { showMeta: false }
  );
  list.appendChild(entry);
  list.scrollTop = list.scrollHeight;
  pollAnswer(id, entry.querySelector(".chat-bubble-answer"));
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
    document.getElementById("slide-card").innerHTML = `<p>${t("lessonComplete")}</p>`;
    document.getElementById("question-box").hidden = true;
    document.getElementById("question-box").classList.remove("open");
    document.getElementById("chat-fab").hidden = true;
  }
}

document.getElementById("chat-fab").addEventListener("click", () => {
  const panel = document.getElementById("question-box");
  panel.classList.toggle("open");
  logClientEvent("chat_panel_toggled", currentLesson.id, currentLesson.parts[currentPartIndex].id, {
    state: panel.classList.contains("open") ? "open" : "closed",
  });
});

document.getElementById("chat-close-btn").addEventListener("click", () => {
  document.getElementById("question-box").classList.remove("open");
  logClientEvent("chat_panel_toggled", currentLesson.id, currentLesson.parts[currentPartIndex].id, {
    state: "closed",
  });
});

// Each sent chat message polls independently by its own question id, so
// sending a second message before the first is answered doesn't abandon
// the first bubble's update.
function pollAnswer(id, bubbleEl) {
  const interval = setInterval(async () => {
    const data = await api(`/api/questions/${id}`);
    if (data.status === "answered") {
      clearInterval(interval);
      bubbleEl.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = data.answer_text || "";
      bubbleEl.appendChild(p);
      if (data.answer_audio_url) {
        const audio = document.createElement("audio");
        audio.controls = true;
        audio.src = data.answer_audio_url;
        bubbleEl.appendChild(audio);
      }
      bubbleEl.appendChild(buildAnswerRatingRow(id, data.rating));
    } else if (data.status === "failed") {
      clearInterval(interval);
      bubbleEl.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = t("reviewError");
      bubbleEl.appendChild(p);
    }
  }, 3000);
}

checkLogin();
