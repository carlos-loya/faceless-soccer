# /// script
# requires-python = ">=3.10"
# dependencies = ["elevenlabs", "python-dotenv"]
# ///
"""Regenerate a SINGLE scene's VO (+ patch the assets props.json) without re-spending
credits on the whole video. Usage: uv run pipeline/regen_scene.py <spec_stem> <scene_index>
Uses the same engine dispatch as a full run: default = production ElevenLabs; set TTV_DRAFT=1 for a
free draft re-record (VoiceBox/Carlos, Piper fallback)."""
import json, os, sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from generate_assets import say, synth_vo, audio_seconds, DRAFT  # shared VO dispatch (engine via env)

STEM = sys.argv[1]
IDX = int(sys.argv[2])

assets = Path("out/assets") / STEM
spec = json.loads(Path(f"out/specs/{STEM}.json").read_text())
sc = next(s for s in spec["scenes"] if s["index"] == IDX)

el = None
if not DRAFT:  # production re-record needs the ElevenLabs client; a draft (VoiceBox/Piper) doesn't
    from elevenlabs.client import ElevenLabs
    el = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
mp3 = assets / f"scene-{IDX}.mp3"
text = say(sc["voiceover"])
print(f"regenerating scene-{IDX} VO: {text}")
# synth_vo refreshes karaoke word-timings too (ElevenLabs = real; VoiceBox/Piper = approximate).
words = synth_vo(el, text, mp3, display_text=sc["voiceover"])
d = audio_seconds(mp3)

props = json.loads((assets / "props.json").read_text())
for s in props["scenes"]:
    if s.get("index") == IDX:
        s.update({"voiceover": sc["voiceover"], "on_screen_text": sc["on_screen_text"],
                  "graphic_type": sc["graphic_type"], "audio_seconds": d, "words": words})
props["total_seconds"] = round(sum(s["audio_seconds"] for s in props["scenes"]), 2)
(assets / "props.json").write_text(json.dumps(props, indent=2))
print(f"patched props.json; scene-{IDX} dur {d}s; total {props['total_seconds']}s")
