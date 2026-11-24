"""A dedicated single-turn LLM call for this app's Q&A flow, backed by a
local Ollama model (qwen2.5:3b by default) -- same local-LLM pattern as the
JME reference architecture, so this runs free and offline, no OpenAI spend.

Deliberately NOT src.langgraph.agent.get_agent(): that graph's
conversation_helper mode is hardcoded to Arabic-as-native-language and
carries global vocab-drill caches (_judge_cache, _word_attempts) meant for
a live multi-turn voice call, neither of which fits a plain async
question-in/answer-out flow.
"""

from __future__ import annotations

from . import ollama_client
from .languages import DEFAULT_LANGUAGE, LANGUAGES

_SYSTEM_PROMPT = """\
You are a friendly Arabic tutor. The student's native language is {language_name}. \
You are helping them with a short, specific Arabic lesson part (given below as context).

Answer the student's question about that lesson part. Write your ENTIRE answer \
in {language_name}. The ONLY exception is a single Arabic word or short phrase \
that is itself the vocabulary/grammar example being taught -- quote that one \
word/phrase in Arabic script and then immediately explain it in {language_name}. \
Every sentence of explanation, every grammar term, and every connecting word must \
be in {language_name} -- do not slip into Arabic or any other language for the \
explanation itself. Keep the answer short (2-4 sentences) and encouraging, \
suitable to be read aloud as an audio reply.

Lesson context:
{lesson_context}
"""


def answer_question(question_text: str, lesson_context: str, language: str = DEFAULT_LANGUAGE) -> str:
    language_name = LANGUAGES.get(language, LANGUAGES[DEFAULT_LANGUAGE])["prompt_name"]
    system = _SYSTEM_PROMPT.format(language_name=language_name, lesson_context=lesson_context)
    return ollama_client.generate(question_text, system=system)
