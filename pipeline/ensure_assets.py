# /// script
# requires-python = ">=3.10"
# ///
"""
Auto-fetch + auto-cutout — make visuals fully hands-off.

Given a spec, ensure every entity it references has a free CC image in the KB, and the
subject has a cutout — creating stub entities, fetching images, and cutting out as needed.
After this runs, prepare.mjs finds everything ready.

Run:  uv run pipeline/ensure_assets.py out/specs/<stem>.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def deslug(s: str) -> str:
    return s.replace("-", " ").title()


def main() -> None:
    spec = json.loads(Path(sys.argv[1]).read_text())
    ent_dir = Path("kb/entities")
    ent_dir.mkdir(parents=True, exist_ok=True)

    # Every entity the spec references: the subject + each scene's `entity` background,
    # PLUS every nation named in `matchup` (scoreboard/VS badge) and each `group_table` row.
    # Those nations are only referenced by the scoreboard/standings renderer — if their flag
    # entity is missing, prepare.mjs silently drops the row (or the whole scoreboard), so they
    # MUST be ensured here too.
    referenced = set()
    nations = set()
    if spec.get("subject"):
        referenced.add(spec["subject"])
    for slug in spec.get("matchup") or []:
        if slug:
            nations.add(slug)
    for sc in spec.get("scenes", []):
        if sc.get("visual_source") == "entity" and sc.get("visual_query"):
            referenced.add(sc["visual_query"])
        for row in sc.get("group_table") or []:
            if row.get("team"):
                nations.add(row["team"])
    referenced |= nations

    need_image = []
    for slug in sorted(referenced):
        p = ent_dir / f"{slug}.json"
        if not p.exists():
            p.write_text(json.dumps({
                "slug": slug, "type": "nation" if slug in nations else "auto",
                "name": deslug(slug),
                "facts": {}, "image": None, "active_narratives": [], "last_verified": "",
            }, indent=2) + "\n")
            print(f"  + created stub entity: {slug} ({deslug(slug)})")
            need_image.append(slug)
        elif not json.loads(p.read_text()).get("image"):
            need_image.append(slug)

    if need_image:
        print(f"  fetching CC images: {', '.join(need_image)}")
        subprocess.run(["uv", "run", "pipeline/fetch_images.py", *need_image], check=False)

    # Cutout the subject (for the corner sticker), if it now has an image and lacks a cutout.
    subj = spec.get("subject")
    if subj:
        ent = json.loads((ent_dir / f"{subj}.json").read_text())
        if ent.get("image") and not Path(f"out/cutouts/{subj}.png").exists():
            print(f"  cutting out subject: {subj}")
            subprocess.run(["uv", "run", "pipeline/cutout.py", subj], check=False)

    print("assets ensured.")


if __name__ == "__main__":
    main()
