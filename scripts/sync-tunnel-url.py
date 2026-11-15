#!/usr/bin/env python3
"""
Keep the public n8n URL in sync everywhere it is used.

A Cloudflare *quick* tunnel hands out a new random URL every time it restarts,
so the URL has to be pushed into four places:

  1. the n8n systemd unit  (N8N_WEBHOOK_URL / WEBHOOK_URL)
  2. the Settings tab in Google Sheets (publicBaseUrl) - used to build the
     one-tap confirmation link inside the reminder e-mails
  3. workflow 13 in n8n (the maintenance workflow that writes #2)
  4. Vercel (N8N_WEBHOOK_BASE) - the web app proxies to this URL

Steps 1-3 are done here. Step 4 is printed at the end (set it in the Vercel
dashboard: project `shifthub`, variable `N8N_WEBHOOK_BASE`).

Usage:
    python3 scripts/sync-tunnel-url.py [--url https://....trycloudflare.com] [--dry-run]
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

UNIT = Path.home() / ".config/systemd/user/shifthub-n8n.service"
TUNNEL_LOG = Path.home() / ".config/shifthub/tunnel.log"
SERVICE = "shifthub-n8n"
URL_FILE = Path(__file__).resolve().parent.parent / "webapp" / "n8n-url.txt"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def current_tunnel_url() -> str:
    if not TUNNEL_LOG.is_file():
        fail(f"no tunnel log at {TUNNEL_LOG}")
    urls = URL_RE.findall(TUNNEL_LOG.read_text(encoding="utf-8", errors="replace"))
    if not urls:
        fail(f"no trycloudflare URL in {TUNNEL_LOG}")
    return urls[-1]


def service_state() -> str:
    result = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def service(action: str) -> None:
    subprocess.run(["systemctl", "--user", action, SERVICE], check=False)


def update_unit(url: str, dry_run: bool) -> bool:
    if not UNIT.is_file():
        fail(f"no systemd unit at {UNIT}")
    text = UNIT.read_text(encoding="utf-8")
    changed = False
    for key in ("N8N_WEBHOOK_URL", "WEBHOOK_URL"):
        pattern = re.compile(rf"^Environment={key}=.*$", re.MULTILINE)
        if pattern.search(text):
            new_text, count = pattern.subn(f"Environment={key}={url}", text)
            if count:
                text = new_text
                changed = True
        else:
            text = text.replace(
                "ExecStart=",
                f"Environment={key}={url}\nExecStart=",
                1,
            )
            changed = True
    if changed and not dry_run:
        UNIT.write_text(text, encoding="utf-8")
    return changed


def set_public_base_url(url: str, dry_run: bool) -> bool:
    """Write publicBaseUrl into the Settings tab via the maintenance workflow."""
    script = Path(__file__).resolve().parent / "set-setting.py"
    if dry_run:
        print(f"   would write Settings.publicBaseUrl = {url}")
        return True
    result = subprocess.run([sys.executable, str(script), "publicBaseUrl", url],
                            capture_output=True, text=True)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        print(output[-1200:])
        return False
    print(output)
    return True


def publish_url_file(url: str, dry_run: bool, publish: bool) -> None:
    """Write the URL to webapp/n8n-url.txt - the web app reads it at request time."""
    current = URL_FILE.read_text(encoding="utf-8").strip() if URL_FILE.is_file() else ""
    if current == url:
        print(f"   webapp/n8n-url.txt is already up to date")
        return
    if dry_run:
        print(f"   would write {URL_FILE} = {url}")
        return
    URL_FILE.write_text(url + "\n", encoding="utf-8")
    print(f"   wrote {URL_FILE} = {url}")
    if publish:
        subprocess.run(["git", "-C", str(URL_FILE.parent.parent), "add", "webapp/n8n-url.txt"],
                       check=False)
        subprocess.run(["git", "-C", str(URL_FILE.parent.parent), "commit", "-m",
                        "chore: point the web app at the current n8n public URL"], check=False)
        subprocess.run(["git", "-C", str(URL_FILE.parent.parent), "push", "origin", "main"],
                       check=False)
        print("   committed and pushed (Vercel redeploys automatically)")
    else:
        print("   commit and push this file so the web app picks it up "
              "(git add webapp/n8n-url.txt && git commit -m 'chore: n8n public URL' && git push)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="explicit tunnel URL (default: read from the tunnel log)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish", action="store_true",
                        help="commit and push webapp/n8n-url.txt so the web app picks the URL up")
    args = parser.parse_args()

    url = args.url or current_tunnel_url()
    print(f"public n8n URL: {url}\n")

    print("1. systemd unit")
    changed = update_unit(url, args.dry_run)
    print(f"   {'would update' if args.dry_run and changed else 'updated'}: {UNIT}")
    if not args.dry_run:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        print("   restarting n8n...")
        service("restart")
        for _ in range(30):
            time.sleep(2)
            if service_state() == "active":
                break
        print(f"   n8n is {service_state()}")
        health = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{url}/healthz"],
            capture_output=True, text=True)
        print(f"   tunnel /healthz -> {health.stdout.strip()}")

    print("\n2. n8n maintenance workflow (13) -> Settings.publicBaseUrl")
    ok = set_public_base_url(url, args.dry_run)
    print(f"   Settings update: {'ok' if ok else 'FAILED'}")

    print("\n3. web app (webapp/n8n-url.txt)")
    publish_url_file(url, args.dry_run, args.publish)

    print("\n4. Vercel (optional)")
    print(f"   the web app reads the URL from the file above, so no redeploy is needed.")
    print(f"   if you prefer an environment variable, set N8N_WEBHOOK_BASE={url} "
          f"in project 'shifthub' (team oxunify).")


if __name__ == "__main__":
    main()
