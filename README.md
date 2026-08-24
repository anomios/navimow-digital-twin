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

- laufende FHEM-Installation
- Python 3.11 oder neuer
- Python `venv`
- Internetzugang zu den für Navimow benötigten Cloud-Endpunkten
- ein vorhandener Navimow-Account
- ein mit diesem Account verknüpfter Mähroboter

Der produktiv getestete Entwicklungsstand wurde mit Python 3.12 verwendet.

## Installation

### 1. Dateien kopieren

Die Dateien werden in die übliche FHEM-Struktur kopiert:

```bash
cp FHEM/70_Navimow.pm /opt/fhem/FHEM/70_Navimow.pm

cp www/pgm2/navimow_live.js \
  /opt/fhem/www/pgm2/navimow_live.js

mkdir -p /opt/fhem/navimow-python
cp -a navimow-python/. /opt/fhem/navimow-python/
```

### 2. Python-Umgebung anlegen

```bash
python3 -m venv /opt/fhem/navimow-python/venv

/opt/fhem/navimow-python/venv/bin/pip install \
  -r requirements.txt
```

Direkte Python-Abhängigkeiten:

```text
aiohttp>=3.14,<4
cryptography>=50,<51
navimow-sdk==0.1.2
paho-mqtt>=2.1,<3
```

### 3. FHEM-Gerät anlegen

Grunddefinition:

```text
define <NAME> Navimow
```

Beispiel:

```text
define NavimowMower Navimow
```

## Authentifizierung und Account-Session

Für die Private-Cloud-Anmeldung steht `navimow_private_account.py` zur Verfügung.

Das Werkzeug unterstützt unter anderem:

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

Standardwerte des Release-Standes sind:

```text
--client-path /opt/fhem/navimow-python
--region fra
--host navimow-fra.ninebot.com
--language de
--fhem-device i210Pro
```

Beispiel:

```bash
/opt/fhem/navimow-python/venv/bin/python \
  /opt/fhem/navimow-python/navimow_private_account.py \
  --interactive \
  --output /opt/fhem/navimow-python/cache/navimow_private_session.json \
  --fhem-device NavimowMower
```

Die E-Mail-Adresse wird interaktiv abgefragt. Das Passwort wird mit `getpass` eingelesen und nicht im Klartext in der Sessiondatei gespeichert.

**Wichtig:** Die erzeugte Sessiondatei enthält erneuerbare Token und darf nicht veröffentlicht oder weitergegeben werden.

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
