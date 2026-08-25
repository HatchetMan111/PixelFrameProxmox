# PixelFrame

Digitaler Bilderrahmen für ein altes Tablet im Heimnetz. Bilder per
Weboberfläche hochladen, Diashow läuft im Browser des Tablets. Läuft
vollständig lokal, keine Cloud, keine Registrierung.

## Installation (Proxmox-Host, als root)

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/PixelFrame/main/install/pixelframe.sh)"
```

Optional per Umgebungsvariable anpassbar (Defaults in Klammern):

```bash
CTID=201 CT_HOSTNAME=bilderrahmen PORT=8095 \
  bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/PixelFrame/main/install/pixelframe.sh)"
```

| Variable | Default | Bedeutung |
|---|---|---|
| `CTID` | `200` | Container-ID |
| `CT_HOSTNAME` | `pixelframe` | Hostname des Containers |
| `DISK_GB` | `2` | Festplattengröße in GB |
| `RAM_MB` | `512` | Arbeitsspeicher in MB |
| `CORES` | `1` | vCPU-Anzahl |
| `BRIDGE` | `vmbr0` | Netzwerk-Bridge |
| `STORAGE` | `local-lvm` | Storage für Rootfs |
| `TEMPLATE_STORAGE` | `local` | Storage für das LXC-Template |
| `PORT` | `8090` | Web-UI-Port |
| `DEBUG` | `0` | `1` = vollständiges `bash -x`-Log |

Nach der Installation zeigt das Skript die fertigen URLs an:

```
Upload:  http://<Container-IP>:8090/upload
Diashow: http://<Container-IP>:8090/frame?interval=8&shuffle=1
```

## Tablet als Bilderrahmen einrichten

1. Kiosk-Browser-App installieren, z. B. **Fully Kiosk Browser** (Android)
   oder `chrome --kiosk http://<Container-IP>:8090/frame?interval=8&shuffle=1`
2. Als Startseite/Autostart hinterlegen, Bildschirm-Standby deaktivieren
3. Die Seite hält den Bildschirm selbst wach (Screen Wake Lock), sofern der
   Browser das unterstützt

Diashow-Parameter in der URL:

- `interval` – Sekunden pro Bild (Standard: 8)
- `shuffle` – `1` für zufällige Reihenfolge, sonst chronologisch

## Update

```bash
pct exec <CTID> -- bash -c "cd /opt/pixelframe && git pull && ./venv/bin/pip install -q -r requirements.txt && systemctl restart pixelframe"
```

## Deinstallation

```bash
pct stop <CTID> && pct destroy <CTID>
```

Entfernt den kompletten Container inkl. aller hochgeladenen Bilder.

## Architektur

Keine Datenbank – das Dateisystem ist die Datenbank. Jedes hochgeladene Bild
wird beim Upload einmalig auf max. 1920px verkleinert, EXIF-korrigiert und
als JPEG gespeichert (`app/main.py`). Zwei Seiten: `/upload` (Verwaltung)
und `/frame` (Diashow, pollt alle 60s neue Bilder). Kein Login – Absicherung
über LAN-only (ufw im Container).

## Entwicklung / Tests

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements-dev.txt
./venv/bin/pytest tests/ -v
```

## Lizenz

MIT, siehe [LICENSE](LICENSE).
