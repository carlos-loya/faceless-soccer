# /// script
# requires-python = ">=3.10"
# dependencies = ["elevenlabs", "python-dotenv"]
# ///
"""Regenerate a SINGLE scene's VO (+ patch the assets props.json) without re-spending
credits on the whole video. Usage: uv run pipeline/regen_scene.py <spec_stem> <scene_index>"""
import base64, json, os, re, subprocess, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from elevenlabs.client import ElevenLabs

STEM = sys.argv[1]
IDX = int(sys.argv[2])
VOICE_ID = os.environ.get("TTV_VOICE_ID", "Gubgw9l4dtIoQA9YZHgx")  # Brian — channel default voice (paid-library; needs >= Starter)
TTS_MODEL = "eleven_multilingual_v2"

assets = Path("out/assets") / STEM
spec = json.loads(Path(f"out/specs/{STEM}.json").read_text())
sc = next(s for s in spec["scenes"] if s["index"] == IDX)

PRON = {k: v for k, v in json.loads(Path("pipeline/pronunciations.json").read_text()).items()
        if not k.startswith("_")}  # "_"-prefixed keys are metadata; respellings ship empty by default
def say(t):
    for k in sorted(PRON, key=len, reverse=True):
        t = re.sub(re.escape(k), PRON[k], t, flags=re.IGNORECASE)
    return t

def _field(obj, *names):
    for n in names:
        v = getattr(obj, n, None)
        if v is None and isinstance(obj, dict):
            v = obj.get(n)
        if v is not None:
            return v
    return None

def words_from_alignment(alignment):
    chars = _field(alignment, "characters") or []
    starts = _field(alignment, "character_start_times_seconds") or []
    ends = _field(alignment, "character_end_times_seconds") or []
    words, cur, cs, ce = [], "", None, None
    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if cur.strip():
                words.append({"word": cur, "start": round(cs, 3), "end": round(ce, 3)})
            cur, cs, ce = "", None, None
        else:
            if cs is None:
                cs = st
            cur += ch
            ce = en
    if cur.strip():
        words.append({"word": cur, "start": round(cs, 3), "end": round(ce, 3)})
    return words

el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
mp3 = assets / f"scene-{IDX}.mp3"
text = say(sc["voiceover"])
print(f"regenerating scene-{IDX} VO: {text}")
# Timestamped TTS so the karaoke word-timings refresh too (was a gap: plain convert left them stale).
resp = el.text_to_speech.convert_with_timestamps(voice_id=VOICE_ID, model_id=TTS_MODEL, text=text, output_format="mp3_44100_128")
mp3.write_bytes(base64.b64decode(_field(resp, "audio_base_64", "audio_base64")))
alignment = _field(resp, "normalized_alignment") or _field(resp, "alignment")
words = words_from_alignment(alignment) if alignment is not None else []

def dur(p):
    o = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(p)], text=True)
    return round(float(o.strip()), 3)
d = dur(mp3)

props = json.loads((assets / "props.json").read_text())
for s in props["scenes"]:
    if s.get("index") == IDX:
        s.update({"voiceover": sc["voiceover"], "on_screen_text": sc["on_screen_text"],
                  "stat_callout": sc["stat_callout"], "graphic_type": sc["graphic_type"],
                  "audio_seconds": d, "words": words})
props["total_seconds"] = round(sum(s["audio_seconds"] for s in props["scenes"]), 2)
(assets / "props.json").write_text(json.dumps(props, indent=2))
print(f"patched props.json; scene-{IDX} dur {d}s; total {props['total_seconds']}s")
