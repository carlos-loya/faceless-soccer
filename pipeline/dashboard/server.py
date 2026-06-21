#!/usr/bin/env python3
"""
TikiTakaFootyTV — Mission Control dashboard server.

A tiny stdlib-only HTTP server that turns the faceless-soccer pipeline into a
clickable control room. It does NOT spend Claude tokens for the deterministic
stages — it just shells out to the scripts that already exist:

    storyboard   -> bash pipeline/storyboard.sh out/specs/<stem>.json
    draft        -> bash pipeline/make_video.sh out/specs/<stem>.json
    production   -> TTV_PRODUCTION=1 bash pipeline/make_video.sh out/specs/<stem>.json
    publish      -> uv run pipeline/upload_youtube.py upload <spec> <mp4> --visibility ...
    gather       -> uv run pipeline/outlier_ingest.py   (deterministic viral feed)

Every action is deterministic glue — NO Claude is invoked from this server (no token
spend, no autonomous agents). The "brain" steps (/find-topics, videospec, /daily) stay
in your own Claude Code session; drop their briefs into out/topics/ and the dashboard
lists them automatically.

Run it:   python3 pipeline/dashboard/server.py   (then open http://localhost:8770)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                       # repo root
SPECS = ROOT / "out" / "specs"
STORY = ROOT / "out" / "storyboards"
RENDERS = ROOT / "out" / "renders"
PUBLISHED = ROOT / "out" / "published"
TOPICS = ROOT / "out" / "topics"
POSTLOG = PUBLISHED / "post-log.jsonl"
PORT = int(os.environ.get("TTV_DASHBOARD_PORT", "8770"))
DEFAULT_TZ = os.environ.get("TTV_SCHEDULE_TZ", "America/New_York")  # friendly times default to ET

TOPICS.mkdir(parents=True, exist_ok=True)
(ROOT / "out" / "dashboard" / "jobs").mkdir(parents=True, exist_ok=True)
JOBDIR = ROOT / "out" / "dashboard" / "jobs"

# ---------------------------------------------------------------- jobs ----------
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _new_job(kind: str, stem: str, cmd: list[str], env: dict | None = None) -> str:
    jid = uuid.uuid4().hex[:12]
    logpath = JOBDIR / f"{jid}.log"
    job = {
        "id": jid, "kind": kind, "stem": stem,
        "cmd": cmd, "status": "running", "returncode": None,
        "started": time.time(), "ended": None, "log": str(logpath),
    }
    with JOBS_LOCK:
        JOBS[jid] = job
    t = threading.Thread(target=_run_job, args=(job, cmd, env, logpath), daemon=True)
    t.start()
    return jid


def _run_job(job, cmd, env, logpath):
    full_env = os.environ.copy()
    # make sure ~/.local/bin (uv, claude) is reachable
    full_env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + full_env.get("PATH", "")
    if env:
        full_env.update(env)
    with open(logpath, "w", encoding="utf-8") as lf:
        lf.write(f"$ {' '.join(cmd)}\n\n")
        lf.flush()
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(ROOT), env=full_env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            job["pid"] = proc.pid
            for line in proc.stdout:           # type: ignore[union-attr]
                lf.write(line)
                lf.flush()
            proc.wait()
            job["returncode"] = proc.returncode
            job["status"] = "done" if proc.returncode == 0 else "failed"
        except Exception as e:  # noqa: BLE001
            lf.write(f"\n[dashboard] job crashed: {e}\n")
            job["returncode"] = -1
            job["status"] = "failed"
        finally:
            job["ended"] = time.time()


def _running_for(stem: str, kinds: set[str]) -> bool:
    with JOBS_LOCK:
        return any(j["stem"] == stem and j["kind"] in kinds and j["status"] == "running"
                   for j in JOBS.values())


def _jobs_public() -> list[dict]:
    with JOBS_LOCK:
        out = []
        for j in sorted(JOBS.values(), key=lambda x: x["started"], reverse=True):
            out.append({k: j[k] for k in
                        ("id", "kind", "stem", "status", "returncode", "started", "ended")})
        return out


# ---------------------------------------------------------------- state ----------
def _read_postlog() -> dict[str, dict]:
    """stem -> {platform -> {url, ts, video_id}}"""
    out: dict[str, dict] = {}
    if not POSTLOG.exists():
        return out
    for line in POSTLOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        stem = rec.get("stem")
        plat = rec.get("platform")
        if not stem or not plat:
            continue
        out.setdefault(stem, {})[plat] = {
            "url": rec.get("url_or_note", ""),
            "ts": rec.get("ts", ""),
            "video_id": rec.get("video_id", ""),
        }
    return out


def _finfo(p: Path) -> dict | None:
    if not p.exists():
        return None
    st = p.stat()
    return {"path": str(p.relative_to(ROOT)), "mb": round(st.st_size / 1e6, 1),
            "mtime": st.st_mtime}


def _spec_card(spec_path: Path, postlog: dict) -> dict:
    stem = spec_path.stem
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        spec = {}
    hook = spec.get("hook", {}) or {}
    scenes = spec.get("scenes", []) or []

    story_html = STORY / f"{stem}.html"
    story_sum = STORY / f"{stem}.summary.json"
    story = None
    if story_html.exists():
        story = {"html": f"out/storyboards/{stem}.html", "mtime": story_html.stat().st_mtime,
                 "unresolved": None, "warnings": []}
        if story_sum.exists():
            try:
                s = json.loads(story_sum.read_text(encoding="utf-8"))
                story["unresolved"] = s.get("unresolved")
                story["warnings"] = s.get("header_warnings", []) or []
                story["scene_count"] = len(s.get("scenes", []) or [])
            except Exception:  # noqa: BLE001
                pass

    draft = _finfo(RENDERS / f"{stem}-draft.mp4")
    prod = _finfo(RENDERS / f"{stem}.mp4") or _finfo(PUBLISHED / f"{stem}.mp4")

    pub = postlog.get(stem, {})

    running = []
    with JOBS_LOCK:
        for j in JOBS.values():
            if j["stem"] == stem and j["status"] == "running":
                running.append(j["kind"])

    return {
        "stem": stem,
        "format": spec.get("format", "?"),
        "topic": spec.get("topic", ""),
        "subject": spec.get("subject", ""),
        "matchup": spec.get("matchup", []) or [],
        "duration": spec.get("target_duration_seconds"),
        "scenes": len(scenes),
        "hook": hook.get("first_frame_text", ""),
        "spoken_hook": hook.get("spoken_hook", ""),
        "youtube_title": spec.get("youtube_title", ""),
        "spec_mtime": spec_path.stat().st_mtime,
        "storyboard": story,
        "draft": draft,
        "production": prod,
        "published": pub,
        "running": running,
    }


def _topics() -> list[dict]:
    out = []
    for p in sorted(TOPICS.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        out.append({"name": p.stem, "mtime": p.stat().st_mtime,
                    "path": f"out/topics/{p.name}",
                    "bytes": p.stat().st_size})
    return out


def build_state() -> dict:
    postlog = _read_postlog()
    cards = [_spec_card(p, postlog) for p in SPECS.glob("*.json")]
    cards.sort(key=lambda c: c["spec_mtime"], reverse=True)
    published_stems = {s for s, plats in postlog.items() if "youtube" in plats}
    telemetry = {
        "specs": len(cards),
        "storyboards": sum(1 for c in cards if c["storyboard"]),
        "drafts": sum(1 for c in cards if c["draft"]),
        "productions": sum(1 for c in cards if c["production"]),
        "published": len(published_stems),
        "topics": len(list(TOPICS.glob("*.md"))),
    }
    return {"telemetry": telemetry, "cards": cards, "topics": _topics(),
            "jobs": _jobs_public(), "now": time.time()}


# ---------------------------------------------------------------- scheduled ------
def _scheduled_queue() -> dict:
    """Run `upload_youtube.py scheduled --json` and return the parsed queue (+ ET labels)."""
    import datetime as _dt

    try:
        proc = subprocess.run(
            ["uv", "run", "pipeline/upload_youtube.py", "scheduled", "--json"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        return {"items": [], "error": f"could not query schedule: {e}"}
    if proc.returncode != 0:
        return {"items": [], "error": (proc.stderr or proc.stdout or "").strip()[:300]}
    # The script prints one JSON line; tolerate stray lines by taking the last non-empty one.
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.strip()), "[]")
    try:
        items = json.loads(line)
    except json.JSONDecodeError:
        return {"items": [], "error": "unexpected output from scheduler"}
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(DEFAULT_TZ)
        for it in items:
            when = _dt.datetime.fromisoformat(it["publish_at"].replace("Z", "+00:00")).astimezone(zone)
            it["local"] = when.strftime("%a %b %d, %-I:%M %p %Z")
    except Exception:
        pass
    return {"items": items, "tz": DEFAULT_TZ}


# ---------------------------------------------------------------- actions --------
def start_action(payload: dict) -> dict:
    action = payload.get("action")
    stem = payload.get("stem", "")
    spec = SPECS / f"{stem}.json"

    if action in ("storyboard", "draft", "production", "publish") and not spec.exists():
        return {"error": f"spec not found: out/specs/{stem}.json"}

    if action == "storyboard":
        if _running_for(stem, {"storyboard"}):
            return {"error": "storyboard already running for this video"}
        jid = _new_job("storyboard", stem, ["bash", "pipeline/storyboard.sh", f"out/specs/{stem}.json"])
        return {"job": jid}

    if action == "draft":
        if _running_for(stem, {"draft", "production"}):
            return {"error": "a render is already running for this video"}
        jid = _new_job("draft", stem, ["bash", "pipeline/make_video.sh", f"out/specs/{stem}.json"])
        return {"job": jid}

    if action == "production":
        if _running_for(stem, {"draft", "production"}):
            return {"error": "a render is already running for this video"}
        jid = _new_job("production", stem, ["bash", "pipeline/make_video.sh", f"out/specs/{stem}.json"],
                       env={"TTV_PRODUCTION": "1"})
        return {"job": jid}

    if action == "publish":
        # refuse drafts; require a production render
        mp4 = None
        for cand in (PUBLISHED / f"{stem}.mp4", RENDERS / f"{stem}.mp4"):
            if cand.exists():
                mp4 = cand
                break
        if mp4 is None:
            return {"error": "no production MP4 found — run a Production render first "
                             "(drafts use free Piper VO and can't be published)"}
        if _running_for(stem, {"publish"}):
            return {"error": "publish already running for this video"}
        vis = payload.get("visibility", "public")
        if vis not in ("public", "unlisted", "private"):
            vis = "public"
        tz = payload.get("tz") or DEFAULT_TZ
        # Friendly time (e.g. "tomorrow 9am") preferred; legacy ISO publish_at still accepted.
        when = payload.get("publish_when") or payload.get("publish_at")
        if when:
            cmd = ["uv", "run", "pipeline/upload_youtube.py", "schedule",
                   f"out/specs/{stem}.json", str(mp4.relative_to(ROOT)), when, "--tz", tz]
        else:
            cmd = ["uv", "run", "pipeline/upload_youtube.py", "upload",
                   f"out/specs/{stem}.json", str(mp4.relative_to(ROOT)), "--visibility", vis]
        jid = _new_job("publish", stem, cmd)
        return {"job": jid}

    if action == "cancel_schedule":
        target = payload.get("target") or stem
        if not target:
            return {"error": "no target for cancel"}
        cmd = ["uv", "run", "pipeline/upload_youtube.py", "cancel", target]
        if payload.get("now"):
            cmd.append("--now")
        jid = _new_job("cancel_schedule", target, cmd)
        return {"job": jid}

    if action == "reschedule":
        target = payload.get("target") or stem
        when = payload.get("publish_when")
        if not target or not when:
            return {"error": "reschedule needs a target and a time"}
        tz = payload.get("tz") or DEFAULT_TZ
        cmd = ["uv", "run", "pipeline/upload_youtube.py", "reschedule", target, when, "--tz", tz]
        jid = _new_job("reschedule", target, cmd)
        return {"job": jid}

    if action == "gather_topics":
        # DETERMINISTIC viral-topic signal — no Claude, no tokens. Runs the outlier
        # engine (YouTube Data API) and tees the ranked feed into a dated topic brief.
        if _running_for("outlier-feed", {"gather_topics"}):
            return {"error": "outlier feed already running"}
        ts = time.strftime("%Y-%m-%d_%H%M%S", time.localtime())
        outfile = TOPICS / f"outlier-feed-{ts}.md"
        rel = json.dumps(str(outfile.relative_to(ROOT)))
        header = (f"echo '# Outlier feed — {ts}' > {rel}; "
                  f"echo '_Deterministic viral signal (outlier_ingest.py). "
                  f"Pair with /find-topics for the grounded synthesis._' >> {rel}; "
                  f"echo '' >> {rel}; echo '```' >> {rel}")
        body = f"uv run pipeline/outlier_ingest.py 2>&1 | tee -a {rel}"
        footer = f"echo '```' >> {rel}"
        sh = f"{header}; {body}; {footer}"
        jid = _new_job("gather_topics", "outlier-feed", ["bash", "-lc", sh])
        return {"job": jid}

    return {"error": f"unknown action: {action}"}


# ---------------------------------------------------------------- http -----------
class Handler(BaseHTTPRequestHandler):
    server_version = "TTVMissionControl/1.0"

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_file(self, rel: str):
        # static files rooted at the repo (with traversal protection)
        target = (ROOT / rel).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            self._send(403, {"error": "forbidden"})
            return
        if not target.is_file():
            self._send(404, {"error": "not found", "path": rel})
            return
        ctype = {
            ".html": "text/html", ".mp4": "video/mp4", ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
            ".json": "application/json", ".md": "text/markdown", ".css": "text/css",
            ".js": "application/javascript", ".svg": "image/svg+xml",
        }.get(target.suffix.lower(), "application/octet-stream")
        # Range support (video scrubbing)
        size = target.stat().st_size
        rng = self.headers.get("Range")
        if rng and ctype == "video/mp4":
            m = re.match(r"bytes=(\d+)-(\d*)", rng)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                length = end - start + 1
                with open(target, "rb") as f:
                    f.seek(start)
                    chunk = f.read(length)
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                self.end_headers()
                try:
                    self.wfile.write(chunk)
                except BrokenPipeError:
                    pass
                return
        with open(target, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        if path == "/" or path == "/index.html":
            self._serve_file("pipeline/dashboard/index.html")
            return
        if path == "/api/state":
            self._send(200, build_state())
            return
        if path == "/api/scheduled":
            # Synchronous, quick (one Data API call) — list videos queued to publish.
            self._send(200, _scheduled_queue())
            return
        if path == "/api/job":
            qs = parse_qs(u.query)
            jid = qs.get("id", [""])[0]
            offset = int(qs.get("offset", ["0"])[0])
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job:
                self._send(404, {"error": "no such job"})
                return
            text = ""
            try:
                with open(job["log"], "r", encoding="utf-8", errors="replace") as f:
                    f.seek(offset)
                    text = f.read()
            except FileNotFoundError:
                pass
            self._send(200, {"id": jid, "status": job["status"],
                             "returncode": job["returncode"], "kind": job["kind"],
                             "stem": job["stem"], "offset": offset + len(text.encode()),
                             "text": text})
            return
        # static (storyboards, renders, published mp4s, images)
        self._serve_file(path.lstrip("/"))

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/action":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "bad json"})
            return
        self._send(200, start_action(payload))


def main():
    if not shutil.which("uv"):
        print("[warn] `uv` not on PATH — pipeline actions need it (see CLAUDE.md tooling)")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  TikiTakaFootyTV — Mission Control")
    print(f"  → http://localhost:{PORT}\n")
    print(f"  repo: {ROOT}")
    print(f"  (Ctrl-C to stop)\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye")


if __name__ == "__main__":
    main()
