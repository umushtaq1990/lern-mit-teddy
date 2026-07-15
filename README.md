# Lern mit Teddy 🐻

> **Version 1.2.0** — A real-time AI voice companion that teaches German or Arabic to children through natural conversation.

Teddy is a friendly 8-year-old bear who lives in the browser. Kids speak with him, he asks about their day, their favourite foods, their pets. Vocabulary cards appear automatically as topics come up, and Teddy works through the items one by one with simple questions — correcting single-word answers into full sentences and sticking to one card at a time until it's finished.

**Built on:** LiveKit · LangGraph · OpenAI · faster-whisper · Edge TTS

---

## Credits & Origin

This project is based on **[langgraph-voice-call-agent](https://github.com/ahmad2b/langgraph-voice-call-agent)** by [@ahmad2b](https://github.com/ahmad2b) — a brilliant starting point for building voice agents with LangGraph and LiveKit.

**What was added / changed in Lern mit Teddy:**

| Feature | Original | Lern mit Teddy |
|---------|----------|----------------|
| Purpose | General voice chatbot demo | German learning for children |
| Agent persona | Generic assistant | Teddy — an 8-year-old bear |
| Prompts | Single English prompt | Per-language prompt files (`de`, `en`, `ar`, `hi`) |
| Vocabulary cards | — | 30 interactive topic sets with article gender colours |
| Item-by-item drilling | — | Deterministic, judge-verified: one word at a time, tick/cross tracked, corrects fragment answers into full sentences |
| Arabic learning mode | — | Native Saudi Arabic voice (Edge TTS), slowed prosody, silent English captions, RTL transcript |
| Animated character | — | SVG bear with lip-sync and blinking |
| Feedback modal | — | Thumbs up/down → Langfuse score |
| Language system message | Agent instructions | Stripped from adapter; LangGraph owns all system prompts |
| Session logs | — | Every session written locally to `logs/sessions/<id>.jsonl` |
| NVIDIA / Cartesia backends | Included | Removed (not needed) |

---

## How it works

1. Open the browser UI at `http://localhost:8080`
2. Select **language to learn** and **your native language**
3. Click **Let's Chat!** — Teddy greets you in German immediately
4. Vocabulary cards appear as Teddy talks about a topic
5. Teddy asks questions about each card item, one at a time

---

## Architecture

```
Browser (http://localhost:8080)
        │  language + native_language → room metadata
        │  WebRTC audio · data channel (captions, vocab_progress)
        ▼
LiveKit Server  (Docker · port 7880)
        │
        ▼
LiveKit Voice Worker  (src/livekit/agent.py)
        │
        ├── STT  faster-whisper (on-device) or Deepgram cloud
        │        — Deepgram doesn't support Arabic, auto-falls back to
        │          faster-whisper "small" for better accented-speech accuracy
        │
        ├── LLM  LangGraph Adapter  →  src/langgraph/agent.py
        │         per-language prompt from src/langgraph/prompts/
        │         topic tracking · question deduplication
        │         Arabic only: deterministic vocab-card drill (below)
        │         + separate translation call → caption data message
        │         + local session log (logs/sessions/<id>.jsonl)
        │
        └── TTS  OpenAI TTS / Kokoro (local) / Hume / Edge TTS
                 — Arabic is forced to Edge TTS (native ar-SA voice,
                   real prosody-based slow rate) regardless of TTS_PROVIDER
```

**Arabic vocab-card drill** (`src/langgraph/agent.py`): every reply is preceded by two extra, narrowly-scoped LLM calls, kept separate from Teddy's persona reply so neither dilutes the other:
1. **Judge call** — reads the transcript and the current card's word list, decides which words have been *both* asked about *and* answered with an attempted full sentence. Runs with `tags=["nostream"]` so its raw JSON output never leaks into the spoken audio stream.
2. **Translator call** — translates Teddy's finished Arabic reply into the learner's native language for the on-screen caption; the main persona call never has to produce a translation itself.

The next word to ask about is chosen by code (`remaining[0]` in the card's fixed order), never left to the model — the prompt tells Teddy exactly one word to focus on, so it can't wander onto a different item or an unrelated topic. Progress (`done` / `current`) is pushed to the frontend as a `vocab_progress` data message so vocab cards show a ✓ once complete and a highlight ring on the active word.

**Key files:**

| File | Responsibility |
|------|---------------|
| `src/langgraph/agent.py` | LangGraph agent — dynamic prompt, topic tracking, Arabic vocab-drill state machine + judge |
| `src/langgraph/prompts/de.py`, `ar.py`, ... | Per-language system prompt, written in that language |
| `src/langgraph/vocab_ar.json` | Arabic vocab-card data (word lists, section triggers) — generated from `app.js`, kept in sync manually |
| `src/livekit/agent.py` | Voice worker — STT → LangGraph → TTS pipeline, session logging wiring |
| `src/livekit/adapter/langgraph.py` | LiveKit ↔ LangGraph streaming bridge; translation dispatch, caption/progress/turn callbacks |
| `src/livekit/session_logger.py` | Local per-session JSONL conversation log |
| `src/livekit/config.py` | Per-call config from room metadata; STT/TTS provider + model overrides per language |
| `src/livekit/providers.py` | TTS + realtime LLM factories |
| `src/livekit/edge_tts_wrapper.py` | Microsoft Edge TTS adapter (native regional voices, rate control) |
| `src/livekit/vision.py` | Optional live video frame injection |
| `src/frontend/` | FastAPI server + browser UI |

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/umushtaq1990/lern-mit-teddy.git
cd lern-mit-teddy
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Minimum required keys:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
OPENAI_API_KEY=your_openai_api_key
LANGUAGE=de
```

### 3. Start LiveKit (Docker)

```bash
docker compose up -d
```

### 4. Download VAD model (first run only)

```bash
uv run python -m src.livekit.agent download-files
```

### 5. Start voice worker

```bash
uv run python -m src.livekit.agent dev
```

### 6. Start frontend

```bash
uv run voice-frontend
# Open http://127.0.0.1:8080
```

> **Note:** No separate LangGraph server needed — the LangGraph agent runs in-process inside the voice worker.

---

## Production Deployment (Docker)

This repository now includes production Docker assets:

- `Dockerfile.frontend` — serves the FastAPI UI and token API on port `8080`
- `Dockerfile.worker` — runs the LiveKit voice worker process
- `docker-compose.prod.yml` — runs both services together

### 1. Prepare environment

Use LiveKit Cloud credentials in your `.env`:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
OPENAI_API_KEY=your_openai_api_key

# Recommended for production to avoid running local Whisper on your server
STT_PROVIDER=deepgram
DEEPGRAM_API_KEY=your_deepgram_api_key

VOICE_MODE=pipeline
LANGUAGE=de
```

### 2. Build and start

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 3. Verify

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8080/api/health
```

If your server has a firewall, allow inbound TCP on port `8080`.

### 4. Update to new versions

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

### Optional: HTTPS + domain

Place Nginx/Caddy in front of `frontend:8080` for TLS termination, then route `https://your-domain` to this service.

---

## Language Prompts

Each supported language has its own prompt file written **in that language** so the LLM starts in the right language context from the first token:

| File | Language | Status |
|------|----------|--------|
| `src/langgraph/prompts/de.py` | German | ✅ Full |
| `src/langgraph/prompts/en.py` | English | ✅ Full |
| `src/langgraph/prompts/ar.py` | Arabic | ✅ Full |
| `src/langgraph/prompts/hi.py` | Hindi | ✅ Full |

Other language codes fall back to English. Add a new `xx.py` to support more languages.

---

## Full Language Learning Curriculum

30 vocabulary sets organised into 7 levels — selectable from a **dropdown during any session**. Cards also appear automatically when Teddy mentions a related word.

| Level | Section | German Title | Sample Words |
|-------|---------|-------------|--------------|
| ⭐ 1 | Greetings | Hallo! (Begrüßung) | Hallo, Tschüss, Wie geht's… |
| ⭐ 1 | Numbers 1–10 | Zahlen 1–10 | eins, zwei, drei … zehn |
| ⭐ 1 | Numbers 11–20 | Zahlen 11–20 | elf, zwölf … zwanzig |
| ⭐ 1 | Alphabet | Das ABC | A wie Apfel … Z wie Zebra |
| ⭐ 1 | Colours | Farben | Rot, Blau, Grün … |
| 👨‍👩‍👧 2 | Family | Familie | Mama, Papa, Bruder … |
| 👨‍👩‍👧 2 | Body | Mein Körper | Kopf, Augen, Nase … |
| 🏠 3 | House rooms | Das Haus | Wohnzimmer, Küche … |
| 🏠 3 | Bedroom | Schlafzimmer | Bett, Lampe, Fenster … |
| 🏠 3 | Bathroom | Badezimmer | Zahnbürste, Seife … |
| 🏠 3 | Living room | Wohnzimmer | Sofa, Fernseher … |
| 🏠 3 | Kitchen | Küche | Herd, Kühlschrank … |
| 🌿 4 | Garden | Garten | Baum, Blume, Biene … |
| 🌿 4 | Weather | Wetter | Sonne, Regen, Schnee … |
| 🌿 4 | Seasons | Jahreszeiten | Frühling, Sommer … |
| 🌿 4 | Animals | Tiere | Hund, Katze, Löwe … |
| 🍕 5 | Breakfast | Frühstück | Milch, Eier, Brot … |
| 🍕 5 | Fruits | Obst | Apfel, Banane … |
| 🍕 5 | Vegetables | Gemüse | Karotte, Tomate … |
| 🍕 5 | Drinks | Getränke | Wasser, Saft, Kakao … |
| 🍕 5 | Favourite Food | Lieblingsessen | Pizza, Nudeln … |
| 🍕 5 | Ice Cream | Eis | Schokolade, Vanille … |
| 🎒 6 | School | Schule | Buch, Stift, Rucksack … |
| 🎒 6 | Transport | Transport & Verkehr | Auto, Bus, Zug … |
| 🎒 6 | Sports | Sport & Spiele | Fußball, Schwimmen … |
| 🎒 6 | Hobbies | Hobbys | Lesen, Malen, Singen … |
| 👗 7 | Clothes | Kleidung | T-Shirt, Hose, Schuhe … |
| 👗 7 | Jobs | Berufe | Arzt, Lehrer, Bäcker … |
| 👗 7 | Toys | Spielzeug | Ball, Puppe, Auto … |
| 👗 7 | Superpowers | Superkräfte | Fliegen, Magie … |

Article gender is colour-coded on every card: **blue** = der, **pink** = die, **green** = das.

**How the dropdown works:** select a section → vocab cards appear immediately → Teddy receives a natural German prompt and switches his drilling focus to that topic.

For Arabic, the same 30 sets exist with Arabic words (`src/langgraph/vocab_ar.json`, mirrored from `app.js`'s `ar` fields) — gender is colour-coded **blue** = مذكر (masculine) / **pink** = مؤنث (feminine) instead of the German three-way system, and cards render right-to-left.

---

## Arabic Learning Mode

Arabic gets several dedicated behaviors beyond what other languages currently have:

- **Voice**: Edge TTS's native Saudi Arabic voice (`ar-SA-ZariyahNeural`) at a slowed prosody rate (`-15%`), regardless of the globally configured `TTS_PROVIDER` — a real regional accent with natural cadence, not OpenAI's generic multilingual voice sped down.
- **STT fallback**: Deepgram's `nova-2` model doesn't support Arabic (rejects the connection outright); the worker automatically falls back to local faster-whisper, using the `small` model size specifically for Arabic (better accuracy on a beginner's imperfect pronunciation than the default `base`).
- **Silent English captions**: a separate translation LLM call (not the main persona call) translates each reply into the learner's native language and sends it to the browser as a data message — displayed as its own line under the transcript, never spoken aloud. Captions are keyed by a per-turn ID so they can't attach to the wrong line.
- **Structured vocab-card drilling**: sessions default to a greetings/introductions curriculum (hello, how are you, name, age, where from, job/school) even without picking a card from the dropdown. Whichever card is active, Teddy is only ever told to ask about exactly one word at a time — chosen deterministically by code — and a fragment answer (e.g. "bread" instead of a sentence) gets modeled into the correct full sentence and re-asked rather than moving on. A dedicated judge call verifies each word is properly answered before advancing; results drive the ✓ checkmarks and highlight ring on the vocab cards in the browser.
- **Topic lock**: if the child brings up something unrelated to the active card (in Arabic or their native language), Teddy briefly acknowledges it, then redirects back to the current word — it won't wander off-topic or get derailed by an ambiguous word (e.g. "حلو" meaning either "sweet" or colloquially "cool!").
- **RTL layout**: Arabic transcript lines render right-to-left with Arabic speaker labels ("تيدي"/"أنت"); English captions stay left-to-right underneath.

---

## TTS Options

**OpenAI TTS** (default, recommended):
```env
TTS_PROVIDER=openai
TTS_MODEL=tts-1-hd
TTS_VOICE=nova
```

**Kokoro** (local, free, no API key):
```bash
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```
```env
TTS_PROVIDER=openai
TTS_BASE_URL=http://localhost:8880/v1
TTS_VOICE=ef_dora   # German female voice
```

**Hume AI** (expressive voice):
```env
TTS_PROVIDER=hume
HUME_API_KEY=your_key
HUME_SECRET_KEY=your_secret
HUME_CONFIG_ID=your_config_id
```

**Microsoft Edge TTS** (free, no key):
```env
TTS_PROVIDER=edge_tts
```

> **Note:** Arabic always uses Edge TTS's native `ar-SA-ZariyahNeural` voice regardless of `TTS_PROVIDER` — see `TTS_PROVIDER_OVERRIDES` in `src/livekit/config.py` to change this.

---

## Session Logs

Every session writes a local, human-readable log to `logs/sessions/<session_id>.jsonl` — one JSON line per turn (user message, Teddy's reply, English translation where applicable, the opening greeting), independent of the in-memory conversation state (which is lost whenever the worker restarts) and independent of cloud tracing (LangSmith/Langfuse, if configured). Useful for reviewing exactly what happened in a past session without needing dashboard access.

```json
{"ts": "2026-07-15T14:49:06Z", "room": "voice_assistant_room_5978", "language": "ar", "native_language": "en", "role": "user", "text": "hello"}
{"ts": "2026-07-15T14:49:07Z", "room": "voice_assistant_room_5978", "language": "ar", "native_language": "en", "role": "assistant", "text": "نعم! بالعربية نقول: مرحباً! قل: مرحباً!"}
{"ts": "2026-07-15T14:49:08Z", "room": "voice_assistant_room_5978", "language": "ar", "native_language": "en", "role": "translation", "text": "Yes! In Arabic we say: Hello! Say: Hello!"}
```

`logs/` is gitignored — these files stay local and are never committed.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Teddy speaks English instead of German | Check `LANGUAGE=de` in `.env`; restart voice worker |
| Frontend shows old English UI | Open an Incognito window or clear site data in DevTools |
| `connection refused` on LiveKit | Run `docker compose up -d` first |
| No audio from Teddy | Check browser microphone permissions |
| Arabic session has no audio / STT errors in logs | Confirm the worker log shows "falling back to local faster-whisper" — Deepgram's `nova-2` doesn't support Arabic and needs this fallback |
| Console fills with `UnicodeEncodeError` / "Logging error" spam on Windows | Cosmetic only — the legacy Windows console (`conhost.exe`) can't render Arabic text; it's caught and doesn't affect the running session. Use Windows Terminal instead for clean log output |
| VAD model not found | Run `uv run python -m src.livekit.agent download-files` |

---

## References

- [langgraph-voice-call-agent](https://github.com/ahmad2b/langgraph-voice-call-agent) — original project by @ahmad2b
- [LiveKit Agents](https://github.com/livekit/agents)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Kokoro-FastAPI](https://github.com/remsky/kokoro-fastapi)
