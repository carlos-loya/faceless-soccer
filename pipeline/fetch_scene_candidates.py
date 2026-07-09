# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Per-spec image candidates for `commons` scenes — fetch several VALIDATED options per scene so
the `pick-images` skill (Claude vision) can choose the correct one. Keyword search alone returns
plausible-but-wrong images (e.g. "FIFA World Cup Trophy" -> Germany lifting it).

Run:  uv run pipeline/fetch_scene_candidates.py out/specs/<stem>.json
Out:  out/candidates/<stem>/scene<N>/cand-*.<ext>  +  out/candidates/<stem>/candidates.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from commons import candidates_for

N = 6  # candidates per scene


def main() -> None:
    spec_path = Path(sys.argv[1])
    spec = json.loads(spec_path.read_text())
    base = Path("out/candidates") / spec_path.stem
    base.mkdir(parents=True, exist_ok=True)

    manifest = {}
    for sc in spec.get("scenes", []):
        if sc.get("visual_source") != "commons":
            continue
        idx, q = sc["index"], sc.get("visual_query", "")
        cands = candidates_for(q, base / f"scene{idx}", N)
        manifest[str(idx)] = {
            "query": q, "on_screen_text": sc.get("on_screen_text", ""),
            "voiceover": sc.get("voiceover", ""), "candidates": cands,
        }
        print(f"  scene {idx} '{q}': {len(cands)} candidates")

    (base / "candidates.json").write_text(json.dumps(manifest, indent=2))
    print("no commons scenes — nothing to pick." if not manifest
          else f"\n-> {base}/candidates.json  (now run the pick-images skill)")


if __name__ == "__main__":
    main()
