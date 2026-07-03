# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
WC2026 fixture query — the schedule side of the automated match pipeline.

Reads kb/fixtures.json (maintained by the soccer-news skill) and answers the questions the
auto orchestrator + owner ask: what finished recently, what's on today, what's next. The
`--notable` filter encodes the coverage rule the owner chose — **knockouts + big teams**:
a match is notable if its stage is a knockout round OR either side is a watchlist nation
(kb/watchlist.json → nations).

Usage:
  uv run pipeline/fixtures.py today            [--notable] [--json]
  uv run pipeline/fixtures.py upcoming [--n N]  [--notable] [--json]
  uv run pipeline/fixtures.py next              [--notable] [--json]
  uv run pipeline/fixtures.py recent [--hours N][--notable] [--json]   # finished in last N hours

`recent` is what the cron polls: matches considered finished whose kickoff (or, if the exact
time is unknown, end-of-match-day) falls within the last N hours. Pair with the auto
orchestrator's processed-ledger so each match is handled once.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "kb" / "fixtures.json"
WATCHLIST = ROOT / "kb" / "watchlist.json"

ET = timezone(timedelta(hours=-4))          # America/New_York during the WC window (EDT)
KNOCKOUT = {"r32", "r16", "qf", "sf", "third", "final"}
# Matches with no exact kickoff time are assumed to finish ~this hour ET on their match day.
ASSUMED_KICKOFF_HOUR = 20                    # 8pm ET — conservative "day is over" marker
ASSUMED_DURATION_H = 2.5                     # kickoff -> final whistle (covers a.e.t.)


def load_matches() -> list[dict]:
    data = json.loads(FIXTURES.read_text())
    return data.get("matches", [])


def watchlist_nations() -> set[str]:
    try:
        return set(json.loads(WATCHLIST.read_text()).get("nations", []))
    except Exception:
        return set()


def is_notable(m: dict, nations: set[str]) -> bool:
    if m.get("stage") in KNOCKOUT:
        return True
    return bool({m.get("home_slug"), m.get("away_slug")} & nations)


def kickoff_dt(m: dict) -> datetime:
    """Best-effort kickoff instant (tz-aware). Falls back to an assumed evening slot on the date."""
    ko = m.get("kickoff_et")
    if ko:
        try:
            return datetime.fromisoformat(ko)
        except ValueError:
            pass
    d = datetime.fromisoformat(m["date"]).date()
    return datetime(d.year, d.month, d.day, ASSUMED_KICKOFF_HOUR, 0, tzinfo=ET)


def final_whistle(m: dict) -> datetime:
    return kickoff_dt(m) + timedelta(hours=ASSUMED_DURATION_H)


def is_finished(m: dict, now: datetime) -> bool:
    # Trust an explicit status; otherwise infer from the clock.
    if m.get("status") == "finished":
        return True
    if m.get("status") == "scheduled" and m.get("result") is None:
        # allow the clock to override a stale 'scheduled' once the match is clearly over
        return now >= final_whistle(m)
    return now >= final_whistle(m)


def matchup(m: dict) -> str:
    return f'{m.get("home", "TBD")} vs {m.get("away", "TBD")}'


def score(m: dict) -> str:
    r = m.get("result")
    if not r:
        return ""
    s = f'{r.get("home")}–{r.get("away")}'
    return f'{s} ({r["note"]})' if r.get("note") else s


def select(cmd: str, matches: list[dict], now: datetime, hours: int, n: int) -> list[dict]:
    if cmd == "today":
        today = now.astimezone(ET).date().isoformat()
        out = [m for m in matches if m["date"] == today]
    elif cmd == "recent":
        cutoff = now - timedelta(hours=hours)
        out = [m for m in matches if is_finished(m, now) and final_whistle(m) >= cutoff]
        out.sort(key=final_whistle)
    elif cmd == "upcoming":
        out = [m for m in matches if not is_finished(m, now)]
        out.sort(key=kickoff_dt)
        out = out[:n]
    elif cmd == "next":
        out = sorted((m for m in matches if not is_finished(m, now)), key=kickoff_dt)[:1]
    else:
        raise SystemExit(f"unknown command: {cmd}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="WC2026 fixture query")
    ap.add_argument("command", choices=["today", "upcoming", "next", "recent"])
    ap.add_argument("--notable", action="store_true", help="knockouts + watchlist-nation matches only")
    ap.add_argument("--hours", type=int, default=36, help="recent: finished within the last N hours")
    ap.add_argument("--n", type=int, default=8, help="upcoming: how many to show")
    ap.add_argument("--json", action="store_true", help="emit JSON (for the orchestrator)")
    ap.add_argument("--now", help="override 'now' (ISO) for testing")
    args = ap.parse_args()

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ET)

    matches = load_matches()
    if args.notable:
        nations = watchlist_nations()
        matches = [m for m in matches if is_notable(m, nations)]

    out = select(args.command, matches, now, args.hours, args.n)

    if args.json:
        print(json.dumps(out, indent=2))
        return

    if not out:
        print(f"(no {args.command} matches)")
        return
    for m in out:
        line = f'  {m["id"]:<8} {m.get("stage", ""):<6} {m["date"]}  {matchup(m)}'
        sc = score(m)
        if sc:
            line += f"   → {sc}"
        print(line)


if __name__ == "__main__":
    main()
