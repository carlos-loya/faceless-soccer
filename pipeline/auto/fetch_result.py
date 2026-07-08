# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Deterministic WC2026 result fetcher — the finality gate for the auto match pipeline.

The brain's grounding (soccer-news) can hallucinate scores/scorers (it once wrote "Zico scored
both Egypt goals"), so the automation must NOT decide a match is final — or what the score was —
from LLM judgment. This pulls the authoritative result from ESPN's free scoreboard endpoint
(no API key) and, only when ESPN says the match is over (status state == "post"), writes the real
score + scorers into kb/fixtures.json. Everything downstream (the /match-recap "result present?"
gate, videospec, fact-check) then works off verified ground truth.

Fails safe: if the match isn't `post`, or ESPN is unreachable, or the event can't be matched,
it writes nothing and exits non-zero — so the runner skips the match and retries next cron.

Usage:
  uv run pipeline/auto/fetch_result.py <fixture-id> [--write]
    <fixture-id>   an id in kb/fixtures.json (e.g. qf-01)
    --write        patch the result into kb/fixtures.json (default: dry-run, print only)

Exit 0 = final result found (and written with --write). Non-zero = not final / not found / error.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "kb" / "fixtures.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={ymd}"


def load_fixtures() -> dict:
    return json.loads(FIXTURES.read_text())


def find_match(data: dict, fid: str) -> dict | None:
    return next((m for m in data.get("matches", []) if m.get("id") == fid), None)


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _team_matches(kb_name: str, comp: dict) -> bool:
    """True if this ESPN competitor is the KB team (display/short/abbrev, case-insensitive)."""
    t = comp.get("team", {})
    kb = _norm(kb_name)
    cands = {_norm(t.get(k, "")) for k in ("displayName", "shortDisplayName", "name", "location", "abbreviation")}
    cands.discard("")
    if kb in cands:
        return True
    # last resort: containment either way (handles "United States" vs "USA" style gaps)
    return any(kb in c or c in kb for c in cands)


def espn_scoreboard(ymd: str) -> list[dict]:
    url = ESPN.format(ymd=ymd)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("events", [])


def find_event(home: str, away: str, ymd: str) -> dict | None:
    """Look on the fixture date and ±1 day (ET/UTC grouping can shift a late kickoff)."""
    base = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
    for delta in (0, -1, 1):
        d = (base + timedelta(days=delta)).strftime("%Y%m%d")
        try:
            events = espn_scoreboard(d)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            continue
        for e in events:
            comps = e.get("competitions", [{}])[0].get("competitors", [])
            if len(comps) == 2 and any(_team_matches(home, c) for c in comps) and any(_team_matches(away, c) for c in comps):
                return e
    return None


def extract_result(event: dict, home: str, away: str) -> dict:
    comp = event["competitions"][0]
    status = comp.get("status", {}).get("type", {})
    detail = status.get("detail") or status.get("shortDetail") or ""

    comps = comp.get("competitors", [])
    home_c = next(c for c in comps if _team_matches(home, c))
    away_c = next(c for c in comps if _team_matches(away, c))
    side_by_teamid = {home_c.get("team", {}).get("id"): "home", away_c.get("team", {}).get("id"): "away"}

    scorers = []
    for d in comp.get("details", []):
        if not d.get("scoringPlay"):
            continue
        ath = d.get("athletesInvolved") or [{}]
        scorers.append({
            "name": ath[0].get("displayName", "?"),
            "minute": d.get("clock", {}).get("displayValue", ""),
            "team": side_by_teamid.get(d.get("team", {}).get("id"), "?"),
            "type": d.get("type", {}).get("text", ""),
        })

    # readable note, grouped by side (matches the existing hand-written note style)
    def side_str(name: str, side: str) -> str:
        goals = [f"{s['name']} {s['minute']}" for s in scorers if s["team"] == side]
        return f"{name}: {', '.join(goals)}" if goals else ""
    parts = [p for p in (side_str(home, "home"), side_str(away, "away")) if p]
    note = f"{detail} — " + "; ".join(parts) if parts else detail

    result = {
        "home": int(home_c.get("score", 0)),
        "away": int(away_c.get("score", 0)),
        "note": note,
        "scorers": scorers,
        "detail": detail,
        "source": "espn",
        "verified": True,
    }
    # penalty shootout, if any
    hs, as_ = home_c.get("shootoutScore"), away_c.get("shootoutScore")
    if hs is not None and as_ is not None:
        result["shootout"] = {"home": hs, "away": as_}
    return result


def write_result(fid: str, match: dict, result: dict) -> None:
    """Patch ONE match's line in kb/fixtures.json, preserving the one-line-per-match format."""
    match = dict(match)
    match["status"] = "finished"
    match["result"] = result
    new_body = json.dumps(match, ensure_ascii=False)  # default separators match the file's style

    lines = FIXTURES.read_text().splitlines(keepends=True)
    token = f'"id": "{fid}"'
    for i, line in enumerate(lines):
        if token in line:
            indent = line[: len(line) - len(line.lstrip())]
            trailing = "," if line.rstrip().endswith(",") else ""
            eol = "\n" if line.endswith("\n") else ""
            lines[i] = f"{indent}{new_body}{trailing}{eol}"
            FIXTURES.write_text("".join(lines))
            return
    raise SystemExit(f"could not locate line for fixture {fid} in {FIXTURES}")


def fetch(fid: str, write: bool) -> int:
    data = load_fixtures()
    match = find_match(data, fid)
    if not match:
        print(f"[fetch_result] unknown fixture id: {fid}", file=sys.stderr)
        return 2
    home, away = match.get("home"), match.get("away")
    if not home or not away or home == "TBD" or away == "TBD":
        print(f"[fetch_result] {fid}: teams not set yet ({home} v {away})", file=sys.stderr)
        return 3

    event = find_event(home, away, match["date"].replace("-", ""))
    if not event:
        print(f"[fetch_result] {fid}: no ESPN event for {home} v {away} around {match['date']}", file=sys.stderr)
        return 4

    state = event["competitions"][0].get("status", {}).get("type", {}).get("state")
    if state != "post":
        detail = event["competitions"][0].get("status", {}).get("type", {}).get("detail", state)
        print(f"[fetch_result] {fid}: not final yet (state={state}, {detail})", file=sys.stderr)
        return 5

    result = extract_result(event, home, away)
    if write:
        write_result(fid, match, result)
        print(f"[fetch_result] {fid}: WROTE {home} {result['home']}–{result['away']} {away} ({result['detail']})", file=sys.stderr)
    print(json.dumps({"id": fid, "home": home, "away": away, "result": result}, ensure_ascii=False, indent=2))
    return 0


def _selfcheck() -> None:
    """Live self-check: r16-06 is a known-good finished match (USA 1 – Belgium 4)."""
    data = load_fixtures()
    m = find_match(data, "r16-06")
    assert m, "r16-06 missing from fixtures"
    ev = find_event(m["home"], m["away"], m["date"].replace("-", ""))
    assert ev, "ESPN event for r16-06 not found (network?)"
    r = extract_result(ev, m["home"], m["away"])
    assert (r["home"], r["away"]) == (1, 4), f"expected USA 1–4 Belgium, got {r['home']}–{r['away']}"
    assert any("Lukaku" in s["name"] for s in r["scorers"]), "expected Lukaku among scorers"
    print("selfcheck OK:", r["home"], "-", r["away"], "| scorers:", len(r["scorers"]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch a WC2026 final result from ESPN")
    ap.add_argument("fixture_id", nargs="?", help="fixture id in kb/fixtures.json (e.g. qf-01)")
    ap.add_argument("--write", action="store_true", help="patch the result into kb/fixtures.json")
    ap.add_argument("--selfcheck", action="store_true", help="verify against known-good r16-06 and exit")
    args = ap.parse_args()

    if args.selfcheck:
        _selfcheck()
        return
    if not args.fixture_id:
        ap.error("fixture_id is required (or use --selfcheck)")
    sys.exit(fetch(args.fixture_id, args.write))


if __name__ == "__main__":
    main()
