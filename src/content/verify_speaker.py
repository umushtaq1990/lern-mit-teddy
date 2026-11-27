"""Verifies which transcript segments are actually the LECTURER's voice,
not a student's -- lectures have students introducing themselves, asking
questions, etc., and picking a reference clip by content alone (does it
*sound* like teaching?) isn't reliable enough for voice cloning, where the
whole result depends on the reference being single-speaker and correct.

Approach: Whisper's segment timestamps have no speaker labels, so this
uses resemblyzer (a lightweight pretrained speaker-embedding model, no
gated HF model/account needed) to compute a voice-embedding "fingerprint"
per audio snippet, anchored against a segment we're highly confident is
the lecturer (the class's opening Islamic greeting, which a teacher says
to start class, not a student) -- then scores every other sampled segment
by cosine similarity to that anchor. High similarity = same speaker.

Must be run with the isolated .venv-voiceclone interpreter:
    .venv-voiceclone\\Scripts\\python.exe -m src.content.verify_speaker
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.content.lecture_audio import extract_audio_clip, load_transcript  # noqa: E402

SCRATCH_DIR = REPO_ROOT / "scratch_speaker_check"


def _embed_clip(encoder: VoiceEncoder, source_video: str, start: float, end: float) -> np.ndarray:
    clip_path = SCRATCH_DIR / f"clip_{start:.0f}_{end:.0f}.wav"
    import static_ffmpeg  # noqa: PLC0415

    static_ffmpeg.add_paths()
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    ffmpeg = shutil.which("ffmpeg")
    SCRATCH_DIR.mkdir(exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-ss", str(start), "-i", source_video, "-t", str(end - start),
        "-vn", "-ar", "16000", "-ac", "1", str(clip_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    wav = preprocess_wav(clip_path)
    return encoder.embed_utterance(wav)


def main() -> None:
    class_number = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    transcript = load_transcript(class_number)
    source = transcript["source_path"]
    encoder = VoiceEncoder()

    # Anchor: the opening Islamic greeting (bismillah...) -- a teacher
    # opens class with this, a student introducing themselves would not.
    anchor_start, anchor_end = 4.0, 24.0
    print(f"Anchor (assumed lecturer): {anchor_start}-{anchor_end}s")
    anchor_embed = _embed_clip(encoder, source, anchor_start, anchor_end)

    # Candidate stretches to check -- spread through the lecture, each a
    # contiguous ~30-40s chunk, picked from segments with real content.
    candidates = [
        (100, 140), (300, 340), (500, 540), (660, 700), (900, 940),
        (1200, 1240), (1800, 1840), (2400, 2440), (3000, 3040),
    ]

    results = []
    for start, end in candidates:
        try:
            embed = _embed_clip(encoder, source, start, end)
            similarity = float(np.dot(anchor_embed, embed))
            results.append((start, end, similarity))
        except Exception as exc:
            results.append((start, end, None))
            print(f"{start}-{end}s: FAILED ({exc})")

    results.sort(key=lambda r: (r[2] is None, -(r[2] or 0)))
    print("\nResults (sorted by similarity to the lecturer anchor, highest first):")
    for start, end, sim in results:
        label = f"{sim:.3f}" if sim is not None else "ERROR"
        flag = " <-- likely LECTURER" if sim is not None and sim > 0.75 else ""
        print(f"  {start:5d}-{end:<5d}s  similarity={label}{flag}")


if __name__ == "__main__":
    main()
