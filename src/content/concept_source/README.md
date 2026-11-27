# Concept source files

One `lecture-NN.json` per lecture, hand-authored (grounded in
`data/Arabic_Course/summaries/`) rather than LLM-generated — see the
docstring in `generate_concept_slides.py` for why.

Schema (bilingual: every learner-facing field is a `{code: text}` dict,
keyed by language code -- see `src/urdu_arabic/languages.py` for the
supported codes. Adding a new language means adding its key to every field
below plus an entry in `languages.py`, nothing else):

```json
{
  "title": {"ur": "Human-readable lecture title in Urdu", "en": "...in English"},
  "concepts": [
    {
      "title": {"ur": "Short Urdu title (3-6 words)", "en": "Equivalent English title"},
      "arabic_example": "One Arabic word/phrase this concept teaches, or null -- NOT translated, same for every language",
      "sentences": [
        {"ur": "2-4 short Urdu sentences, each a complete teaching point", "en": "faithful English translation of the same sentence"}
      ],
      "question": {"ur": "One short Urdu comprehension question", "en": "Equivalent English question"},
      "categories": [
        {"id": "short-slug", "label": {"ur": "...", "en": "Button label, e.g. Animals"}}
      ],
      "examples": [
        {
          "id": "unique-id",
          "category": "short-slug (must match a categories[].id above)",
          "arabic": "Fully vocalized Arabic (e.g. a question + its answer)",
          "transliteration": "...",
          "translation": {"ur": "...", "en": "..."}
        }
      ]
    }
  ]
}
```

`categories` + `examples[].category` together turn a concept's examples list
into a vocabulary slide with picker buttons (e.g. Animals / Home / Living
Room / People) instead of a plain list -- the learner switches sections
themselves. Only set `categories` when that's the intent; a concept with
`examples` but no `categories` keeps the plain flat-list rendering.

Every sentence should already read naturally as a complete sentence in each
language; `generate_concept_slides.py` appends a trailing sentence-final
mark (per-language, from `languages.py`'s `full_stop`) only if missing
(needed so Edge TTS's SentenceBoundary events give each sentence its own
timing for the frontend's pop-in/pop-out sync).
