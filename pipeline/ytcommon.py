"""
Shared YouTube-script helpers: the two-step headless OAuth consent flow + video-id parsing.

The consent flow (auth / auth-finish / creds / service) was byte-for-byte duplicated between
youtube_analytics.py (read-only analytics scope) and upload_youtube.py (upload+force-ssl scope);
`YTOAuth` is the one copy, configured per-script. `uv run pipeline/<x>.py` puts pipeline/ on
sys.path[0], so `from ytcommon import ...` resolves. Google libs are imported lazily inside the
methods, so importing this module stays cheap and dependency-free.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SECRETS = Path(__file__).resolve().parent / ".secrets"
REDIRECT_URI = "http://localhost:8765/"  # desktop clients allow any loopback port
DEFAULT_CLIENT = SECRETS / "yt_oauth_client.json"


def video_id(s: str) -> str | None:
    """Accept a raw id, a /watch?v=, a youtu.be/, or a /shorts/ URL. None if unparseable."""
    s = (s or "").strip()
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[A-Za-z0-9_-]{11}", s) else None


def _relax_env() -> None:
    # allow the http loopback redirect + tolerate Google reordering the returned scope string
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class YTOAuth:
    """One headless two-step OAuth flow, bound to a script's scopes + token/pending files."""

    def __init__(self, *, scopes: list[str], token_env: str, default_token: Path,
                 pending: Path, script: str, success_hint: str, token_label: str = "Token"):
        self.scopes = scopes
        self.token_env = token_env
        self.default_token = default_token
        self.pending = pending
        self.script = script            # e.g. "upload_youtube.py" — used in the printed run-commands
        self.success_hint = success_hint
        self.token_label = token_label

    def _token_path(self) -> Path:
        return Path(os.getenv(self.token_env, str(self.default_token)))

    def _client_path(self) -> Path:
        p = Path(os.getenv("YT_OAUTH_CLIENT", str(DEFAULT_CLIENT)))
        if not p.exists():
            sys.exit(
                f"Missing OAuth client JSON at {p}.\n"
                "Download it from Google Cloud (Desktop app OAuth client) and save it there\n"
                "(or reuse the analytics one). See the setup steps at the top of the script."
            )
        return p

    def creds(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        token_path = self._token_path()
        if not token_path.exists():
            sys.exit(f"Not authorized yet. Run:  uv run pipeline/{self.script} auth")
        creds = Credentials.from_authorized_user_file(str(token_path), self.scopes)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        return creds

    def service(self, api: str, version: str):
        from googleapiclient.discovery import build

        return build(api, version, credentials=self.creds(), cache_discovery=False)

    def do_auth(self) -> None:
        """Step 1: print the consent URL (desktop client uses its client_secret, no PKCE)."""
        from google_auth_oauthlib.flow import Flow

        client_path = self._client_path()
        SECRETS.mkdir(parents=True, exist_ok=True)
        _relax_env()

        flow = Flow.from_client_secrets_file(
            str(client_path), scopes=self.scopes, autogenerate_code_verifier=False)
        flow.redirect_uri = REDIRECT_URI
        auth_url, _state = flow.authorization_url(access_type="offline", prompt="consent")
        self.pending.write_text(json.dumps({"client": str(client_path)}))

        print("\nStep 1 — open this URL, sign in with the CHANNEL's Google account, and authorize:\n")
        print(auth_url)
        print("\n  (If an 'unverified app' screen appears: Advanced > continue — it's your own app.)")
        print("\nStep 2 — the browser redirects to a localhost page that WON'T load")
        print("         (http://localhost:8765/?code=...  — 'site can't be reached'). That's expected.")
        print("         Copy the FULL address-bar URL and run this, with the URL in quotes:\n")
        print(f'   uv run pipeline/{self.script} auth-finish "<paste the full URL>"\n')

    def do_auth_finish(self, resp: str) -> None:
        """Step 2: exchange the pasted redirect URL (or bare code) for a token."""
        from urllib.parse import parse_qs, unquote, urlparse

        from google_auth_oauthlib.flow import Flow

        if not self.pending.exists():
            sys.exit("No pending auth. Run `auth` first to get the URL.")
        p = json.loads(self.pending.read_text())
        _relax_env()

        resp = resp.strip()
        code = (parse_qs(urlparse(resp).query).get("code") or [None])[0] if "code=" in resp else resp
        if not code:
            sys.exit("Could not find an auth code in that input.")
        code = unquote(code)

        flow = Flow.from_client_secrets_file(
            p["client"], scopes=self.scopes, autogenerate_code_verifier=False)
        flow.redirect_uri = REDIRECT_URI
        flow.fetch_token(code=code)

        token_path = self._token_path()
        token_path.write_text(flow.credentials.to_json())
        self.pending.unlink(missing_ok=True)
        print(f"Authorized.  {self.token_label} saved to {token_path}")
        print(self.success_hint)


if __name__ == "__main__":
    assert video_id("https://youtu.be/abcdefghijk") == "abcdefghijk"
    assert video_id("https://www.youtube.com/watch?v=ABCDEFGHIJK&t=1") == "ABCDEFGHIJK"
    assert video_id("https://youtube.com/shorts/12345678901") == "12345678901"
    assert video_id("abcdefghijk") == "abcdefghijk"
    assert video_id("not a video") is None and video_id("") is None
    print("ytcommon.py self-check ok")
