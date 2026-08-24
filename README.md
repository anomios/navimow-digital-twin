# Navimow Digital Twin for FHEM

**Version 1.0.0**

Erster öffentlicher Release des Navimow Digital Twin für FHEM, basierend auf dem intern getesteten Entwicklungsstand 7.8.55.

Das Projekt integriert Segway-Navimow-Mähroboter in FHEM und stellt zusätzlich eine Python-Bridge für Private-Cloud-, MQTT-, Karten-, Timeline- und Digital-Twin-Funktionen bereit.

## Funktionsumfang

- FHEM-Modul für Status, Steuerung und Diagnose
- Python-Bridge für Navimow-Cloud und MQTT-Echtzeitdaten
- Private-Cloud-Anbindung
- Karten- und Geometriedaten
- Digital-Twin-Modell
- Bewegungs-, Trail-, Timeline- und Event-Auswertung
- FHEMWEB-Livekarte
- Zonenstart mit `resume` oder `restart`
- Bridge-Watchdog und automatischer Neustart
- Versions- und Zustandsdiagnose
- optionales Hilfswerkzeug für Account-/Session-Erzeugung

## Verzeichnisstruktur

```text
navimow-digital-twin-1.0.0/
├── FHEM/
│   └── 70_Navimow.pm
├── navimow-python/
│   ├── navimow_bridge.py
│   ├── navimow_connectivity_diag.py
│   ├── navimow_private_account.py
│   └── navimow_private/
│       ├── api/
│       └── ...
├── www/
│   └── pgm2/
│       └── navimow_live.js
├── LICENSE
├── THIRD_PARTY_NOTICES
├── README.md
└── requirements.txt
```

## Voraussetzungen

Benötigt werden:

- eine laufende FHEM-Installation
- Python 3.11 oder neuer
- Python `venv`
- Internetzugang zu den von Navimow verwendeten Cloud-Endpunkten
- ein vorhandener Navimow-Account
- ein mit diesem Account verknüpfter Mähroboter

Der produktiv getestete Entwicklungsstand wurde mit Python 3.12 verwendet.

### Bezugsquellen

- FHEM: https://fhem.de/
- FHEM-Dokumentation: https://fhem.de/commandref.html
- FHEM-Wiki: https://wiki.fhem.de/
- FHEM-Forum: https://forum.fhem.de/
- Python: https://www.python.org/
- Python `venv`: https://docs.python.org/3/library/venv.html
- Navimow SDK: https://github.com/segwaynavimow/navimow-sdk
- Eclipse Paho MQTT Python Client: https://github.com/eclipse-paho/paho.mqtt.python
- pyca/cryptography: https://cryptography.io/

## Installation

Die Beispiele gehen von Debian/Ubuntu und einer FHEM-Installation unter
`/opt/fhem` aus.

### 1. Python und venv installieren

```bash
apt update
apt install python3 python3-venv python3-pip
python3 --version
```

Erforderlich ist Python 3.11 oder neuer.

### 2. Release entpacken

```bash
tar xzf navimow-digital-twin-1.0.0.tar.gz
cd navimow-digital-twin-1.0.0
```

Optional:

```bash
sha256sum -c navimow-digital-twin-1.0.0.tar.gz.sha256
```

### 3. Python-Umgebung anlegen

```bash
mkdir -p /opt/fhem/navimow-python
python3 -m venv /opt/fhem/navimow-python/venv

/opt/fhem/navimow-python/venv/bin/python \
  -m pip install --upgrade pip
```

Eine Aktivierung mit `source` ist nicht erforderlich; die Beispiele verwenden
bewusst immer den vollständigen Pfad.

### 4. Python-Abhängigkeiten installieren

```bash
/opt/fhem/navimow-python/venv/bin/python \
  -m pip install -r requirements.txt
```

Direkte Abhängigkeiten:

```text
aiohttp>=3.14,<4
cryptography>=50,<51
navimow-sdk==0.1.2
paho-mqtt>=2.1,<3
```

Prüfung:

```bash
/opt/fhem/navimow-python/venv/bin/python - <<'PY'
from importlib.metadata import version

for package in ("aiohttp", "cryptography", "navimow-sdk", "paho-mqtt"):
    print(f"{package:15s} {version(package)}")

import aiohttp
import cryptography
import paho.mqtt
import mower_sdk

print("Python-Module: OK")
PY
```

### 5. Projektdateien installieren

```bash
cp FHEM/70_Navimow.pm /opt/fhem/FHEM/70_Navimow.pm

cp www/pgm2/navimow_live.js \
  /opt/fhem/www/pgm2/navimow_live.js

cp navimow-python/navimow_bridge.py \
   navimow-python/navimow_connectivity_diag.py \
   navimow-python/navimow_private_account.py \
   /opt/fhem/navimow-python/

cp -a navimow-python/navimow_private \
  /opt/fhem/navimow-python/

cp requirements.txt \
  /opt/fhem/navimow-python/requirements.txt
```

### 6. Installation prüfen

```bash
ls -l \
  /opt/fhem/FHEM/70_Navimow.pm \
  /opt/fhem/www/pgm2/navimow_live.js \
  /opt/fhem/navimow-python/navimow_bridge.py \
  /opt/fhem/navimow-python/navimow_private_account.py \
  /opt/fhem/navimow-python/requirements.txt
```

Python-Syntax:

```bash
find /opt/fhem/navimow-python \
  -path '/opt/fhem/navimow-python/venv' -prune -o \
  -type f -name '*.py' -print0 | \
xargs -0 /opt/fhem/navimow-python/venv/bin/python -m py_compile
```

### 7. Account und Session einrichten

Im nächsten Abschnitt wird die Authentifizierung mit
`navimow_private_account.py` beschrieben.

**Erst danach sollte das Navimow-Device in FHEM angelegt werden.**

## Authentifizierung und Account-Session

Für die Private-Cloud-Anmeldung steht das Hilfsprogramm
`navimow_private_account.py` zur Verfügung.

Das Werkzeug meldet sich interaktiv mit dem Navimow-Konto an, ermittelt die
zugeordneten Geräte und erzeugt eine lokale Sessiondatei für die Python-Bridge.

### Standardweg

Zuerst das Cache-Verzeichnis anlegen:

```bash
mkdir -p /opt/fhem/navimow-python/cache
chmod 700 /opt/fhem/navimow-python/cache
```

Danach die interaktive Anmeldung starten:

```bash
/opt/fhem/navimow-python/venv/bin/python \
  /opt/fhem/navimow-python/navimow_private_account.py \
  --interactive \
  --output /opt/fhem/navimow-python/cache/navimow_private_session.json \
  --fhem-device NavimowMower
```

`NavimowMower` ist nur ein Beispiel. Wer sein FHEM-Device später anders nennen
möchte, ersetzt den Namen entsprechend.

Während der Anmeldung werden interaktiv abgefragt:

```text
Navimow E-Mail:
Navimow Passwort:
```

Das Passwort wird mit `getpass` eingelesen und nicht im Klartext in der
Sessiondatei gespeichert.

### Erzeugte Sessiondatei prüfen

```bash
ls -l /opt/fhem/navimow-python/cache/navimow_private_session.json
```

Falls nötig:

```bash
chmod 600 /opt/fhem/navimow-python/cache/navimow_private_session.json
```

**Wichtig:** Die Sessiondatei enthält erneuerbare Zugangstoken und darf niemals
veröffentlicht, in ein Git-Repository eingecheckt oder in einem Forum gepostet
werden.

### Unterstützte Optionen

```text
--interactive
--output
--client-path
--region
--host
--language
--fhem-device
--vehicle-sn
```

Standardwerte des Release-Standes:

```text
--client-path /opt/fhem/navimow-python
--region fra
--host navimow-fra.ninebot.com
--language de
--fhem-device i210Pro
```

Für die meisten Installationen genügt der oben gezeigte Standardweg.

### FHEM-Device anlegen

Erst nach erfolgreicher Session-Erzeugung:

```text
define NavimowMower Navimow
```

Danach mindestens die Pfade setzen:

```text
attr NavimowMower bridgePython /opt/fhem/navimow-python/venv/bin/python
attr NavimowMower bridgeScript /opt/fhem/navimow-python/navimow_bridge.py
attr NavimowMower privateClientPath /opt/fhem/navimow-python
attr NavimowMower privateSessionFile /opt/fhem/navimow-python/cache/navimow_private_session.json
```

Je nach verwendetem Zugangsweg können zusätzlich relevant sein:

```text
accessToken
refreshToken
deviceId
privateEmail
privatePassword
privateRegion
privateHost
privateLanguage
privateVehicleSn
privateDeviceId
```

**Keine echten Zugangsdaten aus Beispielkonfigurationen übernehmen.**

### Ersten Funktionstest durchführen

```text
get NavimowMower oauth
get NavimowMower versions
set NavimowMower restartBridge
```

Ein gesunder Zustand sieht typischerweise so aus:

```text
bridgeState        running
privateCloudState  connected
mqttState          connected
```

Falls die Bridge nicht startet, keine Tokens oder Sessioninhalte posten.
Stattdessen den Diagnoseabschnitt dieser README verwenden.

## Wichtige FHEM-Attribute

Das Modul unterstützt unter anderem folgende Attribute:

### Basis / öffentliche API

```text
accessToken
refreshToken
deviceId
interval
disable
```

### Python-Bridge

```text
bridgePython
bridgeScript
bridgeRestartInterval
debugBridge
debugStatusDump
```

### Private Cloud

```text
privateEmail
privatePassword
privateRegion
privateHost
privateLanguage
privateVehicleSn
privateVehicleType
privateDeviceId
privatePollInterval
privateClientPath
privateSessionFile
```

### Karte / Trail / Timeline / Events

```text
privateMapEnabled
privateMapFile
privateTrailEnabled
privateTrailMaxPoints
privateTrailMinDistance
privateTrailFile
privateHistoryMaxEntries
privateTimelineMaxEntries
privateTimelineFile
privateTimelineExportCount
privateEventTimelineMaxEntries
privateEventTimelineFile
privateEventTimelineExportCount
```

### FHEMWEB-Liveansicht

```text
privateLiveSvgFile
privateLiveSvgWidth
privateLiveSvgHeight
privateLiveZoom
privateLivePanX
privateLivePanY
privateLiveBackground
privateLiveZoneFill
privateLiveZoneStroke
privateLiveTrailStroke
privateLiveTrailWidth
privateLiveMowerFill
privateLiveMowerStroke
privateLiveMowerIcon
privateLiveHeadingOffset
privateLiveNoGoFill
privateLiveNoGoStroke
privateLiveVisionOffFill
privateLiveVisionOffStroke
privateLiveLanguage
```

`privateLiveLanguage` unterstützt:

```text
auto
de
en
```

## SET-Befehle

Verfügbar sind:

```text
set <NAME> start ...
set <NAME> pause
set <NAME> resume
set <NAME> dock
set <NAME> refresh
set <NAME> mqttInfo
set <NAME> restartBridge
set <NAME> stopBridge
```

### Mähen starten

Kanonische Syntax:

```text
set <NAME> start <all|ZONE> <resume|restart>
```

Beispiele:

```text
set NavimowMower start all resume
set NavimowMower start all restart
set NavimowMower start Vorgarten resume
```

Zonen können anhand der bekannten Karten-Zonen aufgelöst werden. Für FHEMWEB werden dynamische Auswahlwerte erzeugt.

Aus Gründen der Rückwärtskompatibilität wird auch weiterhin unterstützt:

```text
set <NAME> start all
```

### Bridge-Steuerung

Bridge kontrolliert neu starten:

```text
set <NAME> restartBridge
```

Bridge manuell stoppen:

```text
set <NAME> stopBridge
```

## GET-Befehle

Verfügbar sind:

```text
get <NAME> status
get <NAME> devices
get <NAME> oauth
get <NAME> versions
get <NAME> timelineStatus
get <NAME> timeline [1|5|10|20|50|100]
get <NAME> events [1|5|10|20|50|100]
```

### Beispiele

Aktuellen Status abrufen:

```text
get NavimowMower status
```

Geräteliste abrufen:

```text
get NavimowMower devices
```

OAuth-Konfiguration prüfen:

```text
get NavimowMower oauth
```

Softwarestände anzeigen:

```text
get NavimowMower versions
```

Letzte 20 Timeline-Einträge:

```text
get NavimowMower timeline 20
```

Letzte 20 semantischen Events:

```text
get NavimowMower events 20
```

## FHEMWEB-Liveansicht

Die FHEMWEB-Darstellung verwendet:

```text
www/pgm2/navimow_live.js
```

Komponenten-Version des Browser-Layers:

```text
1.6.0
```

Die Laufzeitdateien der Karten-/Liveansicht werden nicht mit dem Release ausgeliefert. Sie entstehen aus der jeweiligen Mäher- und Karteninstanz.

## Diagnose

### Bridge-Zustand

Wichtige Readings sind unter anderem:

```text
bridgeState
bridgeLastError
bridgeLastConnect
bridgeVersion
fhemModuleVersion
projectVersion
privateCloudState
mqttState
mqttLastError
mqttLastUpdate
state
```

Ein gesunder Zustand sieht typischerweise so aus:

```text
bridgeState        running
privateCloudState  connected
mqttState          connected
```

`bridgeLastError` und `mqttLastError` werden nach einer nachweislich erfolgreichen Wiederverbindung geleert.

### Bridge neu starten

```text
set <NAME> restartBridge
```

### MQTT-Zugangsdaten neu anfordern

```text
set <NAME> mqttInfo
```

### Connectivity-Diagnose

Zusätzlich enthält das Release:

```text
navimow-python/navimow_connectivity_diag.py
```

Dieses Skript ist als Diagnosewerkzeug gedacht und nicht für den normalen Betrieb erforderlich.

## Bevor du im FHEM-Forum fragst

Bitte zuerst die Installation und die obigen Funktionstests vollständig
durchführen.

Falls danach noch ein Problem besteht, bei einer Supportanfrage möglichst die
Ausgabe des folgenden Diagnoseblocks vollständig mitliefern.

**Nicht mitposten:** `accessToken`, `refreshToken`, Passwörter,
`navimow_private_session.json` oder andere Session-/Tokeninhalte.

### Diagnoseblock

Vor dem Ausführen nur den Namen des eigenen FHEM-Navimow-Devices anpassen:

```bash
DEVICE=NavimowMower

echo "=== SYSTEM ==="
uname -a
echo
cat /etc/os-release 2>/dev/null |
  grep -E '^(PRETTY_NAME|VERSION)=' || true

echo
echo "=== PYTHON ==="
python3 --version
/opt/fhem/navimow-python/venv/bin/python --version 2>&1 || true

echo
echo "=== PYTHON-PAKETE ==="
/opt/fhem/navimow-python/venv/bin/python - <<'PY'
from importlib.metadata import version, PackageNotFoundError

for package in ("aiohttp", "cryptography", "navimow-sdk", "paho-mqtt"):
    try:
        print(f"{package:15s} {version(package)}")
    except PackageNotFoundError:
        print(f"{package:15s} FEHLT")

try:
    import aiohttp
    import cryptography
    import paho.mqtt
    import mower_sdk
    print("Python-Module: OK")
except Exception as error:
    print("Python-Module: FEHLER:", error)
PY

echo
echo "=== NAVIMOW-DATEIEN ==="
ls -l \
  /opt/fhem/FHEM/70_Navimow.pm \
  /opt/fhem/www/pgm2/navimow_live.js \
  /opt/fhem/navimow-python/navimow_bridge.py \
  /opt/fhem/navimow-python/navimow_private_account.py \
  /opt/fhem/navimow-python/requirements.txt \
  2>&1

echo
echo "=== VERSIONEN AUF PLATTE ==="
grep -nE '^# (Version|Project)|^our \$VERSION' \
  /opt/fhem/FHEM/70_Navimow.pm 2>/dev/null |
  head -8

grep -nE '^# (Version|Project)|^(BRIDGE|PROJECT)_VERSION' \
  /opt/fhem/navimow-python/navimow_bridge.py 2>/dev/null |
  head -8

grep -nE '^# (Version|Project)|version: "1\.6\.0"' \
  /opt/fhem/www/pgm2/navimow_live.js 2>/dev/null |
  head -8

echo
echo "=== FHEM-SERVICE ==="
systemctl status fhem --no-pager 2>&1 |
  head -25

echo
echo "=== NAVIMOW-READINGS ==="
printf "list %s\n" "$DEVICE" |
  nc -w 3 127.0.0.1 7072 2>/dev/null |
  grep -E \
'bridgeState|bridgeLastError|bridgeLastConnect|bridgeVersion|projectVersion|fhemModuleVersion|privateCloudState|mqttState|mqttLastError|mqttLastUpdate|state ' \
  || true

echo
echo "=== NAVIMOW-LOG ==="
grep -Ei \
'Navimow|bridge|mqtt' \
/opt/fhem/log/fhem-$(date +%Y-%m).log 2>/dev/null |
  tail -80 |
  sed -E \
    -e 's/(accessToken|refreshToken|password|privatePassword)[ =:]+[^ ,;]+/\1=<REDACTED>/Ig' \
    -e 's/(Authorization:[[:space:]]*Bearer[[:space:]]+)[^[:space:]]+/\1<REDACTED>/Ig'
```

`NavimowMower` muss dabei durch den Namen des eigenen FHEM-Devices ersetzt
werden.

### Was bei einer Supportanfrage zusätzlich hilfreich ist

Kurz dazuschreiben:

- verwendetes Navimow-Modell
- Navimow Digital Twin Version
- ob das Problem seit der Erstinstallation besteht oder erst später auftrat
- welcher Befehl ausgeführt wurde
- was erwartet wurde
- was tatsächlich passiert ist

Bitte keine Screenshots von Tokens, Sessiondateien oder kompletten
FHEM-Definitionen mit Zugangsdaten veröffentlichen.

## Laufzeitverzeichnisse

Folgende Verzeichnisse werden absichtlich **nicht** im Release mitgeliefert:

```text
cache/
data/
backups/
venv/
__pycache__/
```

Sie enthalten entweder Laufzeitdaten, lokale Installationsdaten oder Entwicklungsartefakte.

## Sicherheit

Nicht veröffentlichen oder weitergeben:

- `accessToken`
- `refreshToken`
- Navimow-Passwort
- MQTT-Passwort
- Sessiondateien
- `navimow_private_session.json`
- account- oder gerätespezifische Cache-Dateien

Die Sessiondatei wird mit restriktiven Dateirechten geschrieben. Passwörter werden von der Session-Verwaltung nicht dauerhaft gespeichert.

## Versionierung

Mit Version 1.0.0 beginnt die öffentliche Versionsgeschichte.

Der erste öffentliche Release basiert auf dem intern getesteten Entwicklungsstand:

```text
7.8.55
```

Ab 1.0.0 wird Semantic Versioning verwendet:

```text
MAJOR.MINOR.PATCH
```

Beispiele:

- `1.0.1` – kompatible Fehlerkorrektur
- `1.1.0` – neue kompatible Funktion
- `2.0.0` – inkompatible Änderung

Einzelne interne Komponenten besitzen zusätzlich eigene Versionsnummern, beispielsweise `navimow_live.js 1.6.0`.

## Lizenz

Der Projektcode steht unter:

```text
GNU General Public License v3.0 or later
SPDX-License-Identifier: GPL-3.0-or-later
```

Copyright:

```text
Copyright (C) 2026 Klaus Resch aka curiosus/anomios
```

Einzelne übernommene Komponenten stehen unter abweichenden kompatiblen Lizenzen.

Details:

- `LICENSE`
- `THIRD_PARTY_NOTICES`

Insbesondere enthält `THIRD_PARTY_NOTICES` die Herkunft und MIT-Lizenz der übernommenen Navimow-Private-Cloud-Komponenten.

## Haftung

Die Software wird ohne Gewährleistung bereitgestellt. Die vollständigen Bedingungen ergeben sich aus der GPL sowie den in `THIRD_PARTY_NOTICES` dokumentierten Fremdlizenzen.

Dieses Projekt ist eine unabhängige FHEM-Integration und kein offizielles Produkt von Segway oder Navimow.
