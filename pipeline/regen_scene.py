# /// script
# requires-python = ">=3.10"
# dependencies = ["elevenlabs", "python-dotenv"]
# ///
"""Regenerate a SINGLE scene's VO (+ patch the assets props.json) without re-spending
credits on the whole video. Usage: uv run pipeline/regen_scene.py <spec_stem> <scene_index>"""
import json, os, sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
from elevenlabs.client import ElevenLabs

from generate_assets import say, eleven_tts, audio_seconds, VOICE_ID  # shared VO helpers

STEM = sys.argv[1]
IDX = int(sys.argv[2])

assets = Path("out/assets") / STEM
spec = json.loads(Path(f"out/specs/{STEM}.json").read_text())
sc = next(s for s in spec["scenes"] if s["index"] == IDX)

el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
mp3 = assets / f"scene-{IDX}.mp3"
text = say(sc["voiceover"])
print(f"regenerating scene-{IDX} VO: {text}")
# Timestamped TTS so the karaoke word-timings refresh too (was a gap: plain convert left them stale).
words = eleven_tts(el, VOICE_ID, text, mp3)
d = audio_seconds(mp3)

props = json.loads((assets / "props.json").read_text())
for s in props["scenes"]:
    if s.get("index") == IDX:
        s.update({"voiceover": sc["voiceover"], "on_screen_text": sc["on_screen_text"],
                  "graphic_type": sc["graphic_type"], "audio_seconds": d, "words": words})
props["total_seconds"] = round(sum(s["audio_seconds"] for s in props["scenes"]), 2)
(assets / "props.json").write_text(json.dumps(props, indent=2))
print(f"patched props.json; scene-{IDX} dur {d}s; total {props['total_seconds']}s")
