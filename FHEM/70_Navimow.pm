###############################################################################
#
# Navimow Digital Twin
#
# Module      : 70_Navimow.pm
# Version     : 1.0.0
# Project     : 1.0.0
# Created     : 2026-07-30
# Last Change : 2026-08-23
#
# Copyright (C) 2026 Klaus Resch aka curiosus/anomios
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Description :
# FHEM integration for Segway Navimow robotic mowers and the Navimow
# Digital Twin private-cloud bridge.
#
# Public API  :
# Navimow_Initialize()
# Navimow_Define()
# Navimow_Set()
# Navimow_Get()
#
# Change History
#
# 1.0.0   2026-08-24
#   First public release, based on internal development version 7.8.55.
#
# 7.8.24  2026-08-16
#   Added:
#     - FHEMWEB display for the next scheduled mowing
#   Changed:
#     - Shared browser layer raised to navimow_live.js 1.6.0
#   Notes:
#     - Schedule on/off remains read-only; app-side toggle appears to require
#       local Bluetooth proximity and is intentionally not emulated
#
# --------------
#
# 7.8.5   2026-08-12
# Changed:
# - FHEMWEB loads navimow_live.js with an explicit browser-layer version
#   query parameter to prevent stale JavaScript cache after updates
#
# 7.8.4   2026-08-11
# Added:
# - set start supports explicit resume/restart mode
# - FHEMWEB choices expose friendly zone/mode combinations without private ids
# - `set <name> start <zone> resume|restart` remains available on the command line
# Changed:
# - restart is sent as MOW_SETUP_RESTART; resume as MOW_SETUP_CONTINUE
#
# 7.8.3   2026-08-11
# Changed:
# - set start choices show friendly zone names without technical id prefixes
# - Zone names are resolved internally back to their private map ids
#
# 7.8.2   2026-08-11
# Added:
# - privateLiveLanguage:auto,de,en
# - Mowing-task display and cutting-disc indicator
# - Dynamic zone choices for set start
# - Runtime private-bridge zone mowing command
#
# 7.8.1   2026-08-11
#   Added:
#     - FHEMWEB live status panel below the map
#     - Human-readable mower status
#     - Battery SOC plus relative usable-window display
#     - Configured return/charge battery range
#     - Weekly mowing area and current mowing progress
#     - Viewport center/reset button
#   Changed:
#     - FHEMWEB uses shared navimow_live.js 1.1.0
#
# 7.8.0   2026-08-11
#   Added:
#     - Native FHEMWEB detail view for the Navimow live map
#     - Shared browser-side navimow_live.js integration
#     - Live mower overlay with interpolation, zoom and pan
#
# 7.7.8   2026-08-08
#   Fixed:
#     - Declared missing no-go/no-vision style variables in StartBridge
#
# 7.6.2c  2026-08-03
#   Added:
#     - get <device> events [1..100]
#     - Human-readable semantic event log
#     - EventTimeline version, size and sequence readings
#     - Configurable EventTimeline export file and limits
#
# 7.6.0   2026-08-03
#   Added:
#     - get <device> timeline [1..100]
#     - Raw timeline status and exported timeline readings
#
# 7.5.2   2026-08-03
#   Added:
#     - FHEM Timeline integration
#
###############################################################################

package main;

use strict;
use warnings;

use JSON;
use HttpUtils;
use Time::HiRes qw(gettimeofday);

#use lib '/opt/fhem/FHEM/lib';
#use Navimow::API qw(Request RefreshToken);

use constant NAVIMOW_CLIENT_ID =>
    "homeassistant";

use constant NAVIMOW_CLIENT_SECRET =>
    "57056e15-722e-42be-bbaa-b0cbfb208a52";

our $VERSION = "1.0.0";

our $init_done;

our @EXPORT_OK = qw(
    Request
    RefreshToken
);


###############################################################################
# Initialize
###############################################################################

sub Navimow_Initialize($)
{
    my ($hash) = @_;

    $hash->{DefFn}   = "Navimow_Define";
    $hash->{UndefFn} = "Navimow_Undef";
    $hash->{SetFn}   = "Navimow_Set";
    $hash->{GetFn}   = "Navimow_Get";
    $hash->{AttrFn}  = "Navimow_Attr";
    $hash->{FW_detailFn} = "Navimow_FW_detailFn";

    # Wird von der FHEM-Eventloop aufgerufen, sobald die
    # Python-Bridge Daten auf STDOUT liefert.
    $hash->{ReadFn} = "Navimow_BridgeRead";

    # Ermöglicht später den kontrollierten Neustart der Bridge,
    # falls der Kindprozess beendet wurde.
    $hash->{ReadyFn} = "Navimow_BridgeReady";

    $hash->{AttrList} =
          "accessToken "
        . "refreshToken "
        . "deviceId "
        . "interval "
        . "disable:0,1 "
        . "bridgePython "
        . "bridgeScript "
        . "bridgeRestartInterval "
        . "debugBridge:0,1 "
        . "debugStatusDump:0,1 "
        . "privateEmail "
        . "privatePassword "
        . "privateRegion "
        . "privateHost "
        . "privateLanguage "
        . "privateVehicleSn "
        . "privateVehicleType "
        . "privateDeviceId "
        . "privatePollInterval "
        . "privateClientPath "
        . "privateSessionFile "
        . "privateMapEnabled:0,1 "
        . "privateMapFile "
        . "privateTrailEnabled:0,1 "
        . "privateTrailMaxPoints "
        . "privateHistoryMaxEntries "
        . "privateTimelineMaxEntries "
        . "privateTimelineFile "
        . "privateTimelineExportCount "
        . "privateEventTimelineMaxEntries "
        . "privateEventTimelineFile "
        . "privateEventTimelineExportCount "
        . "privateLiveSvgFile "
        . "privateLiveSvgWidth "
        . "privateLiveSvgHeight "
        . "privateLiveZoom "
        . "privateLivePanX "
        . "privateLivePanY "
        . "privateLiveBackground "
        . "privateLiveZoneFill "
        . "privateLiveZoneStroke "
        . "privateLiveTrailStroke "
        . "privateLiveTrailWidth "
        . "privateLiveMowerFill "
        . "privateLiveMowerStroke "
        . "privateLiveMowerIcon "
        . "privateLiveHeadingOffset "
        . "privateLiveNoGoFill "
        . "privateLiveNoGoStroke "
        . "privateLiveVisionOffFill "
        . "privateLiveVisionOffStroke "
        . "privateLiveLanguage:auto,de,en "
        . "privateTrailMinDistance "
        . "privateTrailFile "
        . $readingFnAttributes;

    return;
}


###############################################################################
# Define device
###############################################################################

sub Navimow_Define($$)
{
    my ($hash, $def) = @_;

    my @a = split("[ \t]+", $def);

    return "Verwendung: define <name> Navimow"
        if @a != 2;

    my $name = $a[0];

    $hash->{NAME}  = $name;
    $hash->{STATE} = "defined";

    #
    # Eventuell aus einer älteren Modulversion vorhandene
    # Helper-Einträge entfernen.
    #
    delete($hash->{helper}{busy});
    delete($hash->{helper}{initialized});

    #
    # Ersten Statusabruf nach fünf Sekunden starten.
    #
    Navimow_ScheduleStatus(
        $hash,
        5
    );

    Log3(
        $name,
        3,
        "Navimow ($VERSION): device defined"
    );

    Navimow_StartBridge($hash);

    InternalTimer(
        gettimeofday() + 5,
        "Navimow_GetStatus",
        $hash,
        0
    );

    return undef;
}


###############################################################################
# Undefine device
###############################################################################

sub Navimow_Undef($$)
{
    my ($hash, $arg) = @_;

    #
    # Sämtliche diesem Device zugeordneten Timer entfernen,
    # insbesondere Start-, Restart- und Watchdog-Timer.
    #
    RemoveInternalTimer($hash);

    Navimow_StopBridge($hash);

    delete $hash->{BRIDGE_RESTART_PENDING};

    return undef;
}


###############################################################################
# Stop Bridge
###############################################################################

sub Navimow_StopBridge($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    RemoveInternalTimer(
        $hash,
        "Navimow_StartBridge"
    );

    RemoveInternalTimer(
        $hash,
        "Navimow_BridgeWatchdog"
    );

    #
    # Zuerst aus der FHEM-Eventloop entfernen.
    #
    if (defined($hash->{BRIDGE_SELECT_NAME})) {
        delete $selectlist{$hash->{BRIDGE_SELECT_NAME}};
        delete $hash->{BRIDGE_SELECT_NAME};
    }

    delete $hash->{FD};

    #
    # STDIN der Bridge schließen. Dadurch kann sich der
    # Python-Prozess bereits regulär beenden.
    #
    if (defined($hash->{BRIDGE_IN})) {
        close($hash->{BRIDGE_IN});
        delete $hash->{BRIDGE_IN};
    }

    #
    # Kindprozess beenden.
    #
    if (defined($hash->{BRIDGE_PID})) {
        my $pid = $hash->{BRIDGE_PID};

        if ($pid > 0 && kill(0, $pid)) {
            Log3(
                $name,
                4,
                "Navimow $name: stopping bridge process PID $pid"
            );

            kill("TERM", $pid);

            #
            # Dem Prozess kurz Gelegenheit geben, sich sauber
            # zu beenden. Insgesamt maximal etwa 0,3 Sekunden.
            #
            for (1 .. 3) {
                last if waitpid($pid, 1) == $pid;
                select(undef, undef, undef, 0.1);
            }

            #
            # Falls er auf SIGTERM nicht reagiert, sicher beenden.
            #
            if (kill(0, $pid)) {
                Log3(
                    $name,
                    3,
                    "Navimow $name: bridge process PID $pid did not terminate, sending SIGKILL"
                );

                kill("KILL", $pid);
                waitpid($pid, 0);
            }
        }
        else {
            waitpid($pid, 1);
        }

        delete $hash->{BRIDGE_PID};
    }

    #
    # STDOUT und STDERR erst nach dem Beenden schließen.
    #
    if (defined($hash->{BRIDGE_OUT})) {
        close($hash->{BRIDGE_OUT});
        delete $hash->{BRIDGE_OUT};
    }

    if (defined($hash->{BRIDGE_ERR})) {
        close($hash->{BRIDGE_ERR});
        delete $hash->{BRIDGE_ERR};
    }

    delete $hash->{BRIDGE_BUFFER};
    delete $hash->{BRIDGE_ERROR_BUFFER};
    delete $hash->{BRIDGE_RUNNING};
    delete $hash->{BRIDGE_STARTED};
    delete $hash->{BRIDGE_LAST_HEARTBEAT};

    return;
}


###############################################################################
# Starte Bridge
###############################################################################

sub Navimow_StartBridge($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    RemoveInternalTimer(
        $hash,
        "Navimow_StartBridge"
    );

    RemoveInternalTimer(
        $hash,
        "Navimow_BridgeWatchdog"
    );

    return if IsDisabled($name);
    return if $hash->{BRIDGE_MANUAL_STOP};

    #
    # Während FHEM die Konfiguration noch einliest, können die Attribute
    # des Devices noch fehlen. Den Bridge-Start deshalb bis zum Ende der
    # FHEM-Initialisierung verschieben.
    #
    if (!$init_done) {
        InternalTimer(
            gettimeofday() + 1,
            "Navimow_StartBridge",
            $hash,
            0
        );

        return;
    }

    #
    # Falls bereits eine Bridge läuft, nicht noch eine zweite starten.
    #
    if (
        defined($hash->{BRIDGE_PID})
        && $hash->{BRIDGE_PID} > 0
        && kill(0, $hash->{BRIDGE_PID})
    ) {
        Log3(
            $name,
            4,
            "Navimow $name: bridge process already running with PID "
                . $hash->{BRIDGE_PID}
        );

        #
        # Sicherstellen, dass auch für einen bereits laufenden Prozess
        # der Watchdog aktiv ist.
        #
        my $watchdogInterval = AttrVal(
            $name,
            "bridgeWatchdogInterval",
            90
        );

        $watchdogInterval = 90
            if $watchdogInterval !~ /^\d+(?:\.\d+)?$/
            || $watchdogInterval < 30;

        InternalTimer(
            gettimeofday() + $watchdogInterval,
            "Navimow_BridgeWatchdog",
            $hash,
            0
        );

        return;
    }

    #
    # Eventuelle Überreste eines vorherigen Prozesses entfernen.
    #
    Navimow_StopBridge($hash);

    my $accessToken = AttrVal(
        $name,
        "accessToken",
        ""
    );

    my $deviceId = AttrVal(
        $name,
        "deviceId",
        ""
    );

    #
    # Ein vollständiger SDK-Statusdump wird nur dann angefordert,
    # wenn das entsprechende Diagnoseattribut gesetzt ist.
    #
    my $debugStatusDump = AttrVal(
        $name,
        "debugStatusDump",
        0
    ) ? 1 : 0;

    if ($accessToken eq "") {
        Log3(
            $name,
            3,
            "Navimow $name: bridge cannot start, accessToken is missing"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "missingAccessToken",
            1
        );

        return;
    }

    if ($deviceId eq "") {
        Log3(
            $name,
            3,
            "Navimow $name: bridge cannot start, deviceId is missing"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "missingDeviceId",
            1
        );

        return;
    }

    # MQTT-AUTOSTART-BEGIN
    #
    # Das MQTT-Passwort liegt absichtlich nur im fluechtigen Internal
    # $hash->{".mqttPassword"} und ist nach einem FHEM-Neustart weg.
    # In diesem Fall MQTT-Zugangsdaten automatisch asynchron nachladen.
    # Die Bridge startet trotzdem sofort private-only und wird nach
    # erfolgreichem Callback kontrolliert neu gestartet.
    #
    if (($hash->{".mqttPassword"} // "") eq "") {
        my $now = gettimeofday();
        my $last = $hash->{helper}{mqttAutoInfoLastRequest} // 0;

        if (($now - $last) >= 30) {
            $hash->{helper}{mqttAutoInfoLastRequest} = $now;
            $hash->{helper}{mqttAutoRestartNeeded} = 1;

            Log3(
                $name,
                3,
                "Navimow $name: MQTT credentials missing; requesting them automatically"
            );

            Navimow_GetMQTTInfo($hash);
        }
    }
    # MQTT-AUTOSTART-END

    my $privateEmail = AttrVal(
        $name,
        "privateEmail",
        ""
    );

    my $privatePassword = AttrVal(
        $name,
        "privatePassword",
        ""
    );

    my $privateRegion = AttrVal(
        $name,
        "privateRegion",
        "fra"
    );

    my $privateHost = AttrVal(
        $name,
        "privateHost",
        "navimow-fra.ninebot.com"
    );

    my $privateLanguage = AttrVal(
        $name,
        "privateLanguage",
        "de"
    );

    my $privateVehicleSn = AttrVal(
        $name,
        "privateVehicleSn",
        $deviceId
    );

    my $privateVehicleType = AttrVal(
        $name,
        "privateVehicleType",
        801
    );

    my $privateDeviceId = AttrVal(
        $name,
        "privateDeviceId",
        ""
    );

    my $privatePollInterval = AttrVal(
        $name,
        "privatePollInterval",
        3
    );

    my $privateClientPath = AttrVal(
        $name,
        "privateClientPath",
        "/opt/fhem/navimow-python"
    );

    my $privateSessionFile = AttrVal(
        $name,
        "privateSessionFile",
        "/opt/fhem/navimow-python/cache/navimow_private_session.json"
    );

    my $privateMapEnabled = AttrVal(
        $name,
        "privateMapEnabled",
        1
    ) ? 1 : 0;

    my $privateMapFile = AttrVal(
        $name,
        "privateMapFile",
        "/opt/fhem/navimow-python/cache/navimow_map_detail.json"
    );

    my $privateTrailEnabled = AttrVal(
        $name,
        "privateTrailEnabled",
        1
    ) ? 1 : 0;

    my $privateTrailMaxPoints = AttrVal(
        $name,
        "privateTrailMaxPoints",
        3000
    );
    my $privateHistoryMaxEntries = AttrVal(
        $name,
        "privateHistoryMaxEntries",
        1000
    );
    my $privateTimelineMaxEntries = AttrVal(
        $name,
        "privateTimelineMaxEntries",
        5000
    );
    my $privateTimelineFile = AttrVal(
        $name,
        "privateTimelineFile",
        "/opt/fhem/navimow-python/cache/navimow_timeline_recent.json"
    );
    my $privateTimelineExportCount = AttrVal(
        $name,
        "privateTimelineExportCount",
        100
    );
    my $privateEventTimelineMaxEntries = AttrVal(
        $name,
        "privateEventTimelineMaxEntries",
        1000
    );
    my $privateEventTimelineFile = AttrVal(
        $name,
        "privateEventTimelineFile",
        "/opt/fhem/navimow-python/cache/navimow_event_timeline_recent.json"
    );
    my $privateEventTimelineExportCount = AttrVal(
        $name,
        "privateEventTimelineExportCount",
        100
    );
    my $privateLiveSvgFile = AttrVal(
        $name,
        "privateLiveSvgFile",
        "/opt/fhem/www/images/navimow/live/navimow.svg"
    );
    my $privateLiveSvgWidth = AttrVal(
        $name,
        "privateLiveSvgWidth",
        900
    );
    my $privateLiveSvgHeight = AttrVal(
        $name,
        "privateLiveSvgHeight",
        650
    );
    my $privateLiveZoom = AttrVal($name, "privateLiveZoom", 1.0);
    my $privateLivePanX = AttrVal($name, "privateLivePanX", 0.0);
    my $privateLivePanY = AttrVal($name, "privateLivePanY", 0.0);
    my $privateLiveBackground = AttrVal(
        $name, "privateLiveBackground", "#ffffff"
    );
    my $privateLiveZoneFill = AttrVal(
        $name, "privateLiveZoneFill", "#dfeee0"
    );
    my $privateLiveZoneStroke = AttrVal(
        $name, "privateLiveZoneStroke", "#477a4b"
    );
    my $privateLiveTrailStroke = AttrVal(
        $name, "privateLiveTrailStroke", "#2f7d32"
    );
    my $privateLiveTrailWidth = AttrVal(
        $name, "privateLiveTrailWidth", 1.0
    );
    my $privateLiveMowerFill = AttrVal($name, "privateLiveMowerFill", "#70b85a");
    my $privateLiveMowerStroke = AttrVal($name, "privateLiveMowerStroke", "#1f4d24");
    my $privateLiveMowerIcon = AttrVal($name, "privateLiveMowerIcon", "");
    my $privateLiveHeadingOffset = AttrVal($name, "privateLiveHeadingOffset", 90.0);
    my $privateLiveNoGoFill = AttrVal(
        $name, "privateLiveNoGoFill", "#8b8b8b"
    );
    my $privateLiveNoGoStroke = AttrVal(
        $name, "privateLiveNoGoStroke", "#3f3f3f"
    );
    my $privateLiveVisionOffFill = AttrVal(
        $name, "privateLiveVisionOffFill", "#d0b35a"
    );
    my $privateLiveVisionOffStroke = AttrVal(
        $name, "privateLiveVisionOffStroke", "#8c7426"
    );
    my $privateLiveLanguage = AttrVal(
        $name, "privateLiveLanguage", "auto"
    );

    my $privateTrailMinDistance = AttrVal(
        $name,
        "privateTrailMinDistance",
        0.08
    );

    my $privateTrailFile = AttrVal(
        $name,
        "privateTrailFile",
        "/opt/fhem/navimow-python/cache/navimow_mowing_trail.json"
    );

    my $python = AttrVal(
        $name,
        "bridgePython",
        "/opt/fhem/navimow-python/venv/bin/python"
    );

    my $script = AttrVal(
        $name,
        "bridgeScript",
        "/opt/fhem/navimow-python/navimow_bridge.py"
    );

    if (!-x $python) {
        Log3(
            $name,
            3,
            "Navimow $name: Python interpreter is not executable: $python"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "pythonNotExecutable",
            1
        );

        return;
    }

    if (!-f $script) {
        Log3(
            $name,
            3,
            "Navimow $name: bridge script does not exist: $script"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "scriptNotFound",
            1
        );

        return;
    }

    require IPC::Open3;
    require Symbol;
    require Fcntl;

    my ($bridgeIn, $bridgeOut);
    my $bridgeErr = Symbol::gensym();

    my $pid;

    eval {
        $pid = IPC::Open3::open3(
            $bridgeIn,
            $bridgeOut,
            $bridgeErr,
            $python,
            $script
        );
    };

    if ($@ || !defined($pid) || $pid <= 0) {
        my $error = $@ || "unknown process start error";
        $error =~ s/[\r\n]+/ /g;

        Log3(
            $name,
            3,
            "Navimow $name: unable to start bridge: $error"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "startFailed",
            1
        );

        return;
    }

    #
    # Konfigurationsdaten direkt über STDIN an die Bridge senden.
    # Dadurch wird keine Datei mit dem Access-Token angelegt.
    #
    #
    # Bereits von /openapi/mqtt/userInfo/get/v2 gelieferte MQTT-Daten
    # ebenfalls direkt an die Bridge uebergeben. Das Kennwort bleibt dabei
    # ausschliesslich im Prozess/STDIN und wird nicht als Reading angelegt.
    #
    my $mqttHost = ReadingsVal($name, "mqttHost", "");
    my $mqttUrl  = ReadingsVal($name, "mqttUrl",  "");
    my $mqttUser = ReadingsVal($name, "mqttUser", "");
    my $mqttPassword = $hash->{".mqttPassword"} // "";

    my $config = {
        accessToken     => $accessToken,
        apiBaseUrl      => "https://navimow-fra.ninebot.com",
        bridgeInitialState => ReadingsVal($name, "state", ""),
        mqttEnabled     => ($mqttHost ne "" && $mqttUrl ne "" && $mqttUser ne "" && $mqttPassword ne "") ? 1 : 0,
        mqttHost        => $mqttHost,
        mqttUrl         => $mqttUrl,
        mqttUser        => $mqttUser,
        mqttPassword    => $mqttPassword,
        deviceId            => $deviceId,
        debugStatusDump     => $debugStatusDump,
        privateEmail        => $privateEmail,
        privatePassword     => $privatePassword,
        privateRegion       => $privateRegion,
        privateHost         => $privateHost,
        privateLanguage     => $privateLanguage,
        privateVehicleSn    => $privateVehicleSn,
        privateVehicleType  => $privateVehicleType,
        privateDeviceId     => $privateDeviceId,
        privatePollInterval => $privatePollInterval,
        privateClientPath   => $privateClientPath,
        privateSessionFile  => $privateSessionFile,
        privateMapEnabled      => $privateMapEnabled,
        privateMapFile         => $privateMapFile,
        privateHistoryMaxEntries => $privateHistoryMaxEntries,
        privateTimelineMaxEntries => $privateTimelineMaxEntries,
        privateTimelineFile       => $privateTimelineFile,
        privateTimelineExportCount => $privateTimelineExportCount,
        privateEventTimelineMaxEntries => $privateEventTimelineMaxEntries,
        privateEventTimelineFile       => $privateEventTimelineFile,
        privateEventTimelineExportCount => $privateEventTimelineExportCount,
        privateLiveSvgFile              => $privateLiveSvgFile,
        privateLiveSvgWidth             => $privateLiveSvgWidth,
        privateLiveSvgHeight            => $privateLiveSvgHeight,
        privateLiveZoom                 => $privateLiveZoom,
        privateLivePanX                 => $privateLivePanX,
        privateLivePanY                 => $privateLivePanY,
        privateLiveBackground           => $privateLiveBackground,
        privateLiveZoneFill             => $privateLiveZoneFill,
        privateLiveZoneStroke           => $privateLiveZoneStroke,
        privateLiveTrailStroke          => $privateLiveTrailStroke,
        privateLiveTrailWidth           => $privateLiveTrailWidth,
        privateLiveMowerFill            => $privateLiveMowerFill,
        privateLiveMowerStroke          => $privateLiveMowerStroke,
        privateLiveMowerIcon            => $privateLiveMowerIcon,
        privateLiveHeadingOffset        => $privateLiveHeadingOffset,
        privateLiveNoGoFill             => $privateLiveNoGoFill,
        privateLiveNoGoStroke           => $privateLiveNoGoStroke,
        privateLiveVisionOffFill        => $privateLiveVisionOffFill,
        privateLiveVisionOffStroke      => $privateLiveVisionOffStroke,
        privateLiveLanguage             => $privateLiveLanguage,

        privateTrailEnabled    => $privateTrailEnabled,
        privateTrailMaxPoints  => $privateTrailMaxPoints,
        privateTrailMinDistance => $privateTrailMinDistance,
        privateTrailFile       => $privateTrailFile
    };

    my $configJson;

    eval {
        $configJson = encode_json($config);
    };

    if ($@ || !defined($configJson)) {
        my $error = $@ || "unable to encode bridge configuration";
        $error =~ s/[\r\n]+/ /g;

        Log3(
            $name,
            3,
            "Navimow $name: $error"
        );

        kill("TERM", $pid);
        waitpid($pid, 0);

        close($bridgeIn);
        close($bridgeOut);
        close($bridgeErr);

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "configEncodeFailed",
            1
        );

        return;
    }

    my $oldHandle = select($bridgeIn);
    $| = 1;
    select($oldHandle);

    my $writeOk = eval {
        print {$bridgeIn} $configJson . "\n";
        1;
    };

    if (!$writeOk) {
        my $error = $@ || $!;
        $error =~ s/[\r\n]+/ /g;

        Log3(
            $name,
            3,
            "Navimow $name: unable to send configuration to bridge: $error"
        );

        kill("TERM", $pid);
        waitpid($pid, 0);

        close($bridgeIn);
        close($bridgeOut);
        close($bridgeErr);

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "configWriteFailed",
            1
        );

        return;
    }

    #
    # STDOUT und STDERR nichtblockierend schalten.
    #
    foreach my $handle ($bridgeOut, $bridgeErr) {
        my $flags = fcntl(
            $handle,
            Fcntl::F_GETFL(),
            0
        );

        if (defined($flags)) {
            fcntl(
                $handle,
                Fcntl::F_SETFL(),
                $flags | Fcntl::O_NONBLOCK()
            );
        }
    }

    my $fd = fileno($bridgeOut);

    if (!defined($fd)) {
        Log3(
            $name,
            3,
            "Navimow $name: bridge STDOUT has no file descriptor"
        );

        kill("TERM", $pid);
        waitpid($pid, 0);

        close($bridgeIn);
        close($bridgeOut);
        close($bridgeErr);

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "invalidFileDescriptor",
            1
        );

        return;
    }

    my $selectName = "NavimowBridge_" . $name;

    $hash->{BRIDGE_PID}          = $pid;
    $hash->{BRIDGE_IN}           = $bridgeIn;
    $hash->{BRIDGE_OUT}          = $bridgeOut;
    $hash->{BRIDGE_ERR}          = $bridgeErr;
    $hash->{BRIDGE_SELECT_NAME}  = $selectName;
    $hash->{BRIDGE_BUFFER}       = "";
    $hash->{BRIDGE_ERROR_BUFFER} = "";
    $hash->{BRIDGE_STARTED}      = gettimeofday();
    $hash->{FD}                  = $fd;

    #
    # Ein Heartbeat eines früheren Bridge-Prozesses darf für den
    # neu gestarteten Prozess nicht als Lebenszeichen gelten.
    #
    delete $hash->{BRIDGE_LAST_HEARTBEAT};
    delete $hash->{BRIDGE_RUNNING};
    delete $hash->{BRIDGE_RESTART_PENDING};

    $selectlist{$selectName} = $hash;

    readingsBeginUpdate($hash);

    readingsBulkUpdate(
        $hash,
        "bridgeState",
        "starting"
    );

    readingsBulkUpdate(
        $hash,
        "bridgePid",
        $pid
    );

    readingsEndUpdate(
        $hash,
        1
    );

    Log3(
        $name,
        3,
        "Navimow $name: bridge process started with PID $pid"
    );

    #
    # Eigenständigen Bridge-Watchdog starten.
    #
    my $watchdogInterval = AttrVal(
        $name,
        "bridgeWatchdogInterval",
        90
    );

    $watchdogInterval = 90
        if $watchdogInterval !~ /^\d+(?:\.\d+)?$/
        || $watchdogInterval < 30;

    InternalTimer(
        gettimeofday() + $watchdogInterval,
        "Navimow_BridgeWatchdog",
        $hash,
        0
    );

    return;
}


###############################################################################
# Update Status Readings
###############################################################################

sub Navimow_UpdateStatusReadings($$)
{
    my ($hash, $message) = @_;

    my $name = $hash->{NAME};

    if (ref($message) ne "HASH") {
        Log3(
            $name,
            3,
            "Navimow $name: Statusaktualisierung enthält kein message-Objekt"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeLastError",
            "Statusaktualisierung enthält kein message-Objekt",
            1
        );

        return;
    }

    my $statusData = $message->{data};

    if (ref($statusData) ne "HASH") {
        Log3(
            $name,
            3,
            "Navimow $name: Bridge-Statusmeldung enthält kein data-Objekt"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeLastError",
            "Statusmeldung enthält kein data-Objekt",
            1
        );

        return;
    }

    my $extra =
        ref($statusData->{extra}) eq "HASH"
        ? $statusData->{extra}
        : undef;

    my $deviceId =
        defined($message->{deviceId})
        ? $message->{deviceId}
        : $statusData->{device_id};

    my $status =
        defined($statusData->{status})
        ? $statusData->{status}
        : undef;

    my $batteryPercent =
        defined($statusData->{battery})
        ? $statusData->{battery}
        : undef;

    my $errorCode =
        defined($statusData->{error_code})
        ? $statusData->{error_code}
        : undef;

    my $vehicleState;

    if (
        defined($extra)
        && defined($extra->{vehicleState})
    ) {
        $vehicleState = $extra->{vehicleState};
    }

    my $batteryDescription;

    if (
        defined($extra)
        && defined($extra->{descriptiveCapacityRemaining})
    ) {
        $batteryDescription =
            $extra->{descriptiveCapacityRemaining};
    }

    #
    # Der vollständige REST-Status liefert den Ladezustand zusätzlich
    # innerhalb von extra.capacityRemaining. Dieser Wert wird verwendet,
    # falls im allgemeinen battery-Feld kein Wert vorhanden ist.
    #
    if (
        !defined($batteryPercent)
        && defined($extra)
        && ref($extra->{capacityRemaining}) eq "ARRAY"
    ) {
        foreach my $capacity (
            @{$extra->{capacityRemaining}}
        ) {
            next if ref($capacity) ne "HASH";

            next
                if !defined($capacity->{unit})
                || $capacity->{unit} ne "PERCENTAGE";

            if (defined($capacity->{rawValue})) {
                $batteryPercent = $capacity->{rawValue};
                last;
            }
        }
    }

    my $statusTimestamp =
        defined($statusData->{timestamp})
        ? $statusData->{timestamp}
        : undef;

    my $updateTime = TimeNow();

    readingsBeginUpdate($hash);

    #
    # Zeitpunkt der zuletzt von der Bridge empfangenen Statusmeldung.
    #
    readingsBulkUpdate(
        $hash,
        "lastStatusUpdate",
        $updateTime
    );

    #
    # Der öffentliche Gerätezustand und der unveränderte Rohstatus.
    # Derzeit liefert das SDK bereits verständliche Zustände wie
    # docked, mowing, paused und returning.
    #
    if (defined($status)) {
        readingsBulkUpdate(
            $hash,
            "state_raw",
            $status
        );

        readingsBulkUpdate(
            $hash,
            "state",
            $status
        );
    }

    readingsBulkUpdate(
        $hash,
        "batteryPercent",
        $batteryPercent
    ) if defined($batteryPercent);

    readingsBulkUpdate(
        $hash,
        "errorCode",
        $errorCode
    ) if defined($errorCode);

    #
    # Diese Werte sind nur im vollständigen REST-Status vorhanden.
    # Bei kompakten MQTT-Meldungen bleiben die zuletzt bekannten Werte
    # deshalb bewusst erhalten.
    #
    readingsBulkUpdate(
        $hash,
        "vehicleState",
        $vehicleState
    ) if defined($vehicleState);

    readingsBulkUpdate(
        $hash,
        "batteryDescription",
        $batteryDescription
    ) if defined($batteryDescription);

    readingsBulkUpdate(
        $hash,
        "deviceId",
        $deviceId
    ) if defined($deviceId);

    readingsBulkUpdate(
        $hash,
        "statusTimestamp",
        $statusTimestamp
    ) if defined($statusTimestamp);

    readingsEndUpdate(
        $hash,
        1
    );

    Log3(
        $name,
        4,
        "Navimow $name: status received: "
        . "status="
        . (
            defined($status)
            ? $status
            : "unknown"
        )
        . ", battery="
        . (
            defined($batteryPercent)
            ? $batteryPercent
            : "unknown"
        )
        . ", error="
        . (
            defined($errorCode)
            ? $errorCode
            : "unknown"
        )
    );

    return;
}



###############################################################################
# Handle set commands
###############################################################################

sub Navimow_Set($@)
{
    my ($hash, @a) = @_;
    return "Mindestens ein Argument erforderlich" if (@a < 2);

    my $name = shift @a;
    my $cmd  = shift @a;

    my %sets = (
        start => "START", pause => "PAUSE", resume => "RESUME",
        dock => "DOCK", refresh => "REFRESH", mqttInfo => "MQTTINFO",
        restartBridge => "RESTARTBRIDGE", stopBridge => "STOPBRIDGE",
    );

    if (!exists $sets{$cmd}) {
        my @startChoices;
        my @labels = ("all");
        if (ref($hash->{helper}{mapZones}) eq "ARRAY") {
            foreach my $zone (@{$hash->{helper}{mapZones}}) {
                next if ref($zone) ne "HASH";
                my $id = defined($zone->{id}) ? $zone->{id} : "";
                next if $id eq "";
                my $label = defined($zone->{name}) && $zone->{name} ne ""
                    ? $zone->{name} : "Zone $id";
                $label =~ s/^\s+|\s+$//g;
                $label =~ s/\s+/_/g;
                push @labels, $label;
            }
        }
        foreach my $label (@labels) {
            push @startChoices, $label . "_resume";
            push @startChoices, $label . "_restart";
        }
        my @choices = ("start:" . join(",", @startChoices));
        push @choices, grep { $_ ne "start" } sort keys %sets;
        return "Unknown argument $cmd, choose one of " . join(" ", @choices);
    }

    if ($cmd eq "refresh") {
        Navimow_GetStatus($hash);
        return undef;
    }
    if ($cmd eq "mqttInfo") {
        Navimow_GetMQTTInfo($hash);
        return undef;
    }
    if ($cmd eq "stopBridge") {
        $hash->{BRIDGE_MANUAL_STOP} = 1;
        RemoveInternalTimer($hash, "Navimow_BridgeRestart");
        Navimow_StopBridge($hash);
        readingsSingleUpdate($hash, "bridgeState", "stopped", 1);
        return undef;
    }
    if ($cmd eq "restartBridge") {
        delete $hash->{BRIDGE_MANUAL_STOP};
        Log3($name, 3, "Navimow $name: Bridge wird auf Benutzeranforderung neu gestartet");
        RemoveInternalTimer($hash, "Navimow_StartBridge");
        readingsSingleUpdate($hash, "bridgeState", "restarting", 1);
        Navimow_StopBridge($hash);
        Navimow_StartBridge($hash);
        return undef;
    }

    if ($cmd eq "start") {
        my $selection = @a ? shift @a : "";
        my $mode = @a ? shift @a : "";

        return "Verwendung: set $name start <all|zone> <resume|restart>"
            if !defined($selection) || $selection eq "";

        # FHEMWEB can supply both values in its single value widget, e.g.
        # Zone_1_resume. The command-line form with a separate mode remains
        # the canonical syntax.
        if ($mode eq "" && $selection =~ /^(.*)_(resume|restart)$/i) {
            $selection = $1;
            $mode = lc($2);
        }

        # Backward compatible old form: `set <name> start all`.
        if (lc($selection) eq "all" && $mode eq "") {
            Navimow_SendCommand($hash, "START");
            return undef;
        }

        $mode = lc($mode || "");
        return "Modus muss resume oder restart sein"
            if $mode !~ /^(?:resume|restart)$/;

        my @zoneIds;
        my %knownById;
        my %knownByLabel;

        foreach my $zone (@{ $hash->{helper}{mapZones} || [] }) {
            next if ref($zone) ne "HASH";
            next if !defined($zone->{id}) || $zone->{id} !~ /^\d+$/;

            my $zoneId = int($zone->{id});
            my $label = defined($zone->{name}) && $zone->{name} ne ""
                ? $zone->{name}
                : "Zone $zoneId";
            $label =~ s/^\s+|\s+$//g;
            $label =~ s/\s+/_/g;

            $knownById{$zoneId} = 1;
            $knownByLabel{lc($label)} = $zoneId;
        }

        if (lc($selection) eq "all") {
            @zoneIds = sort { $a <=> $b } keys %knownById;
            return "Keine Kartenzonen für start all $mode verfügbar"
                if !@zoneIds;
        }

        foreach my $token (
            lc($selection) eq "all" ? () : split(/,/, $selection)
        ) {
            $token =~ s/^\s+|\s+$//g;

            if ($token =~ /^\d+$/) {
                my $zoneId = int($token);
                return "Unbekannte Zonen-ID $zoneId"
                    if %knownById && !$knownById{$zoneId};
                push @zoneIds, $zoneId;
                next;
            }

            my $lookup = lc($token);
            return "Unbekannte Zone '$token'"
                if !exists($knownByLabel{$lookup});
            push @zoneIds, $knownByLabel{$lookup};
        }

        my $requestId = time() . "-" . int(rand(1000000));
        my $ok = Navimow_SendPrivateBridgeCommand(
            $hash,
            {
                type => "mowZones",
                requestId => $requestId,
                zoneIds => \@zoneIds,
                mode => $mode,
            }
        );
        return "Private Bridge ist nicht verfügbar" if !$ok;

        readingsSingleUpdate(
            $hash, "lastCommand",
            "startZones:" . join(",", @zoneIds) . ":" . $mode, 1
        );
        return undef;
    }

    Navimow_SendCommand($hash, $sets{$cmd});
    return undef;
}


###############################################################################
# Send runtime command to private bridge
###############################################################################

sub Navimow_SendPrivateBridgeCommand($$)
{
    my ($hash, $payload) = @_;
    return 0 if !$hash || ref($payload) ne "HASH";

    my $bridgeIn = $hash->{BRIDGE_IN};
    return 0 if !defined($bridgeIn);

    my $json;
    eval { $json = encode_json($payload); };
    return 0 if $@ || !defined($json);

    my $ok = eval {
        print {$bridgeIn} $json . "\n";
        1;
    };
    return $ok ? 1 : 0;
}


###############################################################################
# Debug logging
###############################################################################

sub Navimow_Debug($$$)
{
    my ($hash, $level, $message) = @_;

    return
        if (!$hash);

    my $name = $hash->{NAME};

    return
        if (!$name);

    return
        if (!AttrVal(
            $name,
            "debugBridge",
            0
        ));

    Log3(
        $name,
        $level,
        "Navimow $name: $message"
    );

    return;
}


###############################################################################
# Verarbeite vollständigen SDK-Statusdump
###############################################################################

sub Navimow_HandleStatusDump($$)
{
    my ($hash, $message) = @_;

    return
        if (!$hash);

    my $name = $hash->{NAME};

    return
        if (!$name);

    my $statusData = $message->{data};

    if (
        !defined($statusData)
        || ref($statusData) ne "HASH"
    ) {
        Log3(
            $name,
            3,
            "Navimow $name: invalid SDK status dump received"
        );

        return;
    }

    my $jsonText;

    eval {
        #
        # canonical(1) sortiert die Schlüssel und erleichtert den
        # Vergleich von Statusdumps verschiedener Firmware-Versionen.
        #
        $jsonText = JSON->new
            ->canonical(1)
            ->pretty(1)
            ->encode($statusData);
    };

    if ($@ || !defined($jsonText)) {
        my $error = $@ || "unable to encode SDK status dump";
        $error =~ s/[\r\n]+/ /g;

        Log3(
            $name,
            3,
            "Navimow $name: unable to format SDK status dump: $error"
        );

        return;
    }

    Log3(
        $name,
        3,
        "========== Navimow SDK Status Dump BEGIN =========="
    );

    foreach my $line (split(/\n/, $jsonText)) {
        Log3(
            $name,
            3,
            $line
        );
    }

    Log3(
        $name,
        3,
        "========== Navimow SDK Status Dump END =========="
    );

    readingsSingleUpdate(
        $hash,
        "bridgeLastStatusDump",
        TimeNow(),
        1
    );

    #
    # Der Dump ist als einmalige Diagnoseanforderung gedacht.
    # Nach erfolgreicher Verarbeitung wird das Attribut entfernt.
    #
    if (AttrVal($name, "debugStatusDump", 0)) {
        CommandDeleteAttr(
            undef,
            "$name debugStatusDump"
        );
    }

    return;
}


###############################################################################
# Private-Cloud-Positionsdaten verarbeiten
###############################################################################

sub Navimow_UpdateLocationReadings($$)
{
    my ($hash, $message) = @_;

    return if !$hash;

    my $name = $hash->{NAME};
    my $locationData = $message->{data};

    if (ref($locationData) ne "HASH") {
        Log3(
            $name,
            3,
            "Navimow $name: bridge location message contains no data object"
        );
        return;
    }

    my %readingMap = (
        latitude          => "latitude",
        longitude         => "longitude",
        lastLatitude      => "lastLatitude",
        lastLongitude     => "lastLongitude",
        postureX          => "postureX",
        postureY          => "postureY",
        postureTheta      => "postureTheta",
        lastPostureX      => "lastPostureX",
        lastPostureY      => "lastPostureY",
        lastPostureTheta  => "lastPostureTheta",
        mapId             => "mapId",
        mapBaseId         => "mapBaseId",
        mapEditTime       => "mapEditTime",
        mapWorkPosition   => "mapWorkPosition",
        mowingPercentage      => "mowingPercentage",
        mowingWeekArea        => "mowingWeekArea",
        subtotalArea          => "subtotalArea",
        scheduleEnabled       => "scheduleEnabled",
        scheduleWeek          => "scheduleWeek",
        scheduleToday         => "scheduleToday",
        scheduleNext          => "scheduleNext",
        scheduleNextDate      => "scheduleNextDate",
        scheduleNextDay       => "scheduleNextDay",
        scheduleNextStart     => "scheduleNextStart",
        scheduleNextEnd       => "scheduleNextEnd",
        scheduleNextInMinutes => "scheduleNextInMinutes",

        statsTodayRuns            => "statsTodayRuns",
        statsTodayMowingSeconds   => "statsTodayMowingSeconds",
        statsTodayDurationSeconds => "statsTodayDurationSeconds",
        statsTodayDistanceM       => "statsTodayDistanceM",
        statsTodayAreaM2          => "statsTodayAreaM2",

        statsWeekRuns             => "statsWeekRuns",
        statsWeekMowingSeconds    => "statsWeekMowingSeconds",
        statsWeekDurationSeconds  => "statsWeekDurationSeconds",
        statsWeekDistanceM        => "statsWeekDistanceM",
        statsWeekAreaM2           => "statsWeekAreaM2",

        statsMonthRuns            => "statsMonthRuns",
        statsMonthMowingSeconds   => "statsMonthMowingSeconds",
        statsMonthDurationSeconds => "statsMonthDurationSeconds",
        statsMonthDistanceM       => "statsMonthDistanceM",
        statsMonthAreaM2          => "statsMonthAreaM2",

        statsLastStartedAt        => "statsLastStartedAt",
        statsLastMowingEndedAt    => "statsLastMowingEndedAt",
        statsLastEndedAt          => "statsLastEndedAt",
        statsLastMowingSeconds    => "statsLastMowingSeconds",
        statsLastDurationSeconds  => "statsLastDurationSeconds",
        statsLastDistanceM        => "statsLastDistanceM",
        statsLastAreaM2           => "statsLastAreaM2",
        statsLastProgressPercent  => "statsLastProgressPercent",
        statsLastResult           => "statsLastResult",

        pathId                => "pathId",
        reportTime        => "locationReportTime",
        rtk               => "rtk",
        mapSvgFile        => "mapSvgFile",
        trailFile         => "trailFile",
        trailPointCount   => "trailPointCount",
        trailSegmentCount => "trailSegmentCount",
        trailBreakCount   => "trailBreakCount",
        trailDistance     => "trailDistance",
        trailActive       => "trailActive"
    );

    readingsBeginUpdate($hash);

    foreach my $source (sort keys %readingMap) {
        next if !exists($locationData->{$source});
        next if !defined($locationData->{$source});

        readingsBulkUpdate(
            $hash,
            $readingMap{$source},
            $locationData->{$source}
        );
    }

    readingsBulkUpdate(
        $hash,
        "locationLastUpdate",
        TimeNow()
    );

    $hash->{BRIDGE_LAST_LOCATION} = gettimeofday();

    readingsEndUpdate(
        $hash,
        1
    );

    Log3(
        $name,
        4,
        "Navimow $name: private location received: "
        . "x="
        . (defined($locationData->{postureX}) ? $locationData->{postureX} : "unknown")
        . ", y="
        . (defined($locationData->{postureY}) ? $locationData->{postureY} : "unknown")
        . ", progress="
        . (defined($locationData->{mowingPercentage}) ? $locationData->{mowingPercentage} : "unknown")
    );

    return;
}


###############################################################################
# Abgeleiteten Zustand des digitalen Zwillings verarbeiten
###############################################################################

sub Navimow_UpdateModelStateReadings($$)
{
    my ($hash, $message) = @_;

    return if !$hash;

    my $name = $hash->{NAME};
    my $data = $message->{data};

    if (ref($data) ne "HASH") {
        Log3(
            $name,
            3,
            "Navimow $name: bridge modelState message contains no data object"
        );
        return;
    }

    my %readingMap = (
        motionState       => "motionState",
        motionStateDetail => "motionStateDetail",
        speedMps          => "speedMps",
        accelerationMps2   => "accelerationMps2",
        headingDegrees    => "headingDegrees",
        headingCardinal   => "headingCardinal",
        turnRateDps     => "turnRateDps",
        moving            => "moving",
        turning           => "turning",
        distanceSession => "distanceSession",
        locationArea      => "locationArea",
        currentZoneId     => "currentZoneId",
        currentZoneName => "currentZoneName",
        insideBoundary  => "insideBoundary",
        inTunnel        => "inTunnel",
        tunnelId        => "tunnelId",
        dockDistance      => "dockDistance",
        dockBearingDegrees => "dockBearingDegrees",
        dockBearingCardinal => "dockBearingCardinal",
        nearDock        => "nearDock",
        modelLastUpdate => "modelLastUpdate",
        historySize     => "historySize",
        eventSequence   => "eventSequence",
        timelineSize          => "timelineSize",
        timelineSequence      => "timelineSequence",
        eventTimelineSize     => "eventTimelineSize",
        eventTimelineSequence => "eventTimelineSequence",
        liveSvgFile           => "liveSvgFile",
        liveSvgWidth          => "liveSvgWidth",
        liveSvgHeight         => "liveSvgHeight",
        liveSvgZoom           => "liveSvgZoom",
        liveSvgPanX           => "liveSvgPanX",
        liveSvgPanY           => "liveSvgPanY"
    );

    readingsBeginUpdate($hash);

    foreach my $source (sort keys %readingMap) {
        next if !exists($data->{$source});
        next if !defined($data->{$source});

        readingsBulkUpdate(
            $hash,
            $readingMap{$source},
            $data->{$source}
        );
    }

    readingsEndUpdate($hash, 1);

    Log3(
        $name,
        5,
        "Navimow $name: model state received: motion="
        . (defined($data->{motionState}) ? $data->{motionState} : "unknown")
        . ", zone="
        . (defined($data->{currentZoneName}) ? $data->{currentZoneName} : "unknown")
        . ", speed="
        . (defined($data->{speedMps}) ? $data->{speedMps} : "unknown")
    );

    return;
}



###############################################################################
# Softwareversionen der Bridge und ihrer Komponenten verarbeiten
###############################################################################

sub Navimow_UpdateSoftwareVersionReadings($$)
{
    my ($hash, $message) = @_;

    return if !$hash;

    my $versions =
        ref($message->{versions}) eq "HASH"
        ? $message->{versions}
        : {};

    my %mapping = (
        project  => "projectVersion",
        bridge   => "bridgeVersion",
        model    => "modelVersion",
        geometry => "geometryVersion",
        motion   => "motionVersion",
        snapshot => "snapshotVersion",
        events   => "eventsVersion",
        history  => "historyVersion",
        timeline => "timelineVersion",
        eventTimeline => "eventTimelineVersion",
        rendererApi => "rendererApiVersion",
        rendererSvg => "rendererSvgVersion",
    );

    readingsBeginUpdate($hash);
    readingsBulkUpdate(
        $hash,
        "fhemModuleVersion",
        $VERSION
    );

    for my $component (sort keys %mapping)
    {
        next if !defined($versions->{$component});
        readingsBulkUpdate(
            $hash,
            $mapping{$component},
            $versions->{$component}
        );
    }

    readingsEndUpdate($hash, 1);

    Log3(
        $hash->{NAME},
        3,
        "Navimow $hash->{NAME}: software versions "
        . encode_json($versions)
    );

    return;
}


###############################################################################
# Semantisches Ereignis des digitalen Zwillings verarbeiten
###############################################################################

sub Navimow_UpdateModelEventReadings($$)
{
    my ($hash, $message) = @_;

    return if !$hash;

    my $name = $hash->{NAME};
    my $eventName = defined($message->{event}) ? $message->{event} : "unknown";
    my $timestamp = defined($message->{timestamp}) ? $message->{timestamp} : "";
    my $data = ref($message->{data}) eq "HASH" ? $message->{data} : {};

    my $eventData = eval { encode_json($data) };
    $eventData = "{}" if !defined($eventData) || $@;

    readingsBeginUpdate($hash);
    readingsBulkUpdate($hash, "event", $eventName);
    readingsBulkUpdate($hash, "eventTimestamp", $timestamp);
    readingsBulkUpdate($hash, "eventData", $eventData);
    readingsBulkUpdate(
        $hash,
        "eventSequence",
        $data->{sequence}
    ) if defined($data->{sequence});
    readingsEndUpdate($hash, 1);

    Log3(
        $name,
        4,
        "Navimow $name: digital-twin event '$eventName'"
    );

    return;
}


###############################################################################
# Metadaten des gespeicherten privaten Kartenabrufs verarbeiten
###############################################################################

sub Navimow_UpdateMapDetailReadings($$)
{
    my ($hash, $message) = @_;

    return if !$hash;

    my $name = $hash->{NAME};
    my $state = defined($message->{state}) ? $message->{state} : "unknown";

    readingsBeginUpdate($hash);

    readingsBulkUpdate($hash, "mapDetailState", $state);

    my %readingMap = (
        mapId                => "mapDetailMapId",
        mapBaseId            => "mapDetailMapBaseId",
        file                 => "mapDetailFile",
        fileBytes            => "mapDetailBytes",
        responseType         => "mapDetailResponseType",
        mapDetailStringBytes => "mapDetailStringBytes",
        mapDetailDecodedType => "mapDetailDecodedType",
        mapDetailItems       => "mapDetailItems",
        topLevelItems        => "mapDetailTopLevelItems",
        geometryFile          => "mapGeometryFile",
        geometryBytes         => "mapGeometryBytes",
        svgFile               => "mapSvgFile",
        svgBytes              => "mapSvgBytes",
        zoneCount             => "mapZoneCount",
        obstacleCount         => "mapObstacleCount",
        tunnelCount           => "mapTunnelCount",
        visionOffAreaCount    => "mapVisionOffAreaCount",
        dockCount             => "mapDockCount"
    );

    foreach my $source (sort keys %readingMap) {
        next if !exists($message->{$source});
        next if !defined($message->{$source});

        readingsBulkUpdate(
            $hash,
            $readingMap{$source},
            $message->{$source}
        );
    }

    foreach my $arrayField (
        ["topLevelKeys", "mapDetailTopLevelKeys"],
        ["mapDetailKeys", "mapDetailKeys"]
    ) {
        my ($source, $reading) = @{$arrayField};
        next if ref($message->{$source}) ne "ARRAY";

        readingsBulkUpdate(
            $hash,
            $reading,
            join(",", @{$message->{$source}})
        );
    }

    if (ref($message->{zones}) eq "ARRAY") {
        my @zones;
        foreach my $zone (@{$message->{zones}}) {
            next if ref($zone) ne "HASH";
            my $id = defined($zone->{id}) ? $zone->{id} : "";
            my $zoneName = defined($zone->{name}) ? $zone->{name} : "";
            next if $id eq "";
            push @zones, { id => "$id", name => "$zoneName" };
        }
        $hash->{helper}{mapZones} = \@zones;
        readingsBulkUpdate(
            $hash,
            "mapZones",
            join(",", map {
                $_->{id} . ":" . (
                    $_->{name} ne "" ? $_->{name} : ("Zone " . $_->{id})
                )
            } @zones)
        );
    }

    if (ref($message->{bounds}) eq "HASH") {
        my %boundsMap = (
            minX => "mapMinX",
            maxX => "mapMaxX",
            minY => "mapMinY",
            maxY => "mapMaxY",
            width => "mapWidth",
            height => "mapHeight"
        );
        foreach my $source (sort keys %boundsMap) {
            next if !defined($message->{bounds}{$source});
            readingsBulkUpdate($hash, $boundsMap{$source}, $message->{bounds}{$source});
        }
    }

    readingsBulkUpdate(
        $hash,
        "mapDetailLastUpdate",
        TimeNow()
    ) if $state eq "stored";

    readingsEndUpdate($hash, 1);

    Log3(
        $name,
        4,
        "Navimow $name: map-detail $state"
        . (defined($message->{file}) ? " file=$message->{file}" : "")
        . (defined($message->{fileBytes}) ? " bytes=$message->{fileBytes}" : "")
    );

    return;
}


###############################################################################
# Bridge Read
###############################################################################

sub Navimow_BridgeRead($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    return if !defined($hash->{BRIDGE_OUT});

    my $data = "";

    my $bytes = sysread(
        $hash->{BRIDGE_OUT},
        $data,
        8192
    );

    #
    # Lesefehler
    #
    if (!defined($bytes)) {
        return if $!{EAGAIN} || $!{EWOULDBLOCK};

        my $error = "$!";
        $error =~ s/[\r\n]+/ /g;

        Log3(
            $name,
            3,
            "Navimow $name: error reading bridge output: $error"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "readError",
            1
        );

        Navimow_StopBridge($hash);

        my $restartInterval = AttrVal(
            $name,
            "bridgeRestartInterval",
            30
        );

        InternalTimer(
            gettimeofday() + $restartInterval,
            "Navimow_StartBridge",
            $hash,
            0
        );

        return;
    }

    #
    # EOF: Die Bridge wurde beendet.
    #
    if ($bytes == 0) {
        Log3(
            $name,
            3,
            "Navimow $name: bridge connection closed"
        );

        readingsSingleUpdate(
            $hash,
            "bridgeState",
            "disconnected",
            1
        );

        Navimow_StopBridge($hash);

        return if IsDisabled($name);

        my $restartInterval = AttrVal(
            $name,
            "bridgeRestartInterval",
            30
        );

        InternalTimer(
            gettimeofday() + $restartInterval,
            "Navimow_StartBridge",
            $hash,
            0
        );

        return;
    }

    #
    # Empfangene Daten an einen vorhandenen Restpuffer anhängen.
    #
    $hash->{BRIDGE_BUFFER} = ""
        if !defined($hash->{BRIDGE_BUFFER});

    $hash->{BRIDGE_BUFFER} .= $data;

    #
    # Jede vollständige Zeile einzeln verarbeiten.
    #
    while ($hash->{BRIDGE_BUFFER} =~ s/^(.*?\n)//) {
        my $line = $1;

        $line =~ s/[\r\n]+$//;

        next if $line eq "";

        my $message;

        eval {
            $message = decode_json($line);
        };

        if ($@ || ref($message) ne "HASH") {
            my $error =
                $@
                || "decoded message is not a JSON object";

            $error =~ s/[\r\n]+/ /g;

            Log3(
                $name,
                3,
                "Navimow $name: invalid bridge JSON: $error; data: $line"
            );

            readingsSingleUpdate(
                $hash,
                "bridgeLastError",
                "ungültiges JSON",
                1
            );

            next;
        }

        my $type =
            defined($message->{type})
            ? $message->{type}
            : "unknown";

        Log3(
            $name,
            5,
            "Navimow $name: bridge message: $line"
        );

        #
        # Bridge startet.
        #
        if ($type eq "starting") {
            readingsSingleUpdate(
                $hash,
                "bridgeState",
                "starting",
                1
            );
        }

        #
        # MQTT-Subscription wird aufgebaut.
        #
        elsif ($type eq "subscribing") {
            readingsSingleUpdate(
                $hash,
                "bridgeState",
                "subscribing",
                1
            );
        }

        #
        # Zustand des optionalen MQTT-Kanals.
        #
        elsif ($type eq "mqttState") {
            my $state = defined($message->{state}) ? $message->{state} : "unknown";
            my $detail = defined($message->{message}) ? $message->{message} : "";

            readingsBeginUpdate($hash);
            readingsBulkUpdate($hash, "mqttState", $state);
            if ($state eq "connected") {
                readingsBulkUpdate($hash, "mqttLastError", "");
            }
            elsif ($detail ne "") {
                readingsBulkUpdate($hash, "mqttLastError", $detail);
            }
            readingsBulkUpdate($hash, "mqttLastUpdate", TimeNow());
            readingsEndUpdate($hash, 1);
        }

        #
        # Bridge läuft.
        #
        elsif ($type eq "running") {
            $hash->{BRIDGE_RUNNING} = 1;

            readingsBeginUpdate($hash);

            readingsBulkUpdate(
                $hash,
                "bridgeState",
                "running"
            );

            readingsBulkUpdate(
                $hash,
                "bridgeLastError",
                ""
            );

            readingsBulkUpdate(
                $hash,
                "bridgeLastConnect",
                TimeNow()
            );

            readingsBulkUpdate(
                $hash,
                "mqttAvailable",
                $message->{mqttAvailable} ? 1 : 0
            ) if defined($message->{mqttAvailable});

            readingsBulkUpdate(
                $hash,
                "mqttEnabled",
                $message->{mqttEnabled} ? 1 : 0
            ) if defined($message->{mqttEnabled});

            readingsEndUpdate(
                $hash,
                1
            );
        }

        #
        # Regelmäßiger Lebensnachweis der Bridge.
        #
        elsif ($type eq "heartbeat") {
            my $sequence =
                defined($message->{sequence})
                ? $message->{sequence}
                : undef;

            my $uptimeSeconds =
                defined($message->{uptimeSeconds})
                ? $message->{uptimeSeconds}
                : undef;

            $hash->{BRIDGE_RUNNING} = 1;
            
            $hash->{BRIDGE_LAST_HEARTBEAT} = gettimeofday();

            readingsBeginUpdate($hash);

            readingsBulkUpdate(
                $hash,
                "bridgeState",
                "running"
            );

            readingsBulkUpdate(
                $hash,
                "bridgeLastHeartbeat",
                TimeNow()
            );

            readingsBulkUpdate(
                $hash,
                "bridgeHeartbeatSequence",
                $sequence
            ) if defined($sequence);

            readingsBulkUpdate(
                $hash,
                "bridgeUptimeSeconds",
                $uptimeSeconds
            ) if defined($uptimeSeconds);

            readingsEndUpdate(
                $hash,
                1
            );

            Log3(
                $name,
                5,
                "Navimow $name: bridge heartbeat received: "
                . "sequence="
                . (
                    defined($sequence)
                    ? $sequence
                    : "unknown"
                )
                . ", uptime="
                . (
                    defined($uptimeSeconds)
                    ? $uptimeSeconds
                    : "unknown"
                )
                . " seconds"
            );
        }

        #
        # Zustand des privaten App-Cloud-Kanals.
        #
        elsif ($type eq "privateCloudState") {
            my $state =
                defined($message->{state})
                ? $message->{state}
                : "unknown";

            readingsBeginUpdate($hash);

            readingsBulkUpdate(
                $hash,
                "privateCloudState",
                $state
            );

            readingsBulkUpdate(
                $hash,
                "privateCloudMessage",
                $message->{message}
            ) if defined($message->{message});

            readingsBulkUpdate(
                $hash,
                "privateCloudHost",
                $message->{host}
            ) if defined($message->{host});

            readingsEndUpdate(
                $hash,
                1
            );

            $hash->{BRIDGE_PRIVATE_CLOUD_STATE} = $state;
            $hash->{BRIDGE_LAST_PRIVATE_CLOUD_STATE} = gettimeofday();
        }

        #
        # Initiale Statusabfrage wurde gestartet.
        #
        elsif ($type eq "initialStatusRequest") {
            readingsSingleUpdate(
                $hash,
                "bridgeInitialStatusRequest",
                TimeNow(),
                0
            );
        }

        #
        # Bridge wurde getrennt.
        #
        elsif ($type eq "disconnected") {
            delete $hash->{BRIDGE_RUNNING};

            readingsSingleUpdate(
                $hash,
                "bridgeState",
                "disconnected",
                1
            );
        }

        #
        # Fehler- oder Fatal-Meldung der Bridge.
        #
        elsif ($type eq "error" || $type eq "fatal") {
            my $stage =
                defined($message->{stage})
                ? $message->{stage}
                : "";

            my $error =
                defined($message->{message})
                ? $message->{message}
                : "unknown bridge error";

            my $readingValue =
                $stage ne ""
                ? "$stage: $error"
                : $error;

            #
            # Ein Fehler der einmaligen initialen Statusabfrage
            # beendet die MQTT-Verbindung nicht.
            #
            if ($stage eq "initialStatus") {
                readingsSingleUpdate(
                    $hash,
                    "bridgeLastError",
                    $readingValue,
                    1
                );

                Log3(
                    $name,
                    3,
                    "Navimow $name: initial status request failed: $error"
                );

                next;
            }

            #
            # Fehler des privaten App-Cloud-Kanals dürfen die weiterhin
            # funktionierende MQTT-Bridge nicht als beendet markieren.
            #
            if ($stage =~ /^private(?:Cloud|Location|Map)/) {
                readingsBeginUpdate($hash);

                readingsBulkUpdate(
                    $hash,
                    "privateCloudState",
                    "error"
                );

                readingsBulkUpdate(
                    $hash,
                    "privateCloudLastError",
                    $readingValue
                );

                readingsBulkUpdate(
                    $hash,
                    "privateCloudLastErrorTime",
                    TimeNow()
                );

                readingsEndUpdate(
                    $hash,
                    1
                );

                Log3(
                    $name,
                    3,
                    "Navimow $name: private cloud error: $readingValue"
                );

                next;
            }

            delete $hash->{BRIDGE_RUNNING};

            readingsBeginUpdate($hash);

            readingsBulkUpdate(
                $hash,
                "bridgeState",
                $type
            );

            readingsBulkUpdate(
                $hash,
                "bridgeLastError",
                $readingValue
            );

            readingsEndUpdate(
                $hash,
                1
            );

            Log3(
                $name,
                3,
                "Navimow $name: bridge $type: $readingValue"
            );
        }

        #
        # Bridge wurde kontrolliert beendet.
        #
        elsif ($type eq "stopped") {
            my $reason =
                defined($message->{reason})
                ? $message->{reason}
                : "unknown";

            delete $hash->{BRIDGE_RUNNING};

            readingsBeginUpdate($hash);

            readingsBulkUpdate(
                $hash,
                "bridgeState",
                "stopped"
            );

            readingsBulkUpdate(
                $hash,
                "bridgeStopReason",
                $reason
            );

            readingsEndUpdate(
                $hash,
                1
            );
        }

        #
        # Statusdaten des Mähers.
        #
        elsif ($type eq "status") {
            Navimow_UpdateStatusReadings(
                $hash,
                $message
            );
        }

        #
        # Position und Kartenbezug aus der privaten App-Cloud.
        #
        elsif ($type eq "location") {
            Navimow_UpdateLocationReadings(
                $hash,
                $message
            );
        }

        #
        # Abgeleiteter Zustand des digitalen Zwillings.
        #
        elsif ($type eq "commandResult") {
            my $ok = $message->{ok} ? 1 : 0;
            readingsBeginUpdate($hash);
            readingsBulkUpdate(
                $hash, "privateCommandState", $ok ? "accepted" : "error"
            );
            readingsBulkUpdate(
                $hash, "privateCommand",
                defined($message->{command}) ? $message->{command} : ""
            );
            readingsBulkUpdate(
                $hash, "privateCommandMessage",
                defined($message->{message}) ? $message->{message} : ""
            );
            readingsBulkUpdate(
                $hash, "privateCommandRequestId",
                defined($message->{requestId}) ? $message->{requestId} : ""
            );
            readingsEndUpdate($hash, 1);
        }
        elsif ($type eq "softwareVersions") {
            Navimow_UpdateSoftwareVersionReadings(
                $hash,
                $message
            );
        }
        elsif ($type eq "modelState") {
            Navimow_UpdateModelStateReadings(
                $hash,
                $message
            );
        }

        #
        # Semantische Zustandsaenderung des digitalen Zwillings.
        #
        elsif ($type eq "modelEvent") {
            Navimow_UpdateModelEventReadings(
                $hash,
                $message
            );
        }

        #
        # Einmalig abgerufene Karten-Rohdaten wurden lokal gespeichert.
        #
        elsif ($type eq "mapDetail") {
            Navimow_UpdateMapDetailReadings(
                $hash,
                $message
            );
        }

        #
        # Einmaliger vollständiger SDK-Statusdump.
        #
        elsif ($type eq "statusDump") {
            Navimow_HandleStatusDump(
                $hash,
                $message
            );
        }

        #
        # Noch unbekannter Nachrichtentyp.
        #
        else {
            Log3(
                $name,
                4,
                "Navimow $name: unknown bridge message type '$type'"
            );
        }
    }

    #
    # STDERR vorsichtshalber leeren. Die Bridge sollte reguläre
    # Status- und Fehlermeldungen als JSON über STDOUT ausgeben.
    #
    if (defined($hash->{BRIDGE_ERR})) {
        while (1) {
            my $errorData = "";

            my $errorBytes = sysread(
                $hash->{BRIDGE_ERR},
                $errorData,
                4096
            );

            last
                if !defined($errorBytes)
                && (
                    $!{EAGAIN}
                    || $!{EWOULDBLOCK}
                );

            last
                if !defined($errorBytes)
                || $errorBytes == 0;

            $errorData =~ s/[\r\n]+/ /g;

            Log3(
                $name,
                3,
                "Navimow $name: bridge STDERR: $errorData"
            );

            readingsSingleUpdate(
                $hash,
                "bridgeLastError",
                $errorData,
                1
            );
        }
    }

    return;
}


###############################################################################
# Get
###############################################################################

sub Navimow_Get($@)
{
    my ($hash, @a) = @_;

    return "Mindestens ein Argument erforderlich"
        if (@a < 2);

    my $name = shift @a;
    my $cmd  = shift @a;

    my %gets = (
        status   => 1,
        devices  => 1,
        oauth    => 1,
        versions       => 1,
        timelineStatus => 1,
        timeline       => "1,5,10,20,50,100",
        events         => "1,5,10,20,50,100",
    );

    if (!exists $gets{$cmd})
    {
        return "Unknown argument $cmd, choose one of "
             . join(" ", sort keys %gets);
    }

    #
    # Sofort Status aktualisieren
    #
    if ($cmd eq "status")
    {
        Navimow_GetStatus($hash);
        return "Statusabfrage gestartet";
    }

    #
    # Geräteliste abrufen
    #
    if ($cmd eq "devices")
    {
        Navimow_GetDevices($hash);
        return "Geräteabfrage gestartet";
    }

    #
    # OAuth-Diagnose
    #
    if ($cmd eq "oauth")
    {
        my $access  = AttrVal($name, "accessToken", "");
        my $refresh = AttrVal($name, "refreshToken", "");

        my $txt = "";

        $txt .= "AccessToken : "
             . ($access  ? "configured" : "missing")
             . "\n";

        $txt .= "RefreshToken: "
             . ($refresh ? "configured" : "missing")
             . "\n";

        return $txt;
    }

    #
    # Installierte Softwarestände anzeigen.
    #
    if ($cmd eq "events")
    {
        my $count = @a ? shift @a : 20;

        return "Usage: get $name events [1..100]"
            if $count !~ /^\d+$/ || $count < 1 || $count > 100;

        my $eventFile = AttrVal(
            $name,
            "privateEventTimelineFile",
            "/opt/fhem/navimow-python/cache/navimow_event_timeline_recent.json"
        );

        return "Event-Timeline-Datei nicht gefunden: $eventFile"
            if !-e $eventFile;

        my $fh;
        if (!open($fh, "<", $eventFile))
        {
            return "Event-Timeline-Datei $eventFile konnte nicht geöffnet werden: $!";
        }

        local $/;
        my $jsonText = <$fh>;
        close($fh);

        my $payload = eval { decode_json($jsonText) };
        if ($@ || ref($payload) ne "HASH")
        {
            my $error = $@ || "event timeline JSON is not an object";
            $error =~ s/[\r\n]+/ /g;
            return "Event-Timeline konnte nicht dekodiert werden: $error";
        }

        my $entries =
            ref($payload->{entries}) eq "ARRAY"
            ? $payload->{entries}
            : [];

        return "Event-Timeline ist leer"
            if !@{$entries};

        my %eventText = (
            motionStarted   => "Motion started",
            motionStopped   => "Motion stopped",
            dockReached     => "Dock reached",
            dockLeft        => "Dock left",
            tunnelEntered   => "Tunnel entered",
            tunnelLeft      => "Tunnel left",
            zoneEntered     => "Zone entered",
            zoneLeft        => "Zone left",
            chargingStarted => "Charging started",
            chargingStopped => "Charging stopped",
            warning         => "Warning",
            error           => "Error",
        );

        my %eventSymbol = (
            motionStarted   => ">",
            motionStopped   => "#",
            dockReached     => "D",
            dockLeft        => "D",
            tunnelEntered   => "T",
            tunnelLeft      => "T",
            zoneEntered     => "Z",
            zoneLeft        => "Z",
            chargingStarted => "+",
            chargingStopped => "-",
            warning         => "!",
            error           => "X",
        );

        my $start = @{$entries} - $count;
        $start = 0 if $start < 0;

        my @lines;
        my $lastDate = "";
        my $shownEvents = 0;

        for (my $index = $start; $index < @{$entries}; $index++)
        {
            my $entry = $entries->[$index];
            next if ref($entry) ne "HASH";

            my $timestamp = $entry->{timestamp};
            my ($dateText, $timeText) = ("unknown", "unknown");

            if (defined($timestamp) && $timestamp =~ /^\d+(?:\.\d+)?$/)
            {
                my @local = localtime(int($timestamp));
                $dateText = sprintf(
                    "%04d-%02d-%02d",
                    $local[5] + 1900,
                    $local[4] + 1,
                    $local[3]
                );
                $timeText = sprintf(
                    "%02d:%02d:%02d",
                    $local[2],
                    $local[1],
                    $local[0]
                );
            }

            if ($dateText ne $lastDate)
            {
                push @lines, "" if @lines;
                push @lines, $dateText;
                push @lines, "-" x length($dateText);
                $lastDate = $dateText;
            }

            my $eventName =
                defined($entry->{name}) && $entry->{name} ne ""
                ? $entry->{name}
                : "unknown";

            my $text =
                exists($eventText{$eventName})
                ? $eventText{$eventName}
                : $eventName;

            my $symbol =
                exists($eventSymbol{$eventName})
                ? $eventSymbol{$eventName}
                : "*";

            my $payloadData =
                ref($entry->{payload}) eq "HASH"
                ? $entry->{payload}
                : {};

            my @details;

            my $zoneName =
                defined($payloadData->{zoneName})
                ? $payloadData->{zoneName}
                : (
                    defined($payloadData->{zone})
                    ? $payloadData->{zone}
                    : ""
                );

            push @details, $zoneName
                if $zoneName ne "";

            push @details, "zoneId=" . $payloadData->{zoneId}
                if defined($payloadData->{zoneId})
                && $zoneName eq "";

            push @details, "tunnelId=" . $payloadData->{tunnelId}
                if defined($payloadData->{tunnelId});

            my $severity =
                defined($entry->{severity})
                ? $entry->{severity}
                : "info";

            push @details, "severity=$severity"
                if $severity ne "info";

            my $detailText =
                @details
                ? " (" . join(", ", @details) . ")"
                : "";

            my $sequence =
                defined($entry->{sequence})
                ? $entry->{sequence}
                : "?";

            $shownEvents++;
            push @lines, sprintf(
                "%s  [%s] %-18s%s  (#%s)",
                $timeText,
                $symbol,
                $text,
                $detailText,
                $sequence
            );
        }

        my $header = sprintf(
            "Navimow Event Log: showing %d of %d exported events (sequence %s)",
            $shownEvents,
            scalar(@{$entries}),
            defined($payload->{sequence}) ? $payload->{sequence} : "?"
        );

        return $header . "\n\n" . join("\n", @lines);
    }

    if ($cmd eq "timeline")
    {
        my $count = @a ? shift @a : 20;

        return "Usage: get $name timeline [1..100]"
            if $count !~ /^\d+$/ || $count < 1 || $count > 100;

        my $timelineFile = AttrVal(
            $name,
            "privateTimelineFile",
            "/opt/fhem/navimow-python/cache/navimow_timeline_recent.json"
        );

        return "Timeline-Datei nicht gefunden: $timelineFile"
            if !-e $timelineFile;

        my $fh;
        if (!open($fh, "<", $timelineFile))
        {
            return "Timeline-Datei $timelineFile konnte nicht geöffnet werden: $!";
        }

        local $/;
        my $jsonText = <$fh>;
        close($fh);

        my $payload = eval { decode_json($jsonText) };
        if ($@ || ref($payload) ne "HASH")
        {
            my $error = $@ || "timeline JSON is not an object";
            $error =~ s/[\r\n]+/ /g;
            return "Timeline konnte nicht dekodiert werden: $error";
        }

        my $entries =
            ref($payload->{entries}) eq "ARRAY"
            ? $payload->{entries}
            : [];

        my $start = @{$entries} - $count;
        $start = 0 if $start < 0;

        my @lines;
        for (my $index = $start; $index < @{$entries}; $index++)
        {
            my $entry = $entries->[$index];
            next if ref($entry) ne "HASH";

            my $snapshot =
                ref($entry->{snapshot}) eq "HASH"
                ? $entry->{snapshot}
                : {};
            my $motion =
                ref($snapshot->{motion}) eq "HASH"
                ? $snapshot->{motion}
                : {};
            my $geometry =
                ref($snapshot->{geometry}) eq "HASH"
                ? $snapshot->{geometry}
                : {};

            my $timestamp = $entry->{timestamp};
            my $timeText = "unknown";
            if (defined($timestamp) && $timestamp =~ /^\d+(?:\.\d+)?$/)
            {
                my @local = localtime(int($timestamp));
                $timeText = sprintf(
                    "%04d-%02d-%02d %02d:%02d:%02d",
                    $local[5] + 1900,
                    $local[4] + 1,
                    $local[3],
                    $local[2],
                    $local[1],
                    $local[0]
                );
            }

            my $sequence =
                defined($entry->{sequence})
                ? $entry->{sequence}
                : "?";
            my $area =
                defined($geometry->{location_area})
                ? $geometry->{location_area}
                : "unknown";
            my $zone =
                defined($geometry->{current_zone_name})
                && $geometry->{current_zone_name} ne ""
                ? $geometry->{current_zone_name}
                : "-";
            my $motionText =
                defined($snapshot->{motion_detail})
                ? $snapshot->{motion_detail}
                : (
                    defined($motion->{motion})
                    ? $motion->{motion}
                    : "unknown"
                );
            my $speed = sprintf(
                "%.3f",
                defined($motion->{speed_mps})
                ? $motion->{speed_mps}
                : 0
            );

            my @eventNames;
            if (ref($entry->{events}) eq "ARRAY")
            {
                for my $event (@{$entry->{events}})
                {
                    next if ref($event) ne "HASH";
                    push @eventNames, $event->{name}
                        if defined($event->{name});
                }
            }
            my $events =
                @eventNames
                ? join(",", @eventNames)
                : "-";

            push @lines, sprintf(
                "#%-5s %s  area=%-7s zone=%-12s motion=%-9s speed=%s  events=%s",
                $sequence,
                $timeText,
                $area,
                $zone,
                $motionText,
                $speed,
                $events
            );
        }

        return "Timeline ist leer"
            if !@lines;

        my $header = sprintf(
            "Timeline: showing %d of %d exported entries (sequence %s)",
            scalar(@lines),
            scalar(@{$entries}),
            defined($payload->{sequence}) ? $payload->{sequence} : "?"
        );

        return $header . "\n" . join("\n", @lines);
    }

    if ($cmd eq "timelineStatus")
    {
        my @lines = (
            sprintf(
                "%-18s %s",
                "Timeline Version:",
                ReadingsVal($name, "timelineVersion", "unknown")
            ),
            sprintf(
                "%-18s %s",
                "Entries:",
                ReadingsVal($name, "timelineSize", "0")
            ),
            sprintf(
                "%-18s %s",
                "Sequence:",
                ReadingsVal($name, "timelineSequence", "0")
            ),
            sprintf(
                "%-18s %s",
                "History Entries:",
                ReadingsVal($name, "historySize", "0")
            ),
            sprintf(
                "%-18s %s",
                "Event Sequence:",
                ReadingsVal($name, "eventSequence", "0")
            ),
        );

        return join("\n", @lines);
    }

    if ($cmd eq "versions")
    {
        my @versionReadings = (
            [ "Project",  "projectVersion"  ],
            [ "Bridge",   "bridgeVersion"   ],
            [ "FHEM",     "fhemModuleVersion" ],
            [ "Model",    "modelVersion"    ],
            [ "Geometry", "geometryVersion" ],
            [ "Motion",   "motionVersion"   ],
            [ "Snapshot", "snapshotVersion" ],
            [ "Events",   "eventsVersion"   ],
            [ "History",  "historyVersion"  ],
            [ "Timeline", "timelineVersion" ],
            [ "EventTimeline", "eventTimelineVersion" ],
        );

        my @lines;
        for my $entry (@versionReadings)
        {
            my ($label, $reading) = @{$entry};
            push @lines,
                sprintf(
                    "%-10s %s",
                    $label . ":",
                    ReadingsVal($name, $reading, "unknown")
                );
        }

        return join("\n", @lines);
    }

    return undef;
}


###############################################################################
# Send mower command
###############################################################################

sub Navimow_SendCommand($$)
{
    my ($hash, $cmd) = @_;

    my $name = $hash->{NAME};

    my $deviceId =
        AttrVal(
            $name,
            "deviceId",
            ""
        );

    if (!$deviceId)
    {
        Log3(
            $name,
            2,
            "Navimow: no deviceId configured"
        );

        return;
    }

    my %commandMap =
    (
        START =>
        {
            command => "action.devices.commands.StartStop",
            params  =>
            {
                on => JSON::true
            }
        },

        STOP =>
        {
            command => "action.devices.commands.StartStop",
            params  =>
            {
                on => JSON::false
            }
        },

        PAUSE =>
        {
            command => "action.devices.commands.PauseUnpause",
            params  =>
            {
                on => JSON::false
            }
        },

        RESUME =>
        {
            command => "action.devices.commands.PauseUnpause",
            params  =>
            {
                on => JSON::true
            }
        },

        DOCK =>
        {
            command => "action.devices.commands.Dock"
        }
    );

    if (!exists($commandMap{$cmd}))
    {
        Log3(
            $name,
            2,
            "Navimow: unknown command $cmd"
        );

        return;
    }

    my %execution =
    (
        command => $commandMap{$cmd}{command}
    );

    if (exists($commandMap{$cmd}{params}))
    {
        $execution{params} =
            $commandMap{$cmd}{params};
    }

    my $body =
        encode_json(
        {
            commands =>
            [
                {
                    devices =>
                    [
                        {
                            id => $deviceId
                        }
                    ],

                    execution => \%execution
                }
            ]
        });

    Log3(
        $name,
        3,
        "Navimow sending command $cmd"
    );

    Navimow_Request(
        $hash,
        "POST",
        "/openapi/smarthome/sendCommands",
        $body,
        sub
        {
            my ($hash, $json) = @_;

            my $name = $hash->{NAME};

            Log3(
                $name,
                3,
                "Navimow command $cmd accepted"
            );

            readingsSingleUpdate(
                $hash,
                "lastCommand",
                lc($cmd),
                1
            );

            #
            # Status kurz nach der Befehlsannahme aktualisieren.
            # Dieser Abruf ersetzt vorübergehend den regulären Polling-Timer.
            # Navimow_GetStatus plant danach wieder den normalen Intervall.
            #
            Navimow_ScheduleStatus(
                $hash,
                2
            );
        }
    );

    return;
}


###############################################################################
# Parse device list
###############################################################################

sub Navimow_ParseDevices($$)
{
    my ($hash,$json)=@_;

    my $name=$hash->{NAME};

    if (($json->{code}//0) != 1)
    {
        Log3(
            $name,
            2,
            "Navimow authList failed: "
            . ($json->{desc}//"unknown")
        );
        return;
    }

    my $devices =
        $json->{data}
             ->{payload}
             ->{devices};

    return
        if(
            ref($devices) ne "ARRAY"
            ||
            !@$devices
        );

    my $device = $devices->[0];

    readingsBeginUpdate($hash);

    readingsBulkUpdate(
        $hash,
        "deviceName",
        $device->{name}
    ) if exists($device->{name});

    readingsBulkUpdate(
        $hash,
        "model",
        $device->{model}
    ) if exists($device->{model});

    readingsBulkUpdate(
        $hash,
        "firmware",
        $device->{firmware}
    ) if exists($device->{firmware});

    readingsBulkUpdate(
        $hash,
        "deviceId",
        $device->{id}
    ) if exists($device->{id});

    readingsEndUpdate($hash,1);

    #
    # deviceId automatisch als Attribut setzen
    #
    if(
        exists($device->{id})
        &&
        AttrVal($name,"deviceId","") eq ""
    )
    {
        CommandAttr(
            undef,
            "$name deviceId $device->{id}"
        );

        Log3(
            $name,
            3,
            "Navimow deviceId automatically stored"
        );
    }
}


###############################################################################
# Get device list
###############################################################################

sub Navimow_GetDevices($)
{
    my ($hash)=@_;

    Navimow_Request(
        $hash,
        "GET",
        "/openapi/smarthome/authList",
        undef,
        \&Navimow_ParseDevices
    );
}


###############################################################################
# Generic REST request
###############################################################################

sub Navimow_Request($$$$$)
{
    my ($hash,$method,$path,$body,$callback) = @_;

    my $name = $hash->{NAME};

    my $token =
        AttrVal(
            $name,
            "accessToken",
            ""
        );

    if(!$token)
    {
        Log3(
            $name,
            2,
            "Navimow: no accessToken configured"
        );
        return;
    }

    #
    # Request für automatischen Retry merken
    #
    $hash->{helper}{lastRequest} =
    {
        method   => $method,
        path     => $path,
        body     => $body,
        callback => $callback
    };

    Log3(
        $name,
        4,
        "Navimow request $method $path"
    );

    Log3(
        $name,
        4,
        "Navimow $name: using configured access token"
    );

    my %param;

    $param{url} =
        "https://navimow-fra.ninebot.com".$path;

    $param{method}  = $method;
    $param{timeout} = 20;

    $param{header} =
          "Authorization: Bearer $token\r\n"
        . "Content-Type: application/json\r\n"
        . "requestId: ".int(rand(1000000000));

    $param{data} = $body
        if(defined($body));

    #
    # Hash im Callback verfügbar machen
    #
    $param{hash} = $hash;

    $param{callback} = sub
    {
        my ($param,$err,$data) = @_;

        my $hash = $param->{hash};
        my $name = $hash->{NAME};

        Log3(
            $name,
            4,
            "Navimow callback entered"
        );

        if($err ne "")
        {
            Log3(
                $name,
                2,
                "Navimow HTTP error: $err"
            );
            return;
        }

        my $json;

        eval
        {
            $json = decode_json($data);
        };

        if($@)
        {
            Log3(
                $name,
                2,
                "Navimow JSON decode error: $@"
            );

            Log3(
                $name,
                4,
                "Raw response: $data"
            );

            return;
        }

        #
        # AccessToken ungültig?
        #
        if(
               ($json->{code}//0) == 4005
            || ($json->{desc}//"") eq "CODE_OAUTH_INFO_ILLEGAL"
            || ($json->{desc}//"") eq "TOKEN_EXPIRED"
        )
        {
            if(!$hash->{helper}{refreshRunning})
            {
                Log3(
                    $name,
                    3,
                    "Navimow accessToken expired"
                );

                Navimow_RefreshToken($hash);
            }

            return;
        }

        if(($json->{code}//0) != 1)
        {
            Log3(
                $name,
                2,
                "Navimow API error: ".($json->{desc}//"unknown")
            );

            return;
        }

        Log3(
            $name,
            4,
            "Navimow callback successful"
        );

        if($callback)
        {
            eval
            {
                $callback->($hash,$json);
            };

            if($@)
            {
                Log3(
                    $name,
                    2,
                    "Navimow callback died: $@"
                );
            }
        }
    };

    HttpUtils_NonblockingGet(\%param);
}


###############################################################################
# Refresh OAuth Token
###############################################################################

sub Navimow_RefreshToken($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    #
    # Bereits ein Refresh aktiv?
    #
    return
        if $hash->{helper}{refreshRunning};

    $hash->{helper}{refreshRunning} = 1;

    my $refreshToken =
        AttrVal(
            $name,
            "refreshToken",
            ""
        );

    if ($refreshToken eq "") {
        Log3(
            $name,
            2,
            "Navimow $name: kein refreshToken konfiguriert"
        );

        delete $hash->{helper}{refreshRunning};

        readingsSingleUpdate(
            $hash,
            "lastError",
            "kein refreshToken konfiguriert",
            1
        );

        return;
    }

    #
    # Werte für application/x-www-form-urlencoded maskieren.
    #
    my $encodedRefreshToken = urlEncode($refreshToken);

    my %param;

    $param{url} =
        "https://navimow-fra.ninebot.com/openapi/oauth/getAccessToken";

    $param{method}  = "POST";
    $param{timeout} = 20;

    $param{header} =
          "Content-Type: application/x-www-form-urlencoded\r\n"
        . "requestId: "
        . int(rand(1000000000));

    #
    # OAuth-Konfiguration entsprechend mower-sdk /
    # Home-Assistant-Integration.
    #
    $param{data} =
          "grant_type=refresh_token"
        . "&refresh_token=" . $encodedRefreshToken
        . "&client_id=homeassistant"
        . "&client_secret=57056e15-722e-42be-bbaa-b0cbfb208a52";

    $param{hash} = $hash;

    $param{callback} = sub
    {
        my ($param, $err, $data) = @_;

        my $hash = $param->{hash};
        my $name = $hash->{NAME};

        delete $hash->{helper}{refreshRunning};

        if ($err ne "") {
            Log3(
                $name,
                2,
                "Navimow $name: refresh HTTP error: $err"
            );

            readingsSingleUpdate(
                $hash,
                "lastError",
                "OAuth-Refresh HTTP-Fehler: $err",
                1
            );

            return;
        }

        my $json;

        eval {
            $json = decode_json($data);
        };

        if ($@ || ref($json) ne "HASH") {
            my $error = $@ || "response is not a JSON object";

            $error =~ s/[\r\n]+/ /g;

            Log3(
                $name,
                2,
                "Navimow $name: refresh JSON decode error: $error"
            );

            readingsSingleUpdate(
                $hash,
                "lastError",
                "OAuth-Refresh: JSON konnte nicht dekodiert werden",
                1
            );

            return;
        }

        if (
            !exists($json->{access_token})
            || !defined($json->{access_token})
            || $json->{access_token} eq ""
        ) {
            my $message = "OAuth-Refresh fehlgeschlagen";

            if (defined($json->{message}) && $json->{message} ne "") {
                $message .= ": " . $json->{message};
            }
            elsif (defined($json->{msg}) && $json->{msg} ne "") {
                $message .= ": " . $json->{msg};
            }
            elsif (defined($json->{code}) && $json->{code} ne "") {
                $message .= ": " . $json->{code};
            }

            Log3(
                $name,
                2,
                "Navimow $name: $message"
            );

            readingsSingleUpdate(
                $hash,
                "lastError",
                $message,
                1
            );

            return;
        }

        #
        # Neue Tokens speichern.
        #
        CommandAttr(
            undef,
            "$name accessToken $json->{access_token}"
        );

        if (
            exists($json->{refresh_token})
            && defined($json->{refresh_token})
            && $json->{refresh_token} ne ""
        ) {
            CommandAttr(
                undef,
                "$name refreshToken $json->{refresh_token}"
            );
        }

        #
        # Ablaufzeitpunkt speichern, falls expires_in geliefert wird.
        #
        if (
            exists($json->{expires_in})
            && defined($json->{expires_in})
            && $json->{expires_in} =~ /^\d+$/
        ) {
            my $expiresAt =
                time()
                + $json->{expires_in};

            readingsSingleUpdate(
                $hash,
                "tokenExpires",
                FmtDateTime($expiresAt),
                1
            );

            $hash->{helper}{tokenExpiresAt} = $expiresAt;
        }

        readingsSingleUpdate(
            $hash,
            "lastError",
            "",
            0
        );

        Log3(
            $name,
            3,
            "Navimow $name: OAuth token refreshed"
        );

        #
        # Ursprünglichen REST-Request erneut ausführen.
        #
        my $request =
            $hash->{helper}{lastRequest};

        if ($request) {
            Log3(
                $name,
                3,
                "Navimow $name: retrying original request"
            );

            Navimow_Request(
                $hash,
                $request->{method},
                $request->{path},
                $request->{body},
                $request->{callback}
            );

            Log3(
                $name,
                3,
                "Navimow $name: retry dispatched"
            );
        }

        #
        # Die laufende Python-Bridge kennt noch den alten Access-Token.
        # Deshalb Bridge kontrolliert beenden und mit dem neuen Token
        # erneut starten.
        #
        if (defined(&Navimow_StopBridge)) {
            Log3(
                $name,
                3,
                "Navimow $name: Bridge wird nach OAuth-Refresh neu gestartet"
            );

            Navimow_StopBridge($hash);
        }

        if (
            defined(&Navimow_StartBridge)
            && !IsDisabled($name)
        ) {
            InternalTimer(
                gettimeofday() + 1,
                "Navimow_StartBridge",
                $hash,
                0
            );
        }

        return;
    };

    HttpUtils_NonblockingGet(\%param);

    return;
}


###############################################################################
# Request mower status
###############################################################################

sub Navimow_GetStatus($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    #
    # Der aufgerufene Timer ist abgearbeitet.
    #
    RemoveInternalTimer(
        $hash,
        "Navimow_GetStatus"
    );

    return
        if AttrVal($name, "disable", 0);

    my $interval =
        AttrVal(
            $name,
            "interval",
            60
        );

    $interval = 60
        if $interval !~ /^\d+$/ || $interval < 10;

    my $deviceId =
        AttrVal(
            $name,
            "deviceId",
            ""
        );

    if (!$deviceId)
    {
        Log3(
            $name,
            2,
            "Navimow: no deviceId configured"
        );

        #
        # Auch bei fehlender Geräte-ID weiter zyklisch prüfen.
        #
        Navimow_ScheduleStatus(
            $hash,
            $interval
        );

        return;
    }

    my $body =
        encode_json(
        {
            devices =>
            [
                {
                    id => $deviceId
                }
            ]
        });

    Navimow_Request(
        $hash,
        "POST",
        "/openapi/smarthome/getVehicleStatus",
        $body,
        sub
        {
            my ($hash, $json) = @_;

            Navimow_ParseStatus(
                $hash,
                $json
            );
        }
    );

    #
    # Nächsten regulären Statusabruf planen.
    #
    Navimow_ScheduleStatus(
        $hash,
        $interval
    );

    return;
}


###############################################################################
# Convert Navimow vehicle state to readable text
###############################################################################

sub Navimow_StateText($)
{
    my ($state) = @_;

    return "unknown"
        if !defined($state) || $state eq "";

    my %stateText =
    (
        "isDocked"       => "docked",
        "isCharging"     => "charging",
        "isMowing"       => "mowing",
        "isPaused"       => "paused",
        "isReturning"    => "returning",
        "isGoingHome"    => "returning",
        "isIdle"         => "idle",
        "isStandby"      => "standby",
        "isMapping"      => "mapping",
        "isUpdating"     => "updating",
        "isOffline"      => "offline",
        "hasError"       => "error",
        "isError"        => "error",
        "isLocked"       => "locked"
    );

    return $stateText{$state}
        if exists($stateText{$state});

    #
    # Unbekannte Zustände nicht verfälschen
    #
    return $state;
}


###############################################################################
# Parse MQTT connection information
###############################################################################

sub Navimow_ParseMQTTInfo($$)
{
    my ($hash, $json) = @_;

    my $name = $hash->{NAME};

    #
    # Grundsätzliche Prüfung der Antwort
    #
    if (
        ref($json) ne "HASH"
        ||
        ($json->{code} // 0) != 1
    )
    {
        my $desc =
            ref($json) eq "HASH"
            ? ($json->{desc} // "unknown API error")
            : "ungültige JSON-Antwort";

        Log3(
            $name,
            2,
            "Navimow MQTT info failed: $desc"
        );

        return;
    }

    #
    # Je nach API-Version können die Daten direkt unter data
    # oder zusätzlich unter data/payload liegen.
    #
    my $data = $json->{data};

    if (
        ref($data) eq "HASH"
        &&
        ref($data->{payload}) eq "HASH"
    )
    {
        $data = $data->{payload};
    }

    if (ref($data) ne "HASH")
    {
        Log3(
            $name,
            2,
            "Navimow MQTT info failed: response contains no data"
        );

        return;
    }

    my $mqttHost =
        $data->{mqttHost} // "";

    my $mqttUrl =
        $data->{mqttUrl} // "";

    my $mqttUser =
        $data->{userName} // "";

    my $mqttPassword =
        $data->{pwdInfo} // "";

    if (
        $mqttHost eq ""
        &&
        $mqttUrl eq ""
    )
    {
        Log3(
            $name,
            2,
            "Navimow MQTT info failed: mqttHost and mqttUrl are missing"
        );

        return;
    }

    if ($mqttUser eq "")
    {
        Log3(
            $name,
            2,
            "Navimow MQTT info failed: userName is missing"
        );

        return;
    }

    if ($mqttPassword eq "")
    {
        Log3(
            $name,
            2,
            "Navimow MQTT info failed: pwdInfo is missing"
        );

        return;
    }

    #
    # Alte, sichtbare Ablage entfernen.
    #
    delete $hash->{helper}{mqttPassword};

    #
    # Kennwort in einem versteckten Internal ablegen.
    # Der führende Punkt verhindert normalerweise die Anzeige
    # im regulären FHEM-list.
    #
    $hash->{".mqttPassword"} =
        $mqttPassword;

    readingsBeginUpdate($hash);

    readingsBulkUpdate(
        $hash,
        "mqttHost",
        $mqttHost
    );

    readingsBulkUpdate(
        $hash,
        "mqttUrl",
        $mqttUrl
    );

    readingsBulkUpdate(
        $hash,
        "mqttUser",
        $mqttUser
    );

    readingsBulkUpdate(
        $hash,
        "mqttInfoUpdated",
        TimeNow()
    );

    readingsEndUpdate($hash, 1);

    Log3(
        $name,
        3,
        "Navimow MQTT connection information received"
    );

    # MQTT-AUTORESTART-BEGIN
    #
    # Wenn die Bridge vor dem Eintreffen der MQTT-Credentials
    # private-only gestartet wurde, jetzt einmal kontrolliert neu starten.
    # Bei bereits aktivem MQTT ist kein Neustart erforderlich.
    #
    delete $hash->{helper}{mqttAutoInfoLastRequest};

    if (
        !IsDisabled($name)
        && !$hash->{BRIDGE_MANUAL_STOP}
        && ($hash->{helper}{mqttAutoRestartNeeded} // 0)
    ) {
        delete $hash->{helper}{mqttAutoRestartNeeded};
        Log3(
            $name,
            3,
            "Navimow $name: MQTT credentials ready; restarting bridge in hybrid mode"
        );

        RemoveInternalTimer($hash, "Navimow_StartBridge");
        Navimow_StopBridge($hash);

        InternalTimer(
            gettimeofday() + 0.5,
            "Navimow_StartBridge",
            $hash,
            0
        );
    }
    # MQTT-AUTORESTART-END

    return;
}


###############################################################################
# Parse mower status response
###############################################################################

sub Navimow_ParseStatus($$)
{
    my ($hash, $json) = @_;

    my $name = $hash->{NAME};

    Log3(
        $name,
        4,
        "Navimow ParseStatus entered"
    );

    if (ref($json) ne "HASH")
    {
        Log3(
            $name,
            2,
            "Navimow ParseStatus: invalid response"
        );

        return;
    }

    my $devices =
        $json->{data}
             ->{payload}
             ->{devices};

    if (
        ref($devices) ne "ARRAY"
        ||
        !defined($devices->[0])
        ||
        ref($devices->[0]) ne "HASH"
    )
    {
        Log3(
            $name,
            2,
            "Navimow ParseStatus: no device in response"
        );

        return;
    }

    my $device = $devices->[0];

    readingsBeginUpdate($hash);

    if (
        exists($device->{vehicleState})
        &&
        defined($device->{vehicleState})
    )
    {
        my $rawState = $device->{vehicleState};

        readingsBulkUpdate(
            $hash,
            "state_raw",
            $rawState
        );

        readingsBulkUpdate(
            $hash,
            "state",
            Navimow_StateText($rawState)
        );
    }

    if (
        ref($device->{capacityRemaining}) eq "ARRAY"
        &&
        defined($device->{capacityRemaining}[0])
        &&
        ref($device->{capacityRemaining}[0]) eq "HASH"
        &&
        defined($device->{capacityRemaining}[0]{rawValue})
    )
    {
        readingsBulkUpdate(
            $hash,
            "battery",
            $device->{capacityRemaining}[0]{rawValue}
        );
    }

    if (
        exists($device->{descriptiveCapacityRemaining})
        &&
        defined($device->{descriptiveCapacityRemaining})
    )
    {
        readingsBulkUpdate(
            $hash,
            "batteryLevel",
            $device->{descriptiveCapacityRemaining}
        );
    }

    if (
        exists($device->{id})
        &&
        defined($device->{id})
    )
    {
        readingsBulkUpdate(
            $hash,
            "deviceId",
            $device->{id}
        );
    }

    readingsBulkUpdate(
        $hash,
        "lastUpdate",
        TimeNow()
    );

    readingsEndUpdate(
        $hash,
        1
    );

    Log3(
        $name,
        4,
        "Navimow ParseStatus finished"
    );

    return;
}


###############################################################################
# Schedule next status request
###############################################################################

sub Navimow_ScheduleStatus($$)
{
    my ($hash, $delay) = @_;

    my $name = $hash->{NAME};

    return
        if AttrVal($name, "disable", 0);

    #
    # Nur den Timer für Navimow_GetStatus entfernen.
    # Andere mögliche Modultimer bleiben unangetastet.
    #
    RemoveInternalTimer(
        $hash,
        "Navimow_GetStatus"
    );

    InternalTimer(
        gettimeofday() + $delay,
        "Navimow_GetStatus",
        $hash,
        0
    );

    Log3(
        $name,
        5,
        "Navimow next status request scheduled in $delay seconds"
    );

    return;
}


###############################################################################
# Handle attribute changes
###############################################################################

sub Navimow_Attr($$$$)
{
    my ($cmd, $name, $attrName, $attrValue) = @_;

    my $hash = $defs{$name};

    return undef
        if !$hash;

    if ($attrName eq "interval")
    {
        if ($cmd eq "set")
        {
            return "Intervall muss eine Zahl größer oder gleich 10 sein"
                if !defined($attrValue)
                || $attrValue !~ /^\d+$/
                || $attrValue < 10;
        }

        #
        # Timer mit dem neuen Intervall sofort neu planen.
        #
        my $interval =
            $cmd eq "set"
                ? $attrValue
                : 60;

        Navimow_ScheduleStatus(
            $hash,
            $interval
        );

        return undef;
    }

    if ($attrName eq "disable")
    {
        if (
            $cmd eq "set"
            &&
            defined($attrValue)
            &&
            $attrValue !~ /^(0|1)$/
        )
        {
            return "disable muss 0 oder 1 sein";
        }

        if (
            $cmd eq "set"
            &&
            $attrValue
        )
        {
            RemoveInternalTimer(
                $hash,
                "Navimow_GetStatus"
            );

            Log3(
                $name,
                3,
                "Navimow polling disabled"
            );
        }
        else
        {
            Navimow_ScheduleStatus(
                $hash,
                1
            );

            Log3(
                $name,
                3,
                "Navimow polling enabled"
            );
        }

        return undef;
    }

    return undef;
}


###############################################################################
# Get MQTT connection information
###############################################################################

sub Navimow_GetMQTTInfo($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    return
        if AttrVal($name, "disable", 0);

    Navimow_Request(
        $hash,
        "GET",
        "/openapi/mqtt/userInfo/get/v2",
        undef,
        \&Navimow_ParseMQTTInfo
    );

    Log3(
        $name,
        4,
        "Navimow MQTT connection information requested"
    );

    return;
}


###############################################################################
# Prepare MQTT WebSocket connection parameters
###############################################################################

sub Navimow_MQTTPrepare($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    my $mqttHost =
        ReadingsVal(
            $name,
            "mqttHost",
            ""
        );

    my $mqttUrl =
        ReadingsVal(
            $name,
            "mqttUrl",
            ""
        );

    my $mqttUser =
        ReadingsVal(
            $name,
            "mqttUser",
            ""
        );

    my $mqttPassword =
        $hash->{".mqttPassword"} // "";

    my $accessToken =
        AttrVal(
            $name,
            "accessToken",
            ""
        );

    #
    # Pflichtangaben prüfen
    #
    if ($mqttHost eq "")
    {
        readingsSingleUpdate(
            $hash,
            "mqttState",
            "missing mqttHost",
            1
        );

        Log3(
            $name,
            2,
            "Navimow MQTT preparation failed: mqttHost is missing"
        );

        return;
    }

    if ($mqttUrl eq "")
    {
        readingsSingleUpdate(
            $hash,
            "mqttState",
            "missing mqttUrl",
            1
        );

        Log3(
            $name,
            2,
            "Navimow MQTT preparation failed: mqttUrl is missing"
        );

        return;
    }

    if ($mqttUser eq "")
    {
        readingsSingleUpdate(
            $hash,
            "mqttState",
            "missing mqttUser",
            1
        );

        Log3(
            $name,
            2,
            "Navimow MQTT preparation failed: mqttUser is missing"
        );

        return;
    }

    if ($mqttPassword eq "")
    {
        readingsSingleUpdate(
            $hash,
            "mqttState",
            "missing mqttPassword",
            1
        );

        Log3(
            $name,
            2,
            "Navimow MQTT preparation failed: MQTT password is missing"
        );

        return;
    }

    if ($accessToken eq "")
    {
        readingsSingleUpdate(
            $hash,
            "mqttState",
            "missing accessToken",
            1
        );

        Log3(
            $name,
            2,
            "Navimow MQTT preparation failed: accessToken is missing"
        );

        return;
    }

    #
    # mqttHost normalisieren.
    #
    # Erwartete Formen:
    #
    #   wss://mqtt-fra.navimow.com
    #   ws://mqtt-fra.navimow.com
    #   mqtt-fra.navimow.com
    #
    my $scheme = "wss";
    my $host   = $mqttHost;
    my $port   = 443;

    if ($host =~ m{^(wss?)://(.+)$}i)
    {
        $scheme = lc($1);
        $host   = $2;
    }

    #
    # Eventuell im Host angegebene Portnummer übernehmen.
    #
    if ($host =~ /^([^:\/]+):(\d+)$/)
    {
        $host = $1;
        $port = int($2);
    }
    else
    {
        $port =
            $scheme eq "wss"
            ? 443
            : 80;
    }

    #
    # WebSocket-Pfad normalisieren.
    #
    my $path = $mqttUrl;

    if ($path =~ m{^wss?://[^/]+(/.*)$}i)
    {
        $path = $1;
    }

    $path = "/" . $path
        if ($path !~ m{^/});

    #
    # Client-ID erzeugen.
    #
    # Sie darf innerhalb einer Broker-Verbindung nicht mit einem
    # anderen aktiven MQTT-Client kollidieren.
    #
    my $deviceId =
        AttrVal(
            $name,
            "deviceId",
            ReadingsVal(
                $name,
                "deviceId",
                ""
            )
        );

    my $clientId =
          "fhem_"
        . ($deviceId ne "" ? $deviceId : $name)
        . "_"
        . int(rand(1_000_000));

    $clientId =~ s/[^A-Za-z0-9_-]/_/g;

    #
    # Verbindungsparameter intern ablegen.
    #
    # Sensible Werte bleiben in versteckten Internals.
    #
    $hash->{helper}{mqtt}{host}      = $host;
    $hash->{helper}{mqtt}{port}      = $port;
    $hash->{helper}{mqtt}{path}      = $path;
    $hash->{helper}{mqtt}{scheme}    = $scheme;
    $hash->{helper}{mqtt}{tls}       = $scheme eq "wss" ? 1 : 0;
    $hash->{helper}{mqtt}{user}      = $mqttUser;
    $hash->{helper}{mqtt}{clientId}  = $clientId;
    $hash->{helper}{mqtt}{keepAlive} = 2400;

    $hash->{".mqttAuthorization"} =
        "Bearer " . $accessToken;

    readingsBeginUpdate($hash);

    readingsBulkUpdate(
        $hash,
        "mqttBroker",
        $host . ":" . $port
    );

    readingsBulkUpdate(
        $hash,
        "mqttWebSocketPath",
        $path
    );

    readingsBulkUpdate(
        $hash,
        "mqttClientId",
        $clientId
    );

    readingsBulkUpdate(
        $hash,
        "mqttState",
        "prepared"
    );

    readingsEndUpdate($hash, 1);

    Log3(
        $name,
        3,
          "Navimow MQTT parameters prepared: "
        . "host=$host "
        . "port=$port "
        . "path=$path "
        . "tls="
        . ($scheme eq "wss" ? "yes" : "no")
        . " clientId=$clientId"
    );

    return;
}


###############################################################################
# Überwache Bereitschaft der Python-Bridge
###############################################################################

sub Navimow_BridgeReady($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    return undef if $hash->{BRIDGE_MANUAL_STOP};
    
    return undef if IsDisabled($name);

    #
    # Falls die Bridge als laufend markiert ist, prüfen wir zusätzlich
    # den letzten empfangenen Heartbeat.
    #
    # Der Python-Heartbeat wird alle 60 Sekunden gesendet. Mit einem
    # Grenzwert von 150 Sekunden werden zwei ausgefallene Heartbeats
    # toleriert, bevor die Bridge neu gestartet wird.
    #
    if (
        defined($hash->{BRIDGE_RUNNING})
        && defined($hash->{BRIDGE_LAST_HEARTBEAT})
    ) {
        my $heartbeatTimeout = AttrVal(
            $name,
            "bridgeHeartbeatTimeout",
            150
        );

        $heartbeatTimeout = 150
            if $heartbeatTimeout !~ /^\d+(?:\.\d+)?$/
            || $heartbeatTimeout < 90;

        my $heartbeatAge =
            gettimeofday()
            - $hash->{BRIDGE_LAST_HEARTBEAT};

        if ($heartbeatAge > $heartbeatTimeout) {
            #
            # Während bereits ein Neustart vorgemerkt ist, keinen
            # weiteren Neustart auslösen.
            #
            return undef
                if defined($hash->{BRIDGE_RESTART_PENDING});

            Log3(
                $name,
                3,
                "Navimow $name: bridge heartbeat timeout after "
                . int($heartbeatAge)
                . " seconds, scheduling restart"
            );

            delete $hash->{BRIDGE_RUNNING};
            delete $hash->{BRIDGE_LAST_HEARTBEAT};

            readingsBeginUpdate($hash);

            readingsBulkUpdate(
                $hash,
                "bridgeState",
                "heartbeatTimeout"
            );

            readingsBulkUpdate(
                $hash,
                "bridgeHeartbeatAge",
                int($heartbeatAge)
            );

            readingsEndUpdate(
                $hash,
                1
            );

            Navimow_StopBridge($hash);

            my $restartInterval = AttrVal(
                $name,
                "bridgeRestartInterval",
                30
            );

            $restartInterval = 30
                if $restartInterval !~ /^\d+(?:\.\d+)?$/
                || $restartInterval < 1;

            $hash->{BRIDGE_RESTART_PENDING} = 1;

            InternalTimer(
                gettimeofday() + $restartInterval,
                "Navimow_BridgeRestart",
                $hash,
                0
            );

            return undef;
        }
    }

    #
    # Solange Prozess und Dateideskriptor vorhanden sind,
    # besteht kein weiterer Handlungsbedarf.
    #
    if (
        defined($hash->{BRIDGE_PID})
        && $hash->{BRIDGE_PID} > 0
        && kill(0, $hash->{BRIDGE_PID})
        && defined($hash->{FD})
    ) {
        return undef;
    }

    #
    # Während bereits ein Neustart-Timer vorgemerkt ist,
    # keinen weiteren Start auslösen.
    #
    return undef if defined($hash->{BRIDGE_RESTART_PENDING});

    Log3(
        $name,
        3,
        "Navimow $name: bridge is not running, scheduling restart"
    );

    readingsSingleUpdate(
        $hash,
        "bridgeState",
        "restarting",
        1
    );

    Navimow_StopBridge($hash);

    my $restartInterval = AttrVal(
        $name,
        "bridgeRestartInterval",
        30
    );

    $restartInterval = 30
        if $restartInterval !~ /^\d+(?:\.\d+)?$/
        || $restartInterval < 1;

    $hash->{BRIDGE_RESTART_PENDING} = 1;

    InternalTimer(
        gettimeofday() + $restartInterval,
        "Navimow_BridgeRestart",
        $hash,
        0
    );

    return undef;
}


###############################################################################
# Neustart der Python-Bridge nach Wartezeit
###############################################################################

sub Navimow_BridgeRestart($)
{
    my ($hash) = @_;

    delete $hash->{BRIDGE_RESTART_PENDING};

    return if IsDisabled($hash->{NAME});
    return if $hash->{BRIDGE_MANUAL_STOP};

    Navimow_StartBridge($hash);

    return;
}



###############################################################################
# Überwache Bridge-Prozess und Heartbeat
###############################################################################

sub Navimow_BridgeWatchdog($)
{
    my ($hash) = @_;

    my $name = $hash->{NAME};

    #
    # Der Timer ist ein Einmal-Timer und wird am Ende der Prüfung
    # bei weiterhin gesundem Zustand erneut eingeplant.
    #
    RemoveInternalTimer(
        $hash,
        "Navimow_BridgeWatchdog"
    );

    return if IsDisabled($name);
    return if $hash->{BRIDGE_MANUAL_STOP};

    #
    # Während bereits ein Neustart vorgesehen ist, darf der
    # Watchdog keinen weiteren Neustart auslösen.
    #
    return if defined($hash->{BRIDGE_RESTART_PENDING});

    my $watchdogInterval = AttrVal(
        $name,
        "bridgeWatchdogInterval",
        90
    );

    $watchdogInterval = 90
        if $watchdogInterval !~ /^\d+(?:\.\d+)?$/
        || $watchdogInterval < 30;

    my $heartbeatTimeout = AttrVal(
        $name,
        "bridgeHeartbeatTimeout",
        150
    );

    #
    # Der Python-Heartbeat wird alle 60 Sekunden gesendet.
    # Werte unter 90 Sekunden wären daher unnötig empfindlich.
    #
    $heartbeatTimeout = 150
        if $heartbeatTimeout !~ /^\d+(?:\.\d+)?$/
        || $heartbeatTimeout < 90;

    my $now = gettimeofday();

    #
    # Zuerst prüfen, ob der Python-Prozess überhaupt noch existiert.
    #
    my $processRunning =
        defined($hash->{BRIDGE_PID})
        && $hash->{BRIDGE_PID} > 0
        && kill(0, $hash->{BRIDGE_PID});

    my $restartReason;
    my $heartbeatAge;

    if (!$processRunning) {
        $restartReason = "processStopped";
    }
    elsif (defined($hash->{BRIDGE_LAST_HEARTBEAT})) {
        $heartbeatAge =
            $now - $hash->{BRIDGE_LAST_HEARTBEAT};

        if ($heartbeatAge > $heartbeatTimeout) {
            $restartReason = "heartbeatTimeout";
        }
    }
    elsif (defined($hash->{BRIDGE_STARTED})) {
        #
        # Nach einem Neustart existiert zunächst noch kein Heartbeat.
        # Der Startzeitpunkt dient während dieser Anlaufphase als
        # Referenz für den Timeout.
        #
        $heartbeatAge =
            $now - $hash->{BRIDGE_STARTED};

        if ($heartbeatAge > $heartbeatTimeout) {
            $restartReason = "heartbeatNotReceived";
        }
    }
    else {
        #
        # Ein Prozess ohne Startzeit und ohne Heartbeat stellt einen
        # inkonsistenten internen Zustand dar.
        #
        $restartReason = "invalidBridgeState";
    }

    #
    # Erweiterter Gesundheitscheck: Prozess + Heartbeat koennen gesund wirken,
    # obwohl die Bridge logisch festhaengt. Bei verbundener Private-Cloud
    # erwarten wir weiterhin Location-Meldungen.
    #
    if (
        !defined($restartReason)
        && defined($hash->{BRIDGE_PRIVATE_CLOUD_STATE})
        && $hash->{BRIDGE_PRIVATE_CLOUD_STATE} eq "connected"
    ) {
        my $locationTimeout = 600;
        my $locationAge;

        if (defined($hash->{BRIDGE_LAST_LOCATION})) {
            $locationAge = $now - $hash->{BRIDGE_LAST_LOCATION};

            if ($locationAge > $locationTimeout) {
                $restartReason = "locationTimeout";
                $heartbeatAge = $locationAge;
            }
        }
        elsif (
            defined($hash->{BRIDGE_STARTED})
            && ($now - $hash->{BRIDGE_STARTED}) > $locationTimeout
        ) {
            $restartReason = "locationNotReceived";
            $heartbeatAge = $now - $hash->{BRIDGE_STARTED};
        }
    }

    if (defined($restartReason)) {
        my $logMessage =
            "Navimow $name: bridge watchdog detected $restartReason";

        if (defined($heartbeatAge)) {
            $logMessage .=
                " after "
                . int($heartbeatAge)
                . " seconds";
        }

        $logMessage .= ", scheduling restart";

        Log3(
            $name,
            3,
            $logMessage
        );

        readingsBeginUpdate($hash);

        readingsBulkUpdate(
            $hash,
            "bridgeState",
            $restartReason
        );

        if (defined($heartbeatAge)) {
            readingsBulkUpdate(
                $hash,
                "bridgeHeartbeatAge",
                int($heartbeatAge)
            );
        }

        readingsEndUpdate(
            $hash,
            1
        );

        #
        # Schutz gegen Restart-Schleifen:
        # maximal 3 automatische Watchdog-Restarts innerhalb einer Stunde.
        #
        my $windowSeconds = 3600;
        my $maxRestarts   = 3;

        $hash->{BRIDGE_WATCHDOG_RESTARTS} = []
            if ref($hash->{BRIDGE_WATCHDOG_RESTARTS}) ne "ARRAY";

        my @recentRestarts = grep {
            defined($_) && ($now - $_) < $windowSeconds
        } @{$hash->{BRIDGE_WATCHDOG_RESTARTS}};

        if (@recentRestarts >= $maxRestarts) {
            $hash->{BRIDGE_WATCHDOG_RESTARTS} = \@recentRestarts;

            readingsBeginUpdate($hash);
            readingsBulkUpdate($hash, "bridgeWatchdogState", "blocked");
            readingsBulkUpdate($hash, "bridgeWatchdogReason", $restartReason);
            readingsBulkUpdate(
                $hash,
                "bridgeWatchdogRestartCount",
                scalar(@recentRestarts)
            );
            readingsEndUpdate($hash, 1);

            Log3(
                $name,
                2,
                "Navimow $name: bridge watchdog restart blocked after "
                . scalar(@recentRestarts)
                . " automatic restarts within 3600 seconds"
            );

            InternalTimer(
                $now + $watchdogInterval,
                "Navimow_BridgeWatchdog",
                $hash,
                0
            );

            return;
        }

        push @recentRestarts, $now;
        $hash->{BRIDGE_WATCHDOG_RESTARTS} = \@recentRestarts;

        readingsBeginUpdate($hash);
        readingsBulkUpdate($hash, "bridgeWatchdogState", "restarting");
        readingsBulkUpdate($hash, "bridgeWatchdogReason", $restartReason);
        readingsBulkUpdate(
            $hash,
            "bridgeWatchdogRestartCount",
            scalar(@recentRestarts)
        );
        readingsEndUpdate($hash, 1);

        Navimow_StopBridge($hash);

        my $restartInterval = AttrVal(
            $name,
            "bridgeRestartInterval",
            30
        );

        $restartInterval = 30
            if $restartInterval !~ /^\d+(?:\.\d+)?$/
            || $restartInterval < 1;

        $hash->{BRIDGE_RESTART_PENDING} = 1;

        InternalTimer(
            gettimeofday() + $restartInterval,
            "Navimow_BridgeRestart",
            $hash,
            0
        );

        return;
    }

    #
    # Bridge, Heartbeat und Datenfluss sind in Ordnung.
    #
    if (ReadingsVal($name, "bridgeWatchdogState", "") ne "healthy") {
        readingsBeginUpdate($hash);
        readingsBulkUpdate($hash, "bridgeWatchdogState", "healthy");
        readingsBulkUpdate($hash, "bridgeWatchdogReason", "");
        readingsEndUpdate($hash, 1);
    }

    #
    # Den nächsten Watchdog-Durchlauf einplanen.
    #
    InternalTimer(
        $now + $watchdogInterval,
        "Navimow_BridgeWatchdog",
        $hash,
        0
    );

    return;
}



###############################################################################
# FHEMWEB detail view
###############################################################################

sub Navimow_FW_detailFn($$$$)
{
    my ($FW_wname, $name, $room, $pageHash) = @_;
    my $hash = $main::defs{$name};
    return "" if !defined($hash);

    my $safeName = $name;
    $safeName =~ s/[^A-Za-z0-9_-]/_/g;

    my $stageId  = "navimow-live-stage-" . $safeName;
    my $worldId  = "navimow-live-world-" . $safeName;
    my $mapId    = "navimow-live-map-" . $safeName;
    my $mowerId  = "navimow-live-mower-" . $safeName;
    my $statusId = "navimow-live-status-" . $safeName;
    my $centerId = "navimow-live-center-" . $safeName;

    my $mapUrl   = "/fhem/images/navimow/live/navimow_base.svg";
    my $stateUrl = "/fhem/images/navimow/live/navimow_state.js";
    my $jsUrl    = "/fhem/pgm2/navimow_live.js?v=1.6.0";
    my $language = AttrVal($name, "privateLiveLanguage", "auto");
    $language = "auto" if $language !~ /^(?:auto|de|en)$/;

    my $html = <<"EOF";
<style>
\@keyframes navimow-disc-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.navimow-mowing-disc {
  width:28px;height:28px;border-radius:50%;box-sizing:border-box;
  border:3px solid currentColor;position:relative;display:inline-block;
  flex:0 0 28px;
}
.navimow-mowing-disc:before,.navimow-mowing-disc:after {
  content:"";position:absolute;left:50%;top:50%;width:18px;height:2px;
  background:currentColor;transform-origin:center;
}
.navimow-mowing-disc:before { transform:translate(-50%,-50%); }
.navimow-mowing-disc:after { transform:translate(-50%,-50%) rotate(90deg); }
.navimow-mowing-disc-active { animation:navimow-disc-spin .55s linear infinite; }
</style>

<div class="navimow-fhem-live" style="max-width:900px;margin:0 0 1em 0;">
  <div id="$stageId" style="position:relative;width:100%;overflow:hidden;
       touch-action:none;cursor:grab;user-select:none;">
    <div id="$worldId" style="position:relative;width:100%;
         transform-origin:0 0;will-change:transform;">
      <img id="$mapId" src="$mapUrl" alt="Navimow map" draggable="false"
           style="display:block;width:100%;height:auto;pointer-events:none;">
      <img id="$mowerId" alt="Navimow" draggable="false"
           style="display:none;position:absolute;left:0;top:0;
           transform-origin:center center;pointer-events:none;">
    </div>
  </div>

  <div id="$statusId" style="box-sizing:border-box;width:100%;padding:12px 4px 4px;">

    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
         gap:12px 24px;margin:4px 0 14px;">

      <div data-navimow-schedule-next
           style="display:none;align-items:center;gap:10px;min-width:0;">
        <span style="font-size:1.35em;line-height:1;flex:0 0 auto;"
              aria-hidden="true">&#128197;</span>
        <div style="min-width:0;">
          <div data-navimow-field="scheduleNextDisplay"
               style="font-size:1.12em;font-weight:600;
               overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">&ndash;</div>
          <div data-navimow-i18n="nextMowing"
               style="opacity:.7;font-size:.88em;">Next mowing</div>
        </div>
      </div>

      <div style="display:flex;align-items:center;gap:10px;min-width:0;">
        <span class="navimow-mowing-disc" data-navimow-mowing-disc></span>
        <div style="min-width:0;">
          <div data-navimow-field="taskType"
               style="font-size:1.12em;font-weight:600;
               overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">&ndash;</div>
          <div data-navimow-i18n="mowingTask"
               style="opacity:.7;font-size:.88em;">Mowing task</div>
        </div>
      </div>

    </div>

    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
      <div style="flex:1;min-width:0;">
        <div data-navimow-field="status"
             style="font-size:1.35em;font-weight:600;
             overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">&ndash;</div>
        <div data-navimow-i18n="status"
             style="opacity:.7;font-size:.88em;">Status</div>
      </div>
      <button id="$centerId" type="button" data-navimow-i18n="center"
              style="cursor:pointer;padding:.45em .8em;">Center</button>
    </div>

    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 24px;">
      <div>
        <div data-navimow-field="mowingWeekArea" style="font-size:1.3em;font-weight:600;">&ndash;</div>
        <div data-navimow-i18n="weekArea" style="opacity:.7;font-size:.88em;">Week area</div>
      </div>
      <div>
        <div data-navimow-field="batterySoc" style="font-size:1.3em;font-weight:600;">&ndash;</div>
        <div data-navimow-i18n="batterySoc" style="opacity:.7;font-size:.88em;">Battery</div>
      </div>
      <div>
        <div data-navimow-field="mowingPercentage" style="font-size:1.15em;font-weight:600;">&ndash;</div>
        <div data-navimow-i18n="mowingProgress" style="opacity:.7;font-size:.88em;">Progress</div>
      </div>
      <div>
        <div>
          <span data-navimow-field="batteryWindow" style="font-size:1.15em;font-weight:600;">&ndash;</span>
          <span data-navimow-i18n="relative" style="opacity:.65;">relative</span>
        </div>
        <div style="opacity:.7;font-size:.88em;">
          <span data-navimow-i18n="workWindow">Working window</span>
          <span data-navimow-field="batteryRange">&ndash;</span>
        </div>
      </div>
    </div>
  </div>
</div>

<script src="$jsUrl"></script>
<script>
(function () {
    function startNavimowLive() {
        var stage = document.getElementById("$stageId");
        if (!stage) return;
        if (!window.NavimowLive) {
            window.setTimeout(startNavimowLive, 50);
            return;
        }
        if (stage.getAttribute("data-navimow-started") === "1") return;
        stage.setAttribute("data-navimow-started", "1");
        window.NavimowLive.init({
            stageId:"$stageId", worldId:"$worldId", mapId:"$mapId",
            mowerId:"$mowerId", statusRootId:"$statusId",
            centerButtonId:"$centerId", mapUrl:"$mapUrl",
            stateUrl:"$stateUrl", language:"$language"
        });
    }
    startNavimowLive();
})();
</script>
EOF
    return $html;
}

1;
