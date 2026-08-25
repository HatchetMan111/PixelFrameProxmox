#!/usr/bin/env bash
#
# PixelFrame – Proxmox LXC Installer (Community-Scripts-Stil)
# https://github.com/HatchetMan111/PixelFrameProxmox
#
# Ausführung auf dem Proxmox-Host:
#   bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/PixelFrameProxmox/main/install/pixelframe.sh)"
#
# Optionale Variablen (per ENV vor dem Aufruf setzen):
#   CTID, CT_HOSTNAME, DISK_GB, RAM_MB, CORES, BRIDGE, STORAGE, TEMPLATE_STORAGE, PORT, DEBUG
set -euo pipefail

# ---------- Variablen ----------
# Hinweis: absichtlich NICHT $HOSTNAME verwendet – das ist eine eingebaute
# Bash-Variable mit dem echten Hostnamen des Proxmox-Hosts, ${HOSTNAME:-...}
# würde also nie den Default greifen lassen.
CTID="${CTID:-200}"
CT_HOSTNAME="${CT_HOSTNAME:-pixelframe}"
DISK_GB="${DISK_GB:-2}"
RAM_MB="${RAM_MB:-512}"
CORES="${CORES:-1}"
BRIDGE="${BRIDGE:-vmbr0}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
PORT="${PORT:-8090}"
DEBIAN_TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
REPO_URL="https://github.com/HatchetMan111/PixelFrameProxmox.git"
DEBUG="${DEBUG:-0}"

[[ "$DEBUG" == "1" ]] && set -x

# ---------- Fehler-Trap: immer die vollständige Kette ausgeben ----------
on_error() {
  local rc=$?
  echo >&2
  echo "❌ FEHLER (Exit-Code $rc) in Zeile $LINENO" >&2
  echo "   Letzter Befehl: $BASH_COMMAND" >&2
  echo "   → Für ein vollständiges bash -x Log erneut mit DEBUG=1 ausführen:" >&2
  echo "     DEBUG=1 bash -c \"\$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/PixelFrameProxmox/main/install/pixelframe.sh)\"" >&2
  if pct status "$CTID" &>/dev/null; then
    echo >&2
    echo "   Journal des Containers (letzte 50 Zeilen, falls Service existiert):" >&2
    pct exec "$CTID" -- journalctl -u pixelframe --no-pager -n 50 2>&1 | tail -n 50 >&2 || true
  fi
  exit "$rc"
}
trap on_error ERR

log() { echo -e "\033[1;33m[PixelFrame]\033[0m $*"; }

# ---------- Voraussetzungen ----------
if [[ $EUID -ne 0 ]]; then
  echo "Bitte als root auf dem Proxmox-Host ausführen." >&2
  exit 1
fi
if ! command -v pct &>/dev/null; then
  echo "Dieses Skript muss auf einem Proxmox-VE-Host laufen (Befehl 'pct' nicht gefunden)." >&2
  exit 1
fi

# ---------- Template sicherstellen ----------
log "Prüfe Debian-12-LXC-Template..."
if ! pveam list "$TEMPLATE_STORAGE" 2>/dev/null | grep -q "$DEBIAN_TEMPLATE"; then
  log "Lade Template herunter (${DEBIAN_TEMPLATE})..."
  pveam update >/dev/null
  pveam download "$TEMPLATE_STORAGE" "$DEBIAN_TEMPLATE"
fi

# ---------- Container erstellen (idempotent) ----------
if pct status "$CTID" &>/dev/null; then
  log "Container $CTID existiert bereits – überspringe pct create."
else
  log "Erstelle LXC-Container $CTID (${CORES} vCPU, ${RAM_MB}MB RAM, ${DISK_GB}GB Disk)..."
  pct create "$CTID" "${TEMPLATE_STORAGE}:vztmpl/${DEBIAN_TEMPLATE}" \
    --hostname "$CT_HOSTNAME" \
    --cores "$CORES" \
    --memory "$RAM_MB" \
    --swap 512 \
    --rootfs "${STORAGE}:${DISK_GB}" \
    --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
    --onboot 1 \
    --unprivileged 1 \
    --features nesting=1
fi

log "Starte Container..."
pct start "$CTID" 2>/dev/null || true

log "Warte auf Netzwerk im Container..."
for i in $(seq 1 30); do
  if pct exec "$CTID" -- getent hosts deb.debian.org &>/dev/null; then
    break
  fi
  sleep 2
  if [[ "$i" == 30 ]]; then
    echo "❌ Container hat nach 60s kein funktionierendes Netzwerk." >&2
    exit 1
  fi
done

# ---------- App installieren ----------
log "Installiere Systempakete im Container..."
pct exec "$CTID" -- bash -c "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git python3-venv python3-pip curl ufw"

log "Klone Repository ($REPO_URL)..."
pct exec "$CTID" -- bash -c "rm -rf /opt/pixelframe && git clone --depth 1 '$REPO_URL' /opt/pixelframe"

log "Erstelle virtuelle Umgebung und installiere Python-Pakete..."
pct exec "$CTID" -- bash -c "cd /opt/pixelframe && python3 -m venv venv && ./venv/bin/pip install -q --upgrade pip && ./venv/bin/pip install -q -r requirements.txt"

log "Lege Bilder-Verzeichnis an..."
pct exec "$CTID" -- bash -c "mkdir -p /opt/pixelframe/data/images"

log "Installiere systemd-Service auf Port ${PORT}..."
pct exec "$CTID" -- bash -c "cp /opt/pixelframe/deploy/pixelframe.service /etc/systemd/system/pixelframe.service && sed -i 's/__PORT__/${PORT}/' /etc/systemd/system/pixelframe.service"
pct exec "$CTID" -- bash -c "systemctl daemon-reload && systemctl enable --now pixelframe"

log "Öffne Port ${PORT} in der Container-Firewall (ufw)..."
pct exec "$CTID" -- bash -c "ufw allow ${PORT}/tcp >/dev/null 2>&1 || true"

# ---------- Verifikation ----------
log "Prüfe Service-Status..."
sleep 2
if ! pct exec "$CTID" -- systemctl is-active --quiet pixelframe; then
  echo "❌ Service pixelframe läuft nicht. Vollständiges Log:" >&2
  pct exec "$CTID" -- journalctl -u pixelframe --no-pager -n 80 >&2
  exit 1
fi
log "✅ Service aktiv."

log "Prüfe Web-UI (HTTP)..."
if ! pct exec "$CTID" -- curl -sf "http://localhost:${PORT}/frame" -o /dev/null; then
  echo "❌ Web-UI antwortet nicht auf Port ${PORT}. Log:" >&2
  pct exec "$CTID" -- journalctl -u pixelframe --no-pager -n 80 >&2
  exit 1
fi
log "✅ Web-UI erreichbar."

CTIP=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')

echo
echo "=========================================================="
echo " PixelFrame erfolgreich installiert (Container $CTID)"
echo
echo "   Upload:  http://${CTIP}:${PORT}/upload"
echo "   Diashow: http://${CTIP}:${PORT}/frame?interval=8&shuffle=1"
echo
echo " Tipp fürs Tablet: Diashow-URL im Kiosk-Modus öffnen"
echo " (z. B. Fully Kiosk Browser oder 'chrome --kiosk <URL>')"
echo "=========================================================="
