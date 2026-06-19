# /// script
# requires-python = ">=3.10"
# dependencies = ["google-genai", "elevenlabs", "python-dotenv", "piper-tts"]
# ///
"""
Stage A of the render pipeline: VideoSpec JSON -> real assets.

For each scene it:
  - generates the graphic via Nano Banana (Gemini image)  -> scene-N.png
  - generates the voiceover via ElevenLabs                 -> scene-N.mp3
  - measures audio duration (ffprobe)
…then writes props.json (spec + asset paths + durations) for Stage B (Remotion).

Run:  uv run pipeline/generate_assets.py out/specs/lamine-yamal-trajectory.json
Keys come from .env (GEMINI_API_KEY, ELEVENLABS_API_KEY).
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

IMAGE_MODEL = "gemini-2.5-flash-image"      # Nano Banana (free tier)
TTS_MODEL = "eleven_multilingual_v2"
VOICE_ID = os.environ.get("TTV_VOICE_ID", "Gubgw9l4dtIoQA9YZHgx")  # Brian — channel default voice (paid-library; needs >= Starter). Override per-run with TTV_VOICE_ID.

# DRAFT mode (TTV_DRAFT=1): synthesize VO with a FREE local TTS (Piper) instead of ElevenLabs,
# so you can preview backgrounds / players / layout / pacing and get everything right BEFORE
# spending paid credits. Karaoke word-timings are approximated (length-weighted) — the real
# ElevenLabs pass restores exact sync. Same props.json shape, so prepare.mjs + render are identical.
DRAFT = bool(os.environ.get("TTV_DRAFT"))
PIPER_VOICE = os.environ.get("TTV_PIPER_VOICE", "en_US-lessac-medium")
_piper = None  # cached PiperVoice

# Pronunciation dictionary — applied to VOICEOVER text ONLY (on-screen text keeps correct spelling).
# OFF by default (owner pref 2026-06-13): pronunciations.json ships empty. Only add an entry when a
# specific name comes out REALLY BAD in the actual VO — don't pre-load names speculatively. Keys
# beginning with "_" are metadata/comments and are ignored. (Full prior dict: pronunciations.archive.json.)
try:
    PRON = {k: v for k, v in json.loads((Path(__file__).parent / "pronunciations.json").read_text()).items()
            if not k.startswith("_")}
except Exception:
    PRON = {}


def say(text: str) -> str:
    out = text
    for k in sorted(PRON, key=len, reverse=True):  # longest key first to avoid partial overlaps
        out = re.sub(re.escape(k), PRON[k], out, flags=re.IGNORECASE)
    return out

STYLE_SUFFIX = (
    " Vertical 9:16 portrait. Deep black background, gold gradient accents "
    "(#F7D774 to #C8881B), crisp white bold condensed type. Premium broadcast feel. "
    "No real human faces, no logos, no watermarks."
)


def gemini_image(client, prompt: str, out_path: Path) -> bool:
    from google.genai import types
    resp = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=[prompt + STYLE_SUFFIX],
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    )
    for part in resp.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            data = inline.data
            if isinstance(data, str):
                data = base64.b64decode(data)
            out_path.write_bytes(data)
            return True
    return False


def _field(obj, *names):
    """Read a field by name from a pydantic object OR a dict (SDK shape tolerance)."""
    for n in names:
        v = getattr(obj, n, None)
        if v is None and isinstance(obj, dict):
            v = obj.get(n)
        if v is not None:
            return v
    return None


def words_from_alignment(alignment) -> list[dict]:
    """Aggregate ElevenLabs character-level timestamps into word-level [{word,start,end}]."""
    chars = _field(alignment, "characters") or []
    starts = _field(alignment, "character_start_times_seconds") or []
    ends = _field(alignment, "character_end_times_seconds") or []
    words: list[dict] = []
    cur, cur_start, cur_end = "", None, None
    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if cur.strip():
                words.append({"word": cur, "start": round(cur_start, 3), "end": round(cur_end, 3)})
            cur, cur_start, cur_end = "", None, None
        else:
            if cur_start is None:
                cur_start = st
            cur += ch
            cur_end = en
    if cur.strip():
        words.append({"word": cur, "start": round(cur_start, 3), "end": round(cur_end, 3)})
    return words


def eleven_tts(client, voice_id: str, text: str, out_path: Path) -> list[dict]:
    """Generate VO with word-level timestamps (for karaoke captions). Writes the mp3 and
    returns [{word,start,end}] in seconds relative to the clip start. Same call cost as plain TTS."""
    resp = client.text_to_speech.convert_with_timestamps(
        voice_id=voice_id,
        model_id=TTS_MODEL,
        text=text,
        output_format="mp3_44100_128",
    )
    audio_b64 = _field(resp, "audio_base_64", "audio_base64")
    out_path.write_bytes(base64.b64decode(audio_b64))
    alignment = _field(resp, "normalized_alignment") or _field(resp, "alignment")
    return words_from_alignment(alignment) if alignment is not None else []


def split_words(text: str, duration: float) -> list[dict]:
    """Approximate per-word timings by spreading the words across `duration`, weighted by word
    length. Good enough for a DRAFT karaoke preview (real sync comes from ElevenLabs)."""
    toks = text.split()
    if not toks or duration <= 0:
        return []
    weights = [len(t) + 1 for t in toks]
    total = sum(weights)
    words, t = [], 0.0
    for tok, w in zip(toks, weights):
        slice_dur = duration * w / total
        words.append({"word": tok, "start": round(t, 3), "end": round(t + slice_dur, 3)})
        t += slice_dur
    return words


def _piper_voice():
    """Load (download once) the Piper voice, cached in out/.piper/."""
    global _piper
    if _piper is None:
        from piper import PiperVoice
        from piper.download_voices import download_voice
        cache = Path("out/.piper"); cache.mkdir(parents=True, exist_ok=True)
        onnx = cache / f"{PIPER_VOICE}.onnx"
        if not onnx.exists():
            print(f"  [draft] downloading Piper voice {PIPER_VOICE} …", flush=True)
            download_voice(PIPER_VOICE, cache)
        _piper = PiperVoice.load(str(onnx))
    return _piper


def piper_tts(text: str, out_path: Path, display_text: str | None = None) -> list[dict]:
    """DRAFT VO via Piper (free, local). Writes an mp3 and returns approximate word timings.
    `display_text` (the un-respelled original) is used for the karaoke word list so the draft
    shows correct spelling even if `text` was phonetically respelled for the voice."""
    import wave
    voice = _piper_voice()
    wav_path = out_path.with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as wf:
        voice.synthesize_wav(text, wf)
    # wav -> mp3 (keep the .mp3 path the rest of the pipeline expects)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav_path),
         "-codec:a", "libmp3lame", "-q:a", "4", str(out_path)],
        check=True,
    )
    wav_path.unlink(missing_ok=True)
    return split_words(display_text or text, audio_seconds(out_path))


def synth_vo(client, text: str, out_path: Path, display_text: str | None = None) -> list[dict]:
    """Dispatch one VO clip to Piper (DRAFT) or ElevenLabs (real). Returns word timings.

    `text` is the spoken (phonetically respelled) text; `display_text` is the original
    correct spelling. Karaoke captions must show `display_text`, never the respelling — so
    we re-map the timed words back to the original spelling when the token counts match
    (respellings keep word boundaries, so they do). If counts differ, keep the spoken words."""
    if DRAFT:
        return piper_tts(text, out_path, display_text)
    words = eleven_tts(client, VOICE_ID, text, out_path)
    if display_text and display_text != text:
        disp = display_text.split()
        if len(disp) == len(words):
            words = [{**w, "word": d} for w, d in zip(words, disp)]
    return words


def audio_seconds(path: Path) -> float:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            text=True,
        )
        return round(float(out.strip()), 3)
    except Exception:
        return 0.0


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: uv run pipeline/generate_assets.py <spec.json>")
    spec_path = Path(sys.argv[1])
    spec = json.loads(spec_path.read_text())
    stem = spec_path.stem
    assets = Path("out/assets") / stem
    assets.mkdir(parents=True, exist_ok=True)

    skip_images = bool(os.environ.get("TTV_SKIP_IMAGES"))
    gem = None
    if not skip_images:
        from google import genai
        gem = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    el = None
    if not DRAFT:
        from elevenlabs.client import ElevenLabs
        el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

    print(f"VO engine: {'Piper (DRAFT — free, local)' if DRAFT else 'ElevenLabs (paid)'} | "
          f"voice: {PIPER_VOICE if DRAFT else VOICE_ID}")

    out_scenes = []
    for sc in spec["scenes"]:
        i = sc["index"]
        png = assets / f"scene-{i}.png"
        mp3 = assets / f"scene-{i}.mp3"

        img_path = None
        if os.environ.get("TTV_SKIP_IMAGES"):
            print(f"[scene {i}] image SKIPPED (Remotion will render graphics)")
        else:
            print(f"[scene {i}] image …", flush=True)
            try:
                if gemini_image(gem, sc["graphic_prompt"], png):
                    img_path = str(png)
                    print(f"[scene {i}] image OK {png}")
                else:
                    print(f"[scene {i}] image FAILED (no image part)")
            except Exception as e:
                msg = str(e).split("\n")[0][:120]
                print(f"[scene {i}] image SKIPPED — {msg}")

        print(f"[scene {i}] voiceover …", flush=True)
        words = synth_vo(el, say(sc["voiceover"]), mp3, display_text=sc["voiceover"])
        dur = audio_seconds(mp3)
        print(f"[scene {i}] vo OK {mp3} ({dur}s, {len(words)} words timed)")

        out_scenes.append({
            **sc,
            "image": img_path,
            "audio": str(mp3),
            "audio_seconds": dur,
            "words": words,
        })

    # Outro VO: voice the comment-bait question on the end card (strip emoji + trailing "yes or no").
    outro_text = re.sub(r"[^\w\s,.\-?!'\"]", "", spec.get("comment_bait", "")).strip()
    outro_text = re.sub(r"\s+yes or no\s*$", "", outro_text, flags=re.I).strip()
    outro = None
    if outro_text:
        outro_mp3 = assets / "outro.mp3"
        print("[outro] voiceover …", flush=True)
        synth_vo(el, say(outro_text), outro_mp3, display_text=outro_text)
        outro = {"audio": str(outro_mp3), "seconds": audio_seconds(outro_mp3), "text": outro_text}
        print(f"[outro] vo OK ({outro['seconds']}s)")

    props = {
        "spec_stem": stem,
        "format": spec["format"],
        "topic": spec["topic"],
        "voice": {"voice_id": VOICE_ID},
        "scenes": out_scenes,
        "comment_bait": spec["comment_bait"],
        "cta": spec["cta"],
        "outro": outro,
        "total_seconds": round(sum(s["audio_seconds"] for s in out_scenes), 2),
    }
    props_path = assets / "props.json"
    props_path.write_text(json.dumps(props, indent=2))
    print(f"\n✓ assets in {assets}/  | total VO {props['total_seconds']}s | props -> {props_path}")


if __name__ == "__main__":
    main()
