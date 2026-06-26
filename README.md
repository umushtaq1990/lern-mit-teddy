# LinguaAI — Voice Language Learning Agent

Real-time AI language coach built on LiveKit and LangGraph. Speak naturally in your target language — LinguaAI listens, corrects gently, and keeps the conversation flowing.

**Supported languages:** English · Spanish · French · German · Arabic · Chinese · Japanese · Korean · Portuguese · Italian · Dutch · Russian · Turkish · Hindi

**AI models:** OpenAI (GPT) · Gemini Live · Custom / OpenAI Realtime

---

## How it works

1. Open the browser UI and pick the language you want to learn and your native language.
2. Select an AI model and click **🎙️ Let's Chat!**
3. LinguaAI greets you in your target language, assesses your level, and starts a natural conversation.
4. Mistakes are corrected kindly — the coach models the right form without interrupting the flow.
5. If you get stuck, speak or type in your native language and the coach will explain, then guide you back.

---

## Architecture

```
Browser (http://localhost:8080)
        │  language + native_language + model selection
        │  WebRTC audio / video
        ▼
LiveKit Server  (Docker · port 7880)
        │
        │  dispatches room with language metadata
        ▼
LiveKit Voice Worker  (src/livekit/agent.py)
        │
        ├── STT  faster-whisper (on-device, multilingual)
        │        mic audio → text in target language
        │
        ├── LLM  LangGraph Adapter  (src/livekit/adapter/langgraph.py)
        │        │  passes language + native_language in config
        │        ▼
        │    LangGraph Server (port 2024) → src/langgraph/agent.py
        │        LinguaAI coach · dynamic prompt per language pair
        │        Safety filters · no tools (pure conversation)
        │
        └── TTS  Hume / Kokoro (local) / Cartesia / OpenAI
                 coach speech → plays in browser
```

**Key files:**

| File | Responsibility |
|------|---------------|
| `src/langgraph/agent.py` | LinguaAI coach — dynamic prompt, language pair, safety rules |
| `src/livekit/agent.py` | Voice worker — wires STT + LangGraph + TTS, multilingual greetings |
| `src/livekit/config.py` | Config — `language`, `native_language`, voice mode, STT/TTS settings |
| `src/livekit/adapter/langgraph.py` | Bridges LiveKit ↔ LangGraph streaming |
| `src/livekit/stt/faster_whisper_stt.py` | On-device multilingual speech-to-text |
| `src/livekit/providers.py` | TTS + realtime LLM factories |
| `src/livekit/tracing.py` | Optional Langfuse observability |
| `src/frontend/` | FastAPI server + LinguaAI browser UI |

All four processes must run simultaneously: LiveKit (Docker), LangGraph server, voice worker, and frontend.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python + `uv` | 3.12+ |
| Docker Desktop | any recent |
| OpenAI API key | required for pipeline / realtime modes |

---

## Quick Start

### 1. Install dependencies

```bash
git clone https://github.com/ahmad2b/langgraph-voice-call-agent.git
cd langgraph-voice-call-agent
uv sync
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
# LiveKit
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# LLM
OPENAI_API_KEY=your-openai-key
LLM_MODEL=gpt-4.1-nano

# Default language to learn (overridable from UI per session)
LANGUAGE=es   # en | es | fr | de | ar | zh | ja | ko | pt | it | nl | ru | tr | hi

# Voice mode default (overridable from UI per session)
VOICE_MODE=pipeline   # pipeline | openai_realtime | gemini_live | ultravox

# STT — on-device faster-whisper
STT_MODEL=base   # tiny | base | small | medium | large-v3

# TTS — pick one provider
TTS_PROVIDER=openai
TTS_BASE_URL=http://localhost:8880/v1   # Kokoro local (no API key needed)
TTS_VOICE=af_sky

# LangGraph
LANGGRAPH_URL=http://localhost:2024
```

### 3. Download VAD and turn-detector models

```bash
uv run -m src.livekit.agent download-files
```

### 4. Start Docker services

```bash
# LiveKit media server
docker compose up -d

# Kokoro TTS (local, no API key) — skip if using Hume or Cartesia
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

If the containers already exist from a previous run:

```bash
docker start livekit-server
docker start <kokoro-container-name>
```

### 5. Start LangGraph server

```bash
uv run langgraph dev
```

Wait until you see `Ready` before starting the voice worker.

### 6. Start voice worker

```bash
uv run -m src.livekit.agent dev
```

### 7. Start frontend

```bash
uv run python -m src.frontend
# Open http://127.0.0.1:8080
```

### 8. Start a lesson

1. Select **I want to learn** — e.g. Spanish
2. Select **My native language** — e.g. English
3. Select **AI Model** — OpenAI (GPT), Gemini, or Custom
4. Click **🎙️ Let's Chat!**
5. Speak — LinguaAI will greet you in Spanish and start the lesson.

---

## Language Selection

Language is selected in the UI per session and passed as room metadata to the voice worker. It controls:

| Component | Effect |
|-----------|--------|
| STT (faster-whisper) | Transcribes speech in the target language |
| LLM system prompt | Coach responds in the target language; explains in native language when needed |
| TTS | Synthesises speech in the target language |
| Greeting | Opening message is in the target language |
| Turn detector | English turn-detector used for English; VAD-based endpointing for other languages |

**Supported language codes:**

| Code | Language | Code | Language |
|------|----------|------|----------|
| `en` | English  | `ko` | Korean   |
| `es` | Spanish  | `pt` | Portuguese |
| `fr` | French   | `it` | Italian  |
| `de` | German   | `nl` | Dutch    |
| `ar` | Arabic   | `ru` | Russian  |
| `zh` | Chinese  | `tr` | Turkish  |
| `ja` | Japanese | `hi` | Hindi    |

You can also set a server-wide default in `.env`:

```env
LANGUAGE=fr   # all sessions default to French
```

---

## AI Models (Voice Modes)

| UI Label | `VOICE_MODE` | How it works | Requires |
|----------|-------------|--------------|---------|
| OpenAI (GPT) | `pipeline` | STT → LangGraph (GPT) → TTS | `OPENAI_API_KEY` |
| Gemini (Google) | `gemini_live` | Google Gemini Realtime end-to-end | `GOOGLE_API_KEY` |
| Custom Model | `openai_realtime` | OpenAI Realtime API streaming | `OPENAI_API_KEY` |
| Ultravox | `ultravox` | Ultravox Realtime end-to-end | `ULTRAVOX_API_KEY` |

Pipeline mode (OpenAI GPT) is recommended — it gives full LangGraph control and the richest language coaching experience.

---

## TTS Options

**Kokoro** (local, no API key — recommended for privacy):

```bash
docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

```env
TTS_PROVIDER=openai
TTS_BASE_URL=http://localhost:8880/v1
TTS_VOICE=af_sky
```

**Hume**:

```env
TTS_PROVIDER=hume
HUME_API_KEY=your-key
```

**Cartesia**:

```env
TTS_PROVIDER=cartesia
CARTESIA_API_KEY=your-key
```

---

## Content Safety

LinguaAI enforces strict content rules at the prompt level:

- Refuses sexual, violent, abusive, or hateful content
- Refuses harmful role-play scenarios and suggests appropriate alternatives
- Stays focused on language learning — redirects off-topic conversations
- Keeps every session positive, respectful, and educational

---

## Full Environment Variable Reference

```env
# LiveKit
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# LLM
OPENAI_API_KEY=
LLM_MODEL=gpt-4.1-nano

# Language defaults (overridable per session from UI)
LANGUAGE=en        # BCP-47 code of the language to learn
VOICE_MODE=pipeline

# STT — on-device faster-whisper
STT_MODEL=base     # tiny | base | small | medium | large-v3

# TTS
TTS_PROVIDER=openai          # openai | hume | cartesia
TTS_VOICE=af_sky
TTS_BASE_URL=http://localhost:8880/v1   # Kokoro local endpoint
TTS_API_KEY=not-needed                  # placeholder for local servers

HUME_API_KEY=
CARTESIA_API_KEY=

# Realtime modes
OPENAI_REALTIME_MODEL=gpt-4o-realtime-preview
OPENAI_REALTIME_VOICE=alloy
GOOGLE_API_KEY=
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_LIVE_VOICE=Puck
ULTRAVOX_API_KEY=
ULTRAVOX_MODEL=fixie-ai/ultravox
ULTRAVOX_VOICE=Mark

# LangGraph
LANGGRAPH_URL=http://localhost:2024

# Langfuse tracing (optional)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3000
```

---

## Troubleshooting

**`OPENAI_API_KEY` not set** — check `.env`; the key line must not start with `#`.

**LangGraph `connection refused`** — start `uv run langgraph dev` before the voice worker.

**VAD / turn-detector models not found:**

```bash
uv run -m src.livekit.agent download-files
```

**Kokoro TTS silent** — ensure `TTS_PROVIDER=openai` and `TTS_BASE_URL` points to the running Kokoro container.

**Frontend serving old JS** — hard-refresh the browser (`Ctrl+Shift+R`) to clear the cached `app.js`.

**Import errors** — always run as a module:

```bash
uv run -m src.livekit.agent dev   # correct
python src/livekit/agent.py       # wrong
```

**Docker container name conflict:**

```bash
docker start livekit-server   # reuse existing container — no need for docker compose up
```

---

## LiveKit Cloud

Replace local LiveKit with a cloud project:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
```

---

## References

- [LiveKit Agents](https://github.com/livekit/agents)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Kokoro-FastAPI](https://github.com/remsky/kokoro-fastapi)
