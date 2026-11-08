#!/usr/bin/env bash
# Install ShiftHub's n8n as a systemd user service so it starts with WSL and
# keeps running after you close the terminal.
#
# Usage:  bash scripts/install-n8n-service.sh
set -euo pipefail

N8N_BIN="$(command -v n8n || true)"
if [ -z "$N8N_BIN" ]; then
  echo "error: n8n is not on PATH. Install it first: npm install -g n8n" >&2
  exit 1
fi

UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/shifthub-n8n.service"
mkdir -p "$UNIT_DIR"

cat > "$UNIT" <<EOF
[Unit]
Description=ShiftHub n8n (local automation server)
After=network.target

[Service]
Type=simple
WorkingDirectory=$HOME/n8n
Environment=PATH=$(dirname "$N8N_BIN"):/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=TZ=Africa/Lagos
Environment=GENERIC_TIMEZONE=Africa/Lagos
Environment=N8N_SECURE_COOKIE=false
ExecStart=$N8N_BIN start
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now shifthub-n8n
loginctl enable-linger "$USER" 2>/dev/null || true

echo "Installed $UNIT"
echo "Open http://localhost:5678 — it will now start automatically with WSL."
echo "Logs: journalctl --user -u shifthub-n8n -f"
