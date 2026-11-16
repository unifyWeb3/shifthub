#!/usr/bin/env python3
"""
Keep the ShiftHub public URL alive and pointing at the right place.

Why this exists
---------------
The public URL is a Cloudflare *quick* tunnel. Quick tunnels are ephemeral:
the hostname is only valid while that particular cloudflared registration is
alive, and Cloudflare drops the registration after a couple of hours (the
symptom in the journal is `Register tunnel error ... Unauthorized: Tunnel not
found`). cloudflared then retries forever against a registration the server
has already forgotten, so systemd's `Restart=always` never fires and the URL
is dead until somebody restarts the unit by hand.

When the URL changes, five things have to move together or the product breaks
in a different way:

  1. the n8n systemd unit  (N8N_WEBHOOK_URL / WEBHOOK_URL)
  2. Settings.publicBaseUrl in Google Sheets - the one-tap confirm link in
     every reminder email
  3. webapp/n8n-url.txt on GitHub - the Vercel app reads it at request time
  4. the Telegram webhook registration - Telegram posts updates to a fixed
     URL, and a `persisted` n8n trigger does NOT re-register on restart, so
     the bot goes deaf until the workflow is unpublished/re-published
  5. a restart of n8n itself, so it picks up the new N8N_WEBHOOK_URL

This script does all five, and it is safe to run at any time: if the tunnel is
already healthy and the URL has not changed, it does nothing.

Usage:
    python3 scripts/heal-tunnel.py            # heal if needed
    python3 scripts/heal-tunnel.py --check    # report only, change nothing
    python3 scripts/heal-tunnel.py --force    # re-sync even if healthy
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

N8N_DIR = Path.home() / ".n8n"
DB = N8N_DIR / "database.sqlite"
N8N_BIN = os.environ.get("N8N_BIN") or str(Path.home() / ".local/bin/n8n")

REPO = Path(__file__).resolve().parent.parent
N8N_UNIT = Path.home() / ".config/systemd/user/shifthub-n8n.service"
TUNNEL_UNIT = Path.home() / ".config/systemd/user/shifthub-tunnel.service"
TUNNEL_LOG = Path.home() / ".config/shifthub/tunnel.log"
URL_FILE = REPO / "webapp" / "n8n-url.txt"

TUNNEL_SERVICE = "shifthub-tunnel"
N8N_SERVICE = "shifthub-n8n"

TELEGRAM_WORKFLOW_NAME = "ShiftHub — 04 · Telegram YES Confirmation"
TELEGRAM_WEBHOOK_PATH = "/webhook/shifthub-telegram/webhook"

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
HEALTH_PATH = "/webhook/shifthub-dashboard"

TIMEOUT = 40


def log(message: str) -> None:
    print(message, flush=True)


def fail(message: str) -> None:
    log(f"error: {message}")
    raise SystemExit(1)


# --------------------------------------------------------------------------
# tunnel
# --------------------------------------------------------------------------

def tunnel_log_url() -> str | None:
    """The most recent URL cloudflared printed in its log."""
    if not TUNNEL_LOG.is_file():
        return None
    urls = URL_RE.findall(TUNNEL_LOG.read_text(encoding="utf-8", errors="replace"))
    return urls[-1] if urls else None


def unit_env_url() -> str | None:
    """The URL the n8n unit is currently configured with."""
    if not N8N_UNIT.is_file():
        return None
    match = re.search(r"^Environment=N8N_WEBHOOK_URL=(\S+)$",
                      N8N_UNIT.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def probe(url: str) -> int | None:
    """HTTP status for a real n8n webhook through the tunnel, or None."""
    try:
        request = urllib.request.Request(url.rstrip("/") + HEALTH_PATH,
                                         headers={"User-Agent": "ShiftHub-heal/1.0"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return None


def service_state(unit: str) -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", unit],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def restart_tunnel() -> str:
    """Restart cloudflared and wait for the NEW hostname it prints."""
    before = tunnel_log_url()
    log(f"  restarting {TUNNEL_SERVICE} (was {before})")
    subprocess.run(["systemctl", "--user", "restart", TUNNEL_SERVICE], check=False)

    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(4)
        current = tunnel_log_url()
        if current and current != before:
            # give the tunnel a moment to finish registering
            for _ in range(6):
                time.sleep(3)
                if probe(current) == 200:
                    return current
            return current
    fail("the tunnel did not hand out a new URL within 90s")


# --------------------------------------------------------------------------
# sync targets
# --------------------------------------------------------------------------

def update_n8n_unit(url: str) -> bool:
    if not N8N_UNIT.is_file():
        fail(f"no systemd unit at {N8N_UNIT}")
    text = N8N_UNIT.read_text(encoding="utf-8")
    changed = False
    for key in ("N8N_WEBHOOK_URL", "WEBHOOK_URL"):
        pattern = re.compile(rf"^Environment={key}=.*$", re.MULTILINE)
        if pattern.search(text):
            new_text, count = pattern.subn(f"Environment={key}={url}", text)
            if count:
                text = new_text
                changed = True
        else:
            text = text.replace("ExecStart=",
                                f"Environment={key}={url}\nExecStart=", 1)
            changed = True
    if changed:
        N8N_UNIT.write_text(text, encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    return changed


def set_public_base_url(url: str) -> bool:
    script = REPO / "scripts" / "set-setting.py"
    result = subprocess.run([sys.executable, str(script), "publicBaseUrl", url],
                            capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        log(output[-900:])
        return False
    log(f"  Settings.publicBaseUrl = {url}")
    return True


def publish_url_file(url: str) -> bool:
    """Write webapp/n8n-url.txt and push it - the Vercel app reads it live."""
    previous = URL_FILE.read_text(encoding="utf-8").strip() if URL_FILE.is_file() else ""
    if previous == url:
        log("  webapp/n8n-url.txt already current")
        return True
    URL_FILE.write_text(url + "\n", encoding="utf-8")
    log(f"  wrote webapp/n8n-url.txt = {url}")
    subprocess.run(["git", "-C", str(REPO), "add", "webapp/n8n-url.txt"], check=False)
    commit = subprocess.run(
        ["git", "-C", str(REPO), "commit", "-m",
         "chore: point the web app at the current n8n public URL"],
        capture_output=True, text=True)
    if commit.returncode != 0:
        log(f"  git commit failed: {commit.stdout.strip()[-300:]} {commit.stderr.strip()[-300:]}")
        return False
    push = subprocess.run(["git", "-C", str(REPO), "push", "origin", "main"],
                          capture_output=True, text=True)
    if push.returncode != 0:
        log(f"  git push failed: {(push.stdout + push.stderr).strip()[-300:]}")
        return False
    log("  pushed - the Vercel app picks the URL up without a redeploy")
    return True


# --------------------------------------------------------------------------
# telegram webhook
# --------------------------------------------------------------------------

def decrypt_legacy(blob: str, key: str) -> dict:
    raw = base64.b64decode(blob)
    if raw[:8] != b"Salted__":
        raise ValueError("unexpected credential format")
    salt, data = raw[8:16], raw[16:]
    material, prev = b"", b""
    while len(material) < 48:
        digest = hashlib.md5(prev + key.encode("latin-1") + salt).digest()
        material += digest
        prev = digest
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    decryptor = Cipher(algorithms.AES(material[:32]),
                       modes.CBC(material[32:48])).decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    return json.loads(plain[:-plain[-1]].decode("utf-8"))


def telegram_token() -> str:
    config = json.loads((N8N_DIR / "config").read_text())
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "select data from credentials_entity where type = 'telegramApi' limit 1"
    ).fetchone()
    conn.close()
    if not row:
        fail("no telegramApi credential in this n8n instance")
    credential = decrypt_legacy(row[0], config["encryptionKey"])
    token = credential.get("accessToken") or credential.get("token")
    if not token:
        fail("the telegram credential has no token")
    return token


def telegram_api(token: str, method: str, params: dict | None = None) -> tuple[int, dict]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            body = {}
        return exc.code, body
    except Exception as exc:
        return 0, {"error": str(exc)}


def telegram_webhook_url(token: str) -> str | None:
    status, body = telegram_api(token, "getWebhookInfo")
    if status != 200:
        return None
    return body.get("result", {}).get("url")


def telegram_workflow_id() -> str:
    conn = sqlite3.connect(DB)
    row = conn.execute("select id from workflow_entity where name = ?",
                       (TELEGRAM_WORKFLOW_NAME,)).fetchone()
    conn.close()
    if not row:
        fail(f"workflow '{TELEGRAM_WORKFLOW_NAME}' is not in this n8n instance")
    return row[0]


def reregister_telegram(url: str) -> bool:
    """
    Point Telegram at the new hostname.

    n8n's telegram trigger registers its webhook when the workflow is
    activated. A `persisted` trigger is restored on restart WITHOUT
    re-registering, so the bot keeps posting to the dead hostname until the
    workflow is unpublished and published again.
    """
    token = telegram_token()
    expected = url.rstrip("/") + TELEGRAM_WEBHOOK_PATH
    current = telegram_webhook_url(token)
    if current == expected:
        log(f"  telegram webhook already points at the current URL")
        return True

    workflow_id = telegram_workflow_id()
    log(f"  telegram webhook is {current or '<unset>'}; re-registering for {workflow_id}")
    subprocess.run([N8N_BIN, "unpublish:workflow", f"--id={workflow_id}"],
                   capture_output=True, text=True, check=False)
    time.sleep(3)
    subprocess.run([N8N_BIN, "publish:workflow", f"--id={workflow_id}"],
                   capture_output=True, text=True, check=False)
    subprocess.run(["systemctl", "--user", "restart", N8N_SERVICE], check=False)

    for _ in range(20):
        time.sleep(5)
        current = telegram_webhook_url(token)
        if current == expected:
            log("  telegram webhook re-registered")
            return True
    log(f"  WARNING: telegram webhook is {current or '<unset>'}, expected {expected}")
    return False


# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="report the current state without changing anything")
    parser.add_argument("--force", action="store_true",
                        help="re-sync everything even if the tunnel looks healthy")
    parser.add_argument("--no-telegram", action="store_true",
                        help="skip the Telegram webhook re-registration")
    args = parser.parse_args()

    log_url = tunnel_log_url()
    unit_url = unit_env_url()
    file_url = URL_FILE.read_text(encoding="utf-8").strip() if URL_FILE.is_file() else ""
    status = probe(unit_url) if unit_url else None

    log(f"tunnel log URL   : {log_url}")
    log(f"n8n unit URL     : {unit_url}")
    log(f"webapp URL file  : {file_url}")
    log(f"tunnel health    : HTTP {status}")
    log(f"tunnel service   : {service_state(TUNNEL_SERVICE)}")
    log(f"n8n service      : {service_state(N8N_SERVICE)}")

    healthy = status == 200
    consistent = (log_url and unit_url and file_url
                  and log_url == unit_url == file_url)

    url = unit_url or log_url
    telegram_ok = True
    if url and not args.no_telegram:
        token = telegram_token()
        expected = url.rstrip("/") + TELEGRAM_WEBHOOK_PATH
        current = telegram_webhook_url(token)
        telegram_ok = current == expected
        log(f"telegram webhook : {current or '<unset>'}")
        log(f"                   {'ok' if telegram_ok else f'STALE (expected {expected})'}")

    if args.check:
        log("")
        log(f"healthy={healthy} consistent={consistent} telegram_ok={telegram_ok}")
        return

    if not healthy or not consistent or not telegram_ok:
        log("")
        log("healing...")
        if not healthy:
            url = restart_tunnel()
            log(f"  new tunnel URL: {url}")
        elif log_url and log_url != url:
            # the tunnel handed out a different hostname than the one in use
            log(f"  tunnel log URL differs from the configured one; adopting {log_url}")
            url = log_url

        log("1. n8n systemd unit")
        if update_n8n_unit(url):
            log(f"  updated {N8N_UNIT}")
            subprocess.run(["systemctl", "--user", "restart", N8N_SERVICE], check=False)
            for _ in range(30):
                time.sleep(2)
                if service_state(N8N_SERVICE) == "active":
                    break
            log(f"  n8n is {service_state(N8N_SERVICE)}")
        else:
            log("  already current")

        log("2. Settings.publicBaseUrl")
        set_public_base_url(url)

        log("3. webapp/n8n-url.txt")
        publish_url_file(url)

        if not args.no_telegram:
            log("4. telegram webhook")
            reregister_telegram(url)
    elif args.force:
        log("")
        log("forced re-sync...")
        update_n8n_unit(url)
        set_public_base_url(url)
        publish_url_file(url)
        if not args.no_telegram:
            reregister_telegram(url)
    else:
        log("")
        log("nothing to do - the tunnel is healthy and the URL is consistent")

    final = probe(url)
    log("")
    log(f"final health check: HTTP {final} for {url}")
    if final != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
