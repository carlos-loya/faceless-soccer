# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Image candidates — fetch several free Wikimedia Commons options for a query so a HUMAN/Claude
can VISUALLY pick the right one (keyword search alone returns plausible-but-wrong images, e.g.
"FIFA World Cup Trophy" -> Germany lifting it). The chosen image is then curated onto a KB
entity for correct, reusable visuals.

Run:  uv run pipeline/fetch_candidates.py "FIFA World Cup Trophy" 8
Out:  out/candidates/<slug>/cand-N.<ext>  +  candidates.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from commons import candidates_for


def main() -> None:
    query = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    out = Path("out/candidates") / slug
    manifest = candidates_for(query, out, n)
    for c in manifest:
        print(f"  [{c['index']}] {c.get('title','')}  ({c.get('width','?')}px)")
    (out / "candidates.json").write_text(json.dumps(manifest, indent=2))
    print(f"\n{len(manifest)} candidates -> {out}/")


if __name__ == "__main__":
    main()
