# Lern mit Teddy 🐻

> **Version 1.0.0** — A real-time AI voice companion that teaches German to children through natural conversation.

Teddy is a friendly 8-year-old bear who lives in the browser. Kids speak with him, he asks about their day, their favourite foods, their pets — all in German. Vocabulary cards appear automatically as topics come up, and Teddy works through the items one by one with simple questions.

**Built on:** LiveKit · LangGraph · OpenAI · faster-whisper

---

## Credits & Origin

This project is based on **[langgraph-voice-call-agent](https://github.com/ahmad2b/langgraph-voice-call-agent)** by [@ahmad2b](https://github.com/ahmad2b) — a brilliant starting point for building voice agents with LangGraph and LiveKit.

**What was added / changed in Lern mit Teddy:**

| Feature | Original | Lern mit Teddy |
|---------|----------|----------------|
| Purpose | General voice chatbot demo | German learning for children |
| Agent persona | Generic assistant | Teddy — an 8-year-old bear |
| Prompts | Single English prompt | Per-language prompt files (`de`, `en`, `ar`, `hi`) |
| Vocabulary cards | — | 16 interactive topic sets with article gender colours |
| Item-by-item drilling | — | Teddy asks about each card item with follow-ups |
| Animated character | — | SVG bear with lip-sync and blinking |
| Feedback modal | — | Thumbs up/down → Langfuse score |
| Language system message | Agent instructions | Stripped from adapter; LangGraph owns all system prompts |
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
        │  WebRTC audio
        ▼
LiveKit Server  (Docker · port 7880)
        │
        ▼
LiveKit Voice Worker  (src/livekit/agent.py)
        │
        ├── STT  faster-whisper  (on-device, multilingual)
        │
        ├── LLM  LangGraph Adapter  →  src/langgraph/agent.py
        │         per-language prompt from src/langgraph/prompts/
        │         topic tracking · question deduplication
        │
        └── TTS  OpenAI TTS / Kokoro (local) / Hume / EdgeTTS
```

**Key files:**

| File | Responsibility |
|------|---------------|
| `src/langgraph/agent.py` | LangGraph agent — dynamic prompt, topic tracking |
| `src/langgraph/prompts/de.py` | German system prompt written in German |
| `src/livekit/agent.py` | Voice worker — STT → LangGraph → TTS pipeline |
| `src/livekit/adapter/langgraph.py` | LiveKit ↔ LangGraph streaming bridge |
| `src/livekit/config.py` | Per-call config from room metadata |
| `src/livekit/providers.py` | TTS + realtime LLM factories |
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

## Vocabulary Sets

16 topic sets built into the UI — cards appear automatically when Teddy mentions a related word:

| Set | German Title | Items |
|-----|-------------|-------|
| Breakfast | Frühstück | Milch, Eier, Brot, Butter … |
| Fruits | Obst | Apfel, Banane, Orange … |
| Vegetables | Gemüse | Karotte, Tomate, Gurke … |
| Animals | Tiere | Hund, Katze, Vogel … |
| Family | Familie | Mama, Papa, Bruder … |
| School | Schule | Buch, Stift, Tasche … |
| Sports | Sport & Spiele | Fußball, Schwimmen … |
| Hobbies | Hobbys | Lesen, Malen, Singen … |
| Drinks | Getränke | Wasser, Milch, Saft … |
| Ice Cream | Eis | Schokolade, Vanille … |
| Seasons | Jahreszeiten | Frühling, Sommer … |
| Colours | Farben | Rot, Blau, Grün … |
| Jobs | Berufe | Arzt, Lehrer, Bäcker … |
| Superpowers | Superkräfte | Fliegen, Unsichtbarkeit … |
| Favourite Food | Lieblingsessen | Pizza, Nudeln, Suppe … |
| Toys | Spielzeug | Ball, Puppe, Auto … |

Article gender is colour-coded on every card: **blue** = der, **pink** = die, **green** = das.

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

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Teddy speaks English instead of German | Check `LANGUAGE=de` in `.env`; restart voice worker |
| Frontend shows old English UI | Open an Incognito window or clear site data in DevTools |
| `connection refused` on LiveKit | Run `docker compose up -d` first |
| No audio from Teddy | Check browser microphone permissions |
| VAD model not found | Run `uv run python -m src.livekit.agent download-files` |

---

## References

- [langgraph-voice-call-agent](https://github.com/ahmad2b/langgraph-voice-call-agent) — original project by @ahmad2b
- [LiveKit Agents](https://github.com/livekit/agents)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Kokoro-FastAPI](https://github.com/remsky/kokoro-fastapi)
