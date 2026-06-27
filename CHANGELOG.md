# Changelog

All notable changes to **Lern mit Teddy** are documented here.

Format: [Semantic Versioning](https://semver.org) — `MAJOR.MINOR.PATCH`

---

## [1.1.0] — 2026-06-26

### Added — Full Language Learning Curriculum

- **30-section structured syllabus** grouped into 7 levels, selectable from a dropdown during a live call
- **Level 1 — Basics:** Begrüßung (greetings), Zahlen 1–10, Zahlen 11–20, Das ABC (A–Z with example words), Farben
- **Level 2 — Body & Family:** Mein Körper (10 body parts), Familie
- **Level 3 — Home:** Das Haus (rooms overview), Schlafzimmer, Badezimmer, Wohnzimmer, Küche
- **Level 4 — Nature:** Garten, Wetter, Jahreszeiten, Tiere
- **Level 5 — Food & Drinks:** Frühstück, Obst, Gemüse, Getränke, Lieblingsessen, Eis
- **Level 6 — World & School:** Schule, Transport & Verkehr, Sport, Hobbys
- **Level 7 — Society:** Kleidung, Berufe, Spielzeug, Superkräfte
- **Section dropdown** (`#section-bar`) appears during active sessions — picking a section shows the vocabulary panel AND sends a natural German prompt to Teddy so he switches focus immediately
- **3 new card display types:** `phrase` (wide cards for greeting phrases), `number` (large digit), `abc` (large letter A–Z)
- **14 new VOCAB_SETS:** greetings, numbers1, numbers2, alphabet, body, rooms, bedroom, bathroom, living_room, kitchen, garden, weather, transport, clothes
- **14 new KEYWORD_MAP entries** so sections also appear automatically when Teddy mentions those words
- **Expanded de.py drilling** — 14 new VOKABEL-RUNDEN blocks (Begrüßung, Zahlen 1–10, Zahlen 11–20, ABC, Körper, Räume, Schlafzimmer, Badezimmer, Wohnzimmer, Küche, Garten, Wetter, Transport, Kleidung)
- **Architecture note:** syllabus structure is language-neutral — adding a new language requires only a new `prompts/xx.py` with equivalent drilling sections

---

## [1.0.0] — 2026-06-26

Initial release of **Lern mit Teddy**, forked from
[langgraph-voice-call-agent](https://github.com/ahmad2b/langgraph-voice-call-agent) by @ahmad2b.

### Added
- **Teddy persona** — 8-year-old bear character with SVG animation, lip-sync, and blinking
- **German-first prompt system** — `src/langgraph/prompts/de.py` written entirely in German
  so the LLM starts in the correct language context from the first token
- **Per-language prompt files** — `de`, `en`, `ar`, `hi` each in their own module;
  other languages fall back to English
- **16 interactive vocabulary sets** — Frühstück, Obst, Tiere, Familie, Schule, and more;
  cards appear automatically as Teddy mentions a topic
- **Item-by-item vocabulary drilling** — Teddy asks follow-up questions about each card
  (e.g. "Trinkst du Milch?" → "Wie viele Gläser am Tag?")
- **Article gender colour coding** — der (blue), die (pink), das (green) on every card
- **Tap-to-answer** — clicking a vocab card sends the German word to the agent
- **Silence watchdog** — Teddy re-prompts after 5 seconds of silence
- **Feedback modal** — thumbs up/down scoring sent to Langfuse
- **No-cache headers** on static files — prevents stale JS from being served
- **`selected` attribute** on German option — ensures German is the UI default

### Changed
- Renamed app from **LinguaAI** → **Lern mit Teddy** throughout UI and code
- System prompt language rule moved to **top of prompt** in all language files
- `LangGraphAdapter` strips LiveKit `Agent.instructions` from chat context —
  LangGraph owns all system prompts; no English override can leak in
- Default language changed from `en` → `de` in all fallbacks
- Agent greeting and reprompt strings updated to use "Teddy" name

### Removed
- NVIDIA LLM and TTS backend (separate infrastructure, not needed)
- Cartesia TTS provider (not configured)
- `EnglishModel` turn detector (app is multilingual; VAD handles endpointing)
- `create_lingua_agent()` dead function
- `NVIDIA_BASE_URL` constant
- LangGraph dev server requirement — agent now runs in-process

---

## [0.1.0] — upstream

Original [langgraph-voice-call-agent](https://github.com/ahmad2b/langgraph-voice-call-agent)
by [@ahmad2b](https://github.com/ahmad2b).

General-purpose voice agent demo with LiveKit + LangGraph + OpenAI, supporting 14 languages
and multiple voice modes (pipeline, OpenAI Realtime, Gemini Live, Ultravox).
