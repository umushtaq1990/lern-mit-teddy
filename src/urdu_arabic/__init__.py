"""Isolated Urdu -> Arabic learning web app.

Deliberately independent of src.livekit and src.frontend: no real-time
LiveKit room, no Entra/CIAM login, and no reuse of src.langgraph.agent's
conversation graph (that graph's conversation_helper mode is hardcoded to
Arabic-as-native-language and carries global vocab-drill caches that don't
fit a plain async Q&A flow).

Flow: a user logs in via a short-lived OTP, views a lesson part, and asks a
question (typed or recorded audio). The question is queued and answered
asynchronously by a separate worker process (src.urdu_arabic.worker) — see
server.py and worker.py.
"""
