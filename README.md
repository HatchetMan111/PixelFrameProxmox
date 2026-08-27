# PixelFrame

Digitaler Bilderrahmen für ein altes Tablet im Heimnetz. Bilder und Videos
per Weboberfläche hochladen, Diashow läuft im Browser des Tablets. Läuft
vollständig lokal, keine Cloud, keine Registrierung. Admin-Bereich per
Passwort geschützt, die Tablet-Anzeige selbst braucht kein Login.

## Installation (Proxmox-Host, als root)

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/PixelFrameProxmox/main/install/pixelframe.sh)"
```

Optional per Umgebungsvariable anpassbar (Defaults in Klammern):

```bash
CTID=201 CT_HOSTNAME=bilderrahmen PORT=8095 \
  bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/PixelFrameProxmox/main/install/pixelframe.sh)"
```

| Variable | Default | Bedeutung |
|---|---|---|
| `CTID` | `200` | Container-ID |
| `CT_HOSTNAME` | `pixelframe` | Hostname des Containers |
| `DISK_GB` | `8` | Festplattengröße in GB (Videos brauchen mehr Platz als Bilder) |
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

1. **Für eine wirklich unsichtbare Adressleiste:** `/frame` auf dem Tablet
   öffnen → Browser-Menü → **"Zum Startbildschirm hinzufügen"**. Von dort
   gestartet läuft die Seite ohne jede Browser-Oberfläche (Standalone-Modus).
   Alternativ: Kiosk-Browser-App wie **Fully Kiosk Browser** (Android) oder
   `chrome --kiosk http://<Container-IP>:8090/frame`
2. Als Startseite/Autostart hinterlegen, Bildschirm-Standby deaktivieren
3. Die Seite versucht zusätzlich automatisch den Vollbildmodus (Fullscreen
   API) beim Drehen ins Querformat (wie z. B. bei YouTube) und hält den
   Bildschirm wach (Screen Wake Lock), sofern der Browser das unterstützt.
   Ein kleiner "⤢ Vollbild"-Button bleibt als manueller Fallback sichtbar –
   unterstützt der Browser Vollbild gar nicht (z. B. älteres iOS Safari) oder
   schlägt der Versuch fehl, blendet sich der Button automatisch aus, statt
   nutzlos angezeigt zu bleiben.

Anzeigedauer und Reihenfolge werden im Admin-Panel unter `/upload`
eingestellt (siehe unten) – `/frame` braucht dafür keine URL-Parameter mehr.
Optional lässt sich das weiterhin einmalig überschreiben: `/frame?interval=5&shuffle=1`

## Admin-Panel (`/upload`)

Geschützt mit HTTP Basic Auth – der Browser fragt automatisch nach
Zugangsdaten (Benutzername ist beliebig, nur das Passwort zählt).
**Standard-Passwort: `admin`** – direkt im Panel unter "Admin-Passwort
ändern" anpassbar. `/frame` (die Tablet-Anzeige) bleibt bewusst ohne Login.

- **Bilder & Videos:** JPG/PNG/WEBP (bis 50 MB) und MP4/WEBM (bis 300 MB).
  Videos werden unverändert gespeichert (kein Transcoding) und in der
  Diashow bis zum Ende abgespielt, unabhängig von der Anzeigedauer.
- **Anzeigedauer:** Sekunden pro Bild eintragen, "Speichern" klicken –
  wirkt auf allen offenen `/frame`-Ansichten spätestens nach der nächsten
  Aktualisierung (max. 60s). Gilt nur für Bilder, nicht für Videos.
- **Zufällige Reihenfolge:** Checkbox für Shuffle statt fester Reihenfolge.
- **Reihenfolge ändern:** ↑/↓-Buttons an jedem Bild/Video verschieben es in
  der Diashow-Reihenfolge nach vorne/hinten.
- **Ausblenden:** 👁-Button blendet ein Bild/Video aus der Diashow aus, ohne
  es zu löschen (z. B. für Fotos, die nur zeitweise nicht gezeigt werden
  sollen). Erneuter Klick blendet wieder ein.

## Update

```bash
pct exec <CTID> -- bash -c "cd /opt/pixelframe && git pull && ./venv/bin/pip install -q -r requirements.txt && systemctl restart pixelframe"
```

## Deinstallation

```bash
pct stop <CTID> && pct destroy <CTID>
```

Entfernt den kompletten Container inkl. aller hochgeladenen Bilder/Videos.

**Hinweis für bestehende Installationen:** Der Standard für `DISK_GB` wurde
wegen der Video-Unterstützung von 2 auf 8 GB angehoben. Bereits laufende
Container behalten ihre ursprüngliche Disk-Größe (nachträglich per
`pct resize <CTID> rootfs +6G` erweiterbar); nur Neuinstallationen nutzen
automatisch den neuen Default.

## Architektur

Keine Datenbank – das Dateisystem ist die Datenbank. Bilder werden beim
Upload einmalig auf max. 1920px verkleinert, EXIF-korrigiert und als JPEG
gespeichert; Videos werden unverändert übernommen (`app/main.py`).
Reihenfolge + Sichtbarkeit (`data/order.json`) und Anzeige-Einstellungen
(`data/settings.json`) liegen als kleine JSON-Dateien neben dem Medien-Ordner;
`order.json` heilt sich automatisch (neue Dateien werden angehängt, gelöschte
entfernt). Admin-Passwort-Hash liegt in `data/admin.json` (SHA-256, niemals
im Klartext).

Zwei Seiten: `/upload` (Verwaltung, per Passwort geschützt) und `/frame`
(Diashow, öffentlich/ohne Login – pollt alle 60s neue Bilder/Einstellungen,
zeigt Bilder für die eingestellte Anzeigedauer, Videos bis zum Ende). LAN-only
zusätzlich über ufw im Container.

## Entwicklung / Tests

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements-dev.txt
./venv/bin/pytest tests/ -v

# Frontend-Regressionstests (Node, keine Abhängigkeiten nötig):
node tests/js/frame_first_image.test.js
node tests/js/frame_video_advance.test.js
node tests/js/frame_fullscreen.test.js
```

## Lizenz

MIT, siehe [LICENSE](LICENSE).
