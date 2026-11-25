"""Per-concept illustration pipeline: a small, local, open-source image
model (stabilityai/sd-turbo -- a distilled, 1-4-step Stable Diffusion
variant, picked for being fast and light enough to run on an 8GB consumer
GPU) generates one flat-cartoon-style picture per concept slide, aimed at
a kids'-course "see a picture, hear it, remember it" feel.

Deliberately NOT a paid API (OpenAI images, etc.): runs entirely offline
against a model already on disk, no per-image cost. Must be run with the
isolated .venv-imagegen interpreter (NOT `uv run`/the main project venv),
since torch+diffusers+a CUDA build live there only, kept separate so this
one-off content-generation dependency never touches the main app's
dependency resolution:

    .venv-imagegen\\Scripts\\python.exe -m src.content.generate_concept_images [lecture-01 ...]

With no arguments, processes every lecture; with lecture ids as arguments,
processes only those (used for piloting one lecture before the rest).

Resumable per concept: a part that already has an `image_url` is skipped,
so a killed/interrupted run or a pilot-then-expand run never redoes
already-generated images.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import torch
from diffusers import AutoPipelineForText2Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTENT_DATA_DIR = REPO_ROOT / "src" / "urdu_arabic" / "content_data"
IMAGE_DIR = CONTENT_DATA_DIR / "images"

MODEL_ID = "stabilityai/sd-turbo"

STYLE_PREFIX = "simple flat cartoon illustration for a children's language-learning app"
STYLE_SUFFIX = (
    "bold black outlines, bright flat colors, minimal clean background, "
    "cute and friendly, vector art style, no text, no letters, no words, no writing"
)


def _build_prompt(concept_title_en: str) -> str:
    return f"{STYLE_PREFIX} depicting: {concept_title_en}. {STYLE_SUFFIX}"


def _seed_for(lesson_id: str, part_id: str, example_id: str | None = None) -> int:
    # Stable per-concept (or per-example) seed so a rerun (e.g. after a
    # crash) reproduces the same image instead of generating a different
    # one each time.
    key = f"{lesson_id}/{part_id}/{example_id}" if example_id else f"{lesson_id}/{part_id}"
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:4], "big")


_LEADING_COPULA = re.compile(r"^this is (a|an|the)?\s*", re.IGNORECASE)


def _example_prompt(example: dict[str, Any]) -> str:
    text = (
        example.get("translation", {}).get("en")
        or example.get("transliteration")
        or example.get("arabic", "")
    )
    # Translations carry a parenthetical grammar note, e.g. "The book is new.
    # (nahw: 'kitab' is the subject here, so it ends in -u)" -- that note is
    # for the learner reading the card, not for the image: feeding grammar
    # jargon into the prompt produces confused, off-topic scenes.
    text = text.split(" (")[0].strip()
    # "This is a book." leads the image model away from the noun itself
    # (it tends to render a generic "pointing" scene); the vocabulary being
    # taught is the noun, so strip the demonstrative framing when present.
    text = _LEADING_COPULA.sub("", text).rstrip(".").strip()
    return _build_prompt(text)


def _load_pipeline() -> AutoPipelineForText2Image:
    pipe = AutoPipelineForText2Image.from_pretrained(MODEL_ID, dtype=torch.float16, variant="fp16")
    pipe = pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    return pipe


def _lesson_files(selected: list[str]) -> list[Path]:
    if selected:
        return [CONTENT_DATA_DIR / f"{name}.json" for name in selected]
    return sorted(CONTENT_DATA_DIR.glob("lecture-*.json"))


def _process_lesson(pipe: AutoPipelineForText2Image, path: Path) -> int:
    if not path.exists():
        print(f"skip {path.name}: not found")
        return 0

    lesson = json.loads(path.read_text(encoding="utf-8"))
    lesson_id = lesson["id"]
    generated = 0

    for part in lesson["parts"]:
        if not part.get("image_url"):
            title_en = part["title"].get("en") or part["title"].get("ur", "")
            prompt = _build_prompt(title_en)
            generator = torch.Generator(device="cuda").manual_seed(_seed_for(lesson_id, part["id"]))

            image = pipe(
                prompt=prompt,
                num_inference_steps=2,
                guidance_scale=0.0,
                generator=generator,
            ).images[0]

            image_dir = IMAGE_DIR / lesson_id
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / f"{part['id']}.png"
            image.save(image_path)

            part["image_url"] = f"/content/images/{lesson_id}/{part['id']}.png"
            generated += 1
            print(f"{lesson_id}/{part['id']}: generated image")

            path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")

        for example in part.get("examples", []):
            if example.get("image_url"):
                continue

            prompt = _example_prompt(example)
            generator = torch.Generator(device="cuda").manual_seed(
                _seed_for(lesson_id, part["id"], example["id"])
            )

            image = pipe(
                prompt=prompt,
                num_inference_steps=2,
                guidance_scale=0.0,
                generator=generator,
            ).images[0]

            image_dir = IMAGE_DIR / lesson_id
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = image_dir / f"{part['id']}-{example['id']}.png"
            image.save(image_path)

            example["image_url"] = f"/content/images/{lesson_id}/{part['id']}-{example['id']}.png"
            generated += 1
            print(f"{lesson_id}/{part['id']}/{example['id']}: generated example image")

            path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")

    return generated


def main() -> None:
    selected = sys.argv[1:]
    paths = _lesson_files(selected)
    print(f"Processing {len(paths)} lecture file(s)")

    pipe = _load_pipeline()
    total = 0
    for path in paths:
        try:
            total += _process_lesson(pipe, path)
        except Exception:
            print(f"ERROR processing {path.name}, continuing with next lecture")
            import traceback  # noqa: PLC0415

            traceback.print_exc()

    print(f"Done. Generated {total} new image(s).")


if __name__ == "__main__":
    main()
