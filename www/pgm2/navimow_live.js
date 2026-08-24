/*
##############################################################################
#
# Navimow Digital Twin
#
# Module      : navimow_live.js
# Version     : 1.6.0
# Project     : 1.0.0
# Created     : 2026-08-11
# Last Change : 2026-08-11
#
# Description :
# Shared browser-side live-map layer for FHEMWEB and SmartVisu.
#
# Change History
#
# 1.6.0   2026-08-16
#   Added:
#     - Upcoming scheduled mowing presentation in the shared live status panel
#     - Localized "Next mowing" label
#     - Today/day-aware compact schedule formatting
#   Changed:
#     - Schedule block hidden when the weekly plan is disabled or has no next run
#
# --------------
#
# 1.5.0  2026-08-11
# Changed:
# - Unified mowing task and operating state into one visible activity line
# - Separate raw Status row is hidden to avoid contradictory UI
# - Center/reset button removed from the UI
# - Double-click on the map resets/centers the map view
#
# 1.4.1  2026-08-11
# Fixed:
# - Localized raw motion states: moving, turning, standing
# - Active mowing work overrides standing/moving/turning in visible status
#
# 1.4.0  2026-08-11
# Fixed:
# - Movement-derived mower heading corrected by 180 degrees for the current icon
# - Direction now reacts to the newest real movement segment in curves
# - Removed the extra one-real-point display buffer that caused stop/catch-up
# - German translation for interrupted mowing task
# Added:
# - Docked mower is shown as charging while SOC is below configured charge limit
#
# 1.3.0  2026-08-11
# Changed:
# - Visible mower heading follows the real movement vector while moving
# - Heading is smoothed across recent real positions to reduce saw-tooth turns
# - posture/renderer angle remains fallback while stationary
# - task state 3/5 is shown as an interrupted mowing task
#
# 1.1.0  2026-08-11
#   Added:
#   - Optional reusable live status panel binding
#   - German motion/status labels with raw-value fallback
#   - Battery SOC, usable battery window and charge range display
#   - Weekly mowing area and mowing progress display
#   - Optional center/reset button binding
#
# 1.0.0  2026-08-11
#   Added:
#   - Shared mower overlay, interpolation, zoom, pan and map refresh
#
##############################################################################
*/
(function (global) {
    "use strict";

    const instances = [];

    global.NavimowSmoothLive = global.NavimowSmoothLive || {};
    global.NavimowSmoothLive.push = function (state) {
        instances.forEach(function (instance) {
            instance.accept(state);
        });
    };

    function resolveElement(value) {
        if (!value) return null;
        return typeof value === "string" ? document.getElementById(value) : value;
    }

    function cacheBuster(url) {
        return url + (url.indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now();
    }

    const TRANSLATIONS = {
        de: {
            status: "Status", center: "Zentrieren",
            weekArea: "M\u00e4hfl\u00e4che Woche", batterySoc: "Akku (SOC)",
            mowingProgress: "M\u00e4hfortschritt", workWindow: "Arbeitsfenster",
            relative: "relativ", mowingTask: "M\u00e4hauftrag",
            nextMowing: "N\u00e4chster M\u00e4hvorgang",
            taskNone: "Kein aktiver M\u00e4hauftrag",
            taskOneTime: "Einmaliges M\u00e4hen",
            taskScheduled: "Geplantes M\u00e4hen",
            taskUnknown: "Aktiver M\u00e4hauftrag",
            taskInterrupted: "M\u00e4hauftrag unterbrochen",
            motionDocked: "Geparkt", motionCharging: "L\u00e4dt",
            motionMowing: "M\u00e4ht", motionPaused: "Pausiert",
            motionReturning: "R\u00fcckfahrt", motionIdle: "Bereit",
            motionStopped: "Gestoppt", motionError: "St\u00f6rung",
            motionMoving: "F\u00e4hrt", motionTurning: "Dreht",
            motionStanding: "Steht", motionUnknown: "Unbekannt"
        },
        en: {
            status: "Status", center: "Center",
            weekArea: "Mowed area this week", batterySoc: "Battery (SOC)",
            mowingProgress: "Mowing progress", workWindow: "Working window",
            relative: "relative", mowingTask: "Mowing task",
            nextMowing: "Next mowing",
            taskNone: "No active mowing task",
            taskOneTime: "One-time mowing",
            taskScheduled: "Scheduled mowing",
            taskUnknown: "Active mowing task",
            taskInterrupted: "Mowing task interrupted",
            motionDocked: "Docked", motionCharging: "Charging",
            motionMowing: "Mowing", motionPaused: "Paused",
            motionReturning: "Returning", motionIdle: "Ready",
            motionStopped: "Stopped", motionError: "Error",
            motionMoving: "Moving", motionTurning: "Turning",
            motionStanding: "Standing", motionUnknown: "Unknown"
        }
    };

    function resolveLanguage(value) {
        const requested = String(value || "auto").toLowerCase();
        if (TRANSLATIONS[requested]) return requested;
        const browserLanguage = String(
            (window.navigator && window.navigator.language) || "en"
        ).toLowerCase();
        return browserLanguage.indexOf("de") === 0 ? "de" : "en";
    }

    function translate(language, key) {
        return (TRANSLATIONS[language] && TRANSLATIONS[language][key])
            || TRANSLATIONS.en[key] || key;
    }

    function applyTranslations(root, language) {
        if (!root) return;
        root.querySelectorAll("[data-navimow-i18n]").forEach(function (element) {
            element.textContent = translate(
                language,
                element.getAttribute("data-navimow-i18n")
            );
        });
    }

    function numberOrNull(value) {
        if (value === null || value === undefined || value === "") return null;
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function formatNumber(value, decimals) {
        const number = numberOrNull(value);
        if (number === null) return "\u2013";
        return number.toLocaleString(
            String((window.navigator && window.navigator.language) || "de-DE"),
            {
                minimumFractionDigits: 0,
                maximumFractionDigits: decimals
            }
        );
    }

    function motionLabel(value, language) {
        const raw = String(value || "").trim();
        const key = raw.toLowerCase();
        const labels = {
            docked:"motionDocked", dock:"motionDocked", charging:"motionCharging",
            mowing:"motionMowing", working:"motionMowing", paused:"motionPaused",
            pause:"motionPaused", returning:"motionReturning",
            return_to_dock:"motionReturning", returning_to_dock:"motionReturning",
            going_home:"motionReturning", idle:"motionIdle", stopped:"motionStopped",
            moving:"motionMoving", turning:"motionTurning", standing:"motionStanding",
            error:"motionError"
        };
        return labels[key]
            ? translate(language, labels[key])
            : (raw || translate(language, "motionUnknown"));
    }

    function effectiveMotionLabel(state, language) {
        const area = String(state.area || "").toLowerCase();
        const motion = String(state.motion || "").toLowerCase();
        const soc = numberOrNull(state.batterySoc);
        const chargeLimit = numberOrNull(state.batteryChargeLimit);

        const atDock = area === "dock" || motion === "docked" || motion === "dock";
        if (
            atDock
            && soc !== null
            && chargeLimit !== null
            && soc < chargeLimit - 0.1
        ) {
            return translate(language, "motionCharging");
        }

        return motionLabel(state.motion, language);
    }

    function taskType(state) {
        const plan = String(state.planStatus ?? "");
        const task = String(state.taskStatus ?? "");
        if (plan === "3" && task === "7") return "oneTime";
        if (plan === "2" && task === "2") return "scheduled";
        if (plan === "3" && task === "5") return "interrupted";
        if (plan === "3" && task === "6") return "none";
        return task && task !== "6" ? "unknown" : "none";
    }

    function setText(root, field, value) {
        if (!root) return;
        const element = root.querySelector('[data-navimow-field="' + field + '"]');
        if (element) element.textContent = value;
    }

    function unifiedActivityText(state, language, activity) {
        const area = String(state.area || "").toLowerCase();
        const motion = String(state.motion || "").toLowerCase();
        const soc = numberOrNull(state.batterySoc);
        const limit = numberOrNull(state.batteryChargeLimit);
        const atDock = area === "dock" || motion === "docked" || motion === "dock";

        if (atDock && soc !== null && limit !== null && soc < limit - 0.1) {
            return translate(language, "motionCharging");
        }
        if (activity && activity.mowingActive) {
            return translate(language, "motionMowing");
        }
        if (motion === "returning" || motion === "going_home" || area === "tunnel") {
            return translate(language, "motionReturning");
        }
        if (atDock) return translate(language, "motionDocked");
        if (motion === "moving") return translate(language, "motionMoving");
        if (motion === "turning") return translate(language, "motionTurning");
        if (motion === "paused") return translate(language, "motionPaused");
        if (motion === "error") return translate(language, "motionError");
        return translate(language, "motionStanding");
    }

    function updateStatusPanel(root, state, language, activity) {
        if (!root || !state) return;

        setText(root, "status", unifiedActivityText(state, language, activity));
        const statusField = root.querySelector('[data-navimow-field="status"]');
        if (statusField) {
            const statusRow = statusField.parentElement;
            if (statusRow) statusRow.style.display = "none";
        }

        const soc = numberOrNull(state.batterySoc);
        setText(
            root,
            "batterySoc",
            soc === null ? "\u2013" : formatNumber(soc, 0) + " %"
        );

        const batteryWindow = numberOrNull(state.batteryWindowPercent);
        setText(
            root,
            "batteryWindow",
            batteryWindow === null
                ? "\u2013"
                : formatNumber(batteryWindow, 0) + " %"
        );

        const low = numberOrNull(state.batteryReturnLevel);
        const high = numberOrNull(state.batteryChargeLimit);
        setText(
            root,
            "batteryRange",
            low === null || high === null
                ? "\u2013"
                : formatNumber(low, 0) + "\u2013" + formatNumber(high, 0) + " %"
        );

        const weekArea = numberOrNull(state.mowingWeekArea);
        setText(
            root,
            "mowingWeekArea",
            weekArea === null
                ? "\u2013"
                : formatNumber(weekArea, 2) + " m\u00b2"
        );

        const percentage = numberOrNull(state.mowingPercentage);
        setText(
            root,
            "mowingPercentage",
            percentage === null ? "\u2013" : formatNumber(percentage, 0) + " %"
        );

        const type = taskType(state);
        const taskKey = {
            none:"taskNone", oneTime:"taskOneTime",
            scheduled:"taskScheduled", interrupted:"taskInterrupted",
            unknown:"taskUnknown"
        }[type] || "taskUnknown";
        const taskLabel = translate(language, taskKey);
        const activityLabel = unifiedActivityText(state, language, activity);
        const unifiedLabel = type === "none"
            ? activityLabel
            : taskLabel + " · " + activityLabel;
        setText(root, "taskType", unifiedLabel);

        const scheduleBox = root.querySelector("[data-navimow-schedule-next]");
        const scheduleEnabled =
            state.scheduleEnabled === true ||
            state.scheduleEnabled === 1 ||
            state.scheduleEnabled === "1";

        const nextDay = String(state.scheduleNextDay || "").trim();
        const nextStart = String(state.scheduleNextStart || "").trim();
        const nextEnd = String(state.scheduleNextEnd || "").trim();
        const nextDate = String(state.scheduleNextDate || "").trim();

        let nextDisplay = "";

        if (scheduleEnabled && nextStart) {
            const now = new Date();
            const yyyy = String(now.getFullYear());
            const mm = String(now.getMonth() + 1).padStart(2, "0");
            const dd = String(now.getDate()).padStart(2, "0");
            const today = yyyy + "-" + mm + "-" + dd;

            if (nextDate && nextDate === today) {
                nextDisplay =
                    (language === "de" ? "Heute " : "Today ") +
                    nextStart;
            } else {
                const shortDaysDe = {
                    Sonntag:"So.", Montag:"Mo.", Dienstag:"Di.",
                    Mittwoch:"Mi.", Donnerstag:"Do.",
                    Freitag:"Fr.", Samstag:"Sa."
                };
                const shortDaysEn = {
                    Sunday:"Sun.", Monday:"Mon.", Tuesday:"Tue.",
                    Wednesday:"Wed.", Thursday:"Thu.",
                    Friday:"Fri.", Saturday:"Sat."
                };

                let dayLabel = nextDay;
                if (language === "de" && shortDaysDe[nextDay]) {
                    dayLabel = shortDaysDe[nextDay];
                } else if (language === "en" && shortDaysEn[nextDay]) {
                    dayLabel = shortDaysEn[nextDay];
                }

                nextDisplay = dayLabel
                    ? dayLabel + " " + nextStart
                    : nextStart;
            }

            if (nextEnd) {
                nextDisplay += " \u2013 " + nextEnd;
            }
        }

        setText(root, "scheduleNextDisplay", nextDisplay || "\u2013");

        if (scheduleBox) {
            scheduleBox.style.display =
                scheduleEnabled && nextStart ? "flex" : "none";
        }

        const disc = root.querySelector("[data-navimow-mowing-disc]");
        if (disc) {
            disc.classList.toggle(
                "navimow-mowing-disc-active",
                Boolean(activity && activity.mowingActive)
            );
            disc.style.opacity = type === "none" ? "0.35" : "1";
        }
    }

    function createInstance(options) {
        const stage = resolveElement(options.stage || options.stageId);
        const world = resolveElement(options.world || options.worldId);
        const mapImage = resolveElement(options.map || options.mapId);
        const mowerImage = resolveElement(options.mower || options.mowerId);
        const statusRoot = resolveElement(
            options.statusRoot || options.statusRootId
        );
        const centerButton = resolveElement(
            options.centerButton || options.centerButtonId
        );
        const language = resolveLanguage(options.language);
        applyTranslations(statusRoot, language);

        if (!stage || !world || !mapImage || !mowerImage) {
            throw new Error("NavimowLive: required viewport elements are missing");
        }

        // The former center/reset button is intentionally removed.
        // Map reset/centering is available by double-clicking the map.
        if (centerButton) {
            centerButton.remove();
        }

        const MAP_URL = String(options.mapUrl || mapImage.getAttribute("src") || "");
        const STATE_URL = String(options.stateUrl || "");
        const STATE_POLL_MS = Number(options.statePollMs || 500);
        const MAP_REFRESH_MS = Number(options.mapRefreshMs || 2000);
        const FALLBACK_SEGMENT_MS = Number(options.fallbackSegmentMs || 2000);
        const MIN_SEGMENT_MS = Number(options.minSegmentMs || 800);
        const MAX_SEGMENT_MS = Number(options.maxSegmentMs || 3500);
        const MIN_ZOOM = Number(options.minZoom || 1.0);
        const MAX_ZOOM = Number(options.maxZoom || 6.0);
        const ZOOM_STEP = Number(options.zoomStep || 1.18);
        const PAN_MIN_VISIBLE = Math.max(24, Number(options.panMinVisible || 48));
        const VIEW_ROTATION = options.viewRotation === undefined ? 30 : Number(options.viewRotation);
        const VIEW_ROTATION_RAD = VIEW_ROTATION * Math.PI / 180.0;
        const PAN_EDGE_ALLOWANCE = Math.max(
            0.0,
            Math.min(0.35, Number(
                options.panEdgeAllowance === undefined ? 0.14 : options.panEdgeAllowance
            ))
        );

        /*
         * Pan/zoom and rotation must live on different DOM layers:
         *   stage -> world (screen-aligned pan/zoom) -> rotationPlane -> map+mower
         *
         * This keeps mouse/touch drag horizontal/vertical even when the map is
         * visually rotated.
         */
        let rotationPlane = null;
        if (Math.abs(VIEW_ROTATION) > 0.0001) {
            rotationPlane = document.createElement("div");
            rotationPlane.className = "navimow-rotation-plane";
            rotationPlane.style.position = "relative";
            rotationPlane.style.display = "block";
            rotationPlane.style.width = "100%";
            rotationPlane.style.height = "auto";
            rotationPlane.style.margin = "0";
            rotationPlane.style.padding = "0";
            rotationPlane.style.transformOrigin = "center center";
            rotationPlane.style.transform =
                "rotate(" + VIEW_ROTATION.toFixed(3) + "deg)";

            while (world.firstChild) {
                rotationPlane.appendChild(world.firstChild);
            }
            world.appendChild(rotationPlane);

            /*
             * map and mower were formerly direct children of world.
             * Keep the mower absolutely positioned relative to the new
             * rotationPlane and make sure it is not hidden by inherited
             * smartVISU/FHEMWEB image rules.
             */
            mowerImage.style.position = "absolute";
            mowerImage.style.zIndex = "20";
            mowerImage.style.maxWidth = "none";
            mowerImage.style.margin = "0";
            mowerImage.style.padding = "0";
        }

        const HEADING_POINT_LIMIT = 2;
        const HEADING_MIN_DISTANCE = Math.max(
            0.05,
            Number(options.headingMinDistance || 1.0)
        );
        const MOVEMENT_HEADING_OFFSET = Number(
            options.movementHeadingOffset === undefined
                ? -90.0
                : options.movementHeadingOffset
        );

        let displayed = null;
        let active = null;
        let lastAcceptedKey = "";
        let lastArrival = 0;
        let rafId = 0;
        let stateTimer = 0;
        let mapTimer = 0;

        let viewScale = 1.0;
        let viewX = 0.0;
        let viewY = 0.0;
        let dragging = false;
        let dragStartX = 0.0;
        let dragStartY = 0.0;
        let dragOriginX = 0.0;
        let dragOriginY = 0.0;

        const activePointers = new Map();
        let pinchStartDistance = 0.0;
        let pinchStartScale = 1.0;
        let pinchStartCenterX = 0.0;
        let pinchStartCenterY = 0.0;
        let previousSubtotalArea = null;
        let previousMowingPercentage = null;
        let lastWorkChange = 0;
        let headingPoints = [];
        let lastPositionKey = "";
        let lastMovementHeading = null;

        function pointerDistance(a, b) {
            return Math.hypot(b.x - a.x, b.y - a.y);
        }

        function pointerCenter(a, b) {
            return {
                x: (a.x + b.x) / 2.0,
                y: (a.y + b.y) / 2.0
            };
        }

        function canPanAtCurrentScale() {
            const stageRect = stage.getBoundingClientRect();
            const bounds = rotatedBounds(viewScale);
            return bounds.width > stageRect.width + 0.5
                || bounds.height > stageRect.height + 0.5;
        }

        function baseMapSize() {
            const width = mapImage.clientWidth || stage.clientWidth;
            const height = mapImage.clientHeight ||
                (mapImage.naturalWidth > 0
                    ? width * mapImage.naturalHeight / mapImage.naturalWidth
                    : stage.clientHeight);
            return { width: width, height: height };
        }

        function rotatedBounds(scale) {
            const size = baseMapSize();
            const c = Math.abs(Math.cos(VIEW_ROTATION_RAD));
            const s = Math.abs(Math.sin(VIEW_ROTATION_RAD));
            return {
                width: (size.width * c + size.height * s) * scale,
                height: (size.width * s + size.height * c) * scale
            };
        }

        function applyViewTransform() {
            /*
             * world owns only SCREEN-ALIGNED pan + zoom.
             * rotationPlane owns only the visual map rotation.
             * Dragging therefore always follows the user's horizontal and
             * vertical screen axes, independent of viewRotation.
             */
            world.style.transformOrigin = "0 0";
            world.style.transform =
                "translate(" + viewX.toFixed(2) + "px," +
                viewY.toFixed(2) + "px) " +
                "scale(" + viewScale.toFixed(4) + ")";
        }

        function clampPan() {
            const stageRect = stage.getBoundingClientRect();
            const size = baseMapSize();
            const bounds = rotatedBounds(viewScale);

            /*
             * User-driven panning:
             * The map may intentionally move far outside the viewport.
             * We only keep a small grab strip visible so it cannot be lost
             * completely. Translation remains in screen coordinates.
             */
            const extraX =
                (bounds.width - size.width * viewScale) / 2.0;
            const extraY =
                (bounds.height - size.height * viewScale) / 2.0;

            const minX =
                PAN_MIN_VISIBLE - bounds.width + extraX;
            const maxX =
                stageRect.width - PAN_MIN_VISIBLE + extraX;

            const minY =
                PAN_MIN_VISIBLE - bounds.height + extraY;
            const maxY =
                stageRect.height - PAN_MIN_VISIBLE + extraY;

            viewX = Math.min(maxX, Math.max(minX, viewX));
            viewY = Math.min(maxY, Math.max(minY, viewY));
        }

        function setZoom(newScale, clientX, clientY) {
            const oldScale = viewScale;
            newScale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newScale));
            if (Math.abs(newScale - oldScale) < 0.0001) return;

            const rect = stage.getBoundingClientRect();
            const px = clientX - rect.left;
            const py = clientY - rect.top;
            const worldX = (px - viewX) / oldScale;
            const worldY = (py - viewY) / oldScale;

            viewScale = newScale;
            viewX = px - worldX * newScale;
            viewY = py - worldY * newScale;

            clampPan();
            applyViewTransform();
        }

        function resetView() {
            viewScale = 1.0;
            viewX = 0.0;
            viewY = 0.0;
            clampPan();
            applyViewTransform();
        }

        function reflowView() {
            clampPan();
            applyViewTransform();
        }

        function iconUrl(value) {
            let path = String(value || "").trim();
            if (!path) return "";
            if (/^(data:|https?:)/i.test(path)) return path;

            const prefix = String(options.originPrefix || "").replace(/\/$/, "");
            if (path.indexOf("/fhem/") === 0) return prefix ? prefix + path : path;
            if (path.indexOf("/images/") === 0) return (prefix || "") + "/fhem" + path;
            return path;
        }

        function shortestAngleDelta(from, to) {
            return ((to - from + 540) % 360) - 180;
        }

        function normalizeAngle(value) {
            let angle = Number(value);
            if (!Number.isFinite(angle)) return 0;
            angle %= 360;
            if (angle < 0) angle += 360;
            return angle;
        }

        function positionKey(state) {
            return [
                Number(state.x).toFixed(4),
                Number(state.y).toFixed(4)
            ].join("|");
        }

        function movementHeading(state) {
            const x = Number(state.x);
            const y = Number(state.y);
            if (!Number.isFinite(x) || !Number.isFinite(y)) {
                return null;
            }

            const key = positionKey(state);
            if (key !== lastPositionKey) {
                const last = headingPoints.length
                    ? headingPoints[headingPoints.length - 1]
                    : null;
                const moved = !last || Math.hypot(
                    x - last.x,
                    y - last.y
                ) >= HEADING_MIN_DISTANCE;

                if (moved) {
                    headingPoints.push({ x: x, y: y });
                    if (headingPoints.length > HEADING_POINT_LIMIT) {
                        headingPoints.shift();
                    }
                }
                lastPositionKey = key;
            }

            if (headingPoints.length < 2) {
                return lastMovementHeading;
            }

            const first = headingPoints[0];
            const last = headingPoints[headingPoints.length - 1];
            const dx = last.x - first.x;
            const dy = last.y - first.y;
            if (Math.hypot(dx, dy) < HEADING_MIN_DISTANCE) {
                return lastMovementHeading;
            }

            // Screen coordinates: +x right, +y down. CSS rotate() is clockwise.
            // The mower icon's native nose points upward, hence +90 degrees.
            lastMovementHeading = normalizeAngle(
                Math.atan2(dy, dx) * 180.0 / Math.PI
                + MOVEMENT_HEADING_OFFSET
            );
            return lastMovementHeading;
        }

        function stateWithDisplayHeading(state) {
            const heading = movementHeading(state);
            if (heading === null) return state;
            return Object.assign({}, state, { angle: heading });
        }

        function stateKey(state) {
            return [
                Number(state.x).toFixed(4),
                Number(state.y).toFixed(4),
                Number(state.angle).toFixed(4)
            ].join("|");
        }

        function draw(state) {
            if (!state || !mapImage.complete) return;

            const baseWidth = mapImage.clientWidth;
            const baseHeight = mapImage.clientHeight;
            if (baseWidth <= 0 || baseHeight <= 0) return;

            const sx = baseWidth / Number(state.canvasWidth);
            const sy = baseHeight / Number(state.canvasHeight);
            const width = Number(state.width) * sx;
            const height = Number(state.height) * sy;
            const x = Number(state.x) * sx;
            const y = Number(state.y) * sy;

            mowerImage.style.width = width + "px";
            mowerImage.style.height = height + "px";
            mowerImage.style.left = (x - width / 2) + "px";
            mowerImage.style.top = (y - height / 2) + "px";
            mowerImage.style.transform = "rotate(" + Number(state.angle).toFixed(3) + "deg)";
            mowerImage.style.visibility = "visible";
            mowerImage.style.opacity = "1";
            mowerImage.style.display = "block";

            displayed = Object.assign({}, state);
        }

        function interpolate(a, b, t) {
            const smooth = t * t * (3 - 2 * t);
            return Object.assign({}, b, {
                x: Number(a.x) + (Number(b.x) - Number(a.x)) * smooth,
                y: Number(a.y) + (Number(b.y) - Number(a.y)) * smooth,
                angle: Number(a.angle)
                    + shortestAngleDelta(Number(a.angle), Number(b.angle)) * smooth
            });
        }

        let lastSourceTimestamp = null;
        let smoothedSegmentMs = FALLBACK_SEGMENT_MS;

        function startSegment(target, arrival) {
            if (!displayed) {
                draw(target);
                lastArrival = arrival;
                lastSourceTimestamp = numberOrNull(target.sourceTimestamp);
                return;
            }

            let observedMs = null;
            const sourceTimestamp = numberOrNull(target.sourceTimestamp);

            if (
                sourceTimestamp !== null
                && lastSourceTimestamp !== null
                && sourceTimestamp > lastSourceTimestamp
            ) {
                observedMs = (sourceTimestamp - lastSourceTimestamp) * 1000.0;
            } else if (lastArrival > 0) {
                observedMs = arrival - lastArrival;
            }

            if (observedMs !== null && Number.isFinite(observedMs)) {
                observedMs = Math.max(
                    MIN_SEGMENT_MS,
                    Math.min(MAX_SEGMENT_MS, observedMs)
                );
                smoothedSegmentMs =
                    smoothedSegmentMs * 0.60 + observedMs * 0.40;
            }

            // Slight overlap absorbs normal polling jitter without adding the
            // former complete one-sample delay.
            const duration = Math.max(
                MIN_SEGMENT_MS,
                Math.min(MAX_SEGMENT_MS, smoothedSegmentMs * 1.06)
            );

            lastArrival = arrival;
            if (sourceTimestamp !== null) {
                lastSourceTimestamp = sourceTimestamp;
            }

            active = {
                from: Object.assign({}, displayed),
                to: Object.assign({}, target),
                start: performance.now(),
                duration: duration
            };
        }

        function accept(state) {
            if (!state) return;

            const values = [
                state.x, state.y, state.angle,
                state.canvasWidth, state.canvasHeight
            ].map(Number);
            if (!values.every(Number.isFinite)) return;

            const displayState = stateWithDisplayHeading(state);
            const key = stateKey(displayState);
            if (key === lastAcceptedKey) return;
            lastAcceptedKey = key;

            const src = iconUrl(displayState.icon);
            if (src && mowerImage.getAttribute("src") !== src) {
                mowerImage.src = src;
            }

            const subtotalArea = numberOrNull(state.subtotalArea);
            const mowingPercentage = numberOrNull(state.mowingPercentage);
            const nowActivity = performance.now();

            if (
                (subtotalArea !== null && previousSubtotalArea !== null
                    && subtotalArea > previousSubtotalArea + 0.001)
                ||
                (mowingPercentage !== null && previousMowingPercentage !== null
                    && mowingPercentage !== previousMowingPercentage)
            ) {
                lastWorkChange = nowActivity;
            }
            if (subtotalArea !== null) previousSubtotalArea = subtotalArea;
            if (mowingPercentage !== null) {
                previousMowingPercentage = mowingPercentage;
            }

            const explicitMowing = ["mowing", "working"].indexOf(
                String(state.motion || "").toLowerCase()
            ) >= 0;
            const activeTask = taskType(state) !== "none";
            const recentWork = lastWorkChange > 0
                && (nowActivity - lastWorkChange) <= 10000;

            updateStatusPanel(
                statusRoot, displayState, language,
                { mowingActive: activeTask && (explicitMowing || recentWork) }
            );
            if (typeof options.onState === "function") {
                options.onState(Object.assign({}, displayState));
            }

            const arrival = performance.now();

            if (!displayed) {
                draw(displayState);
                lastArrival = arrival;
                lastSourceTimestamp = numberOrNull(
                    displayState.sourceTimestamp
                );
                return;
            }

            // Every new real point becomes the current target immediately.
            // If an older segment is still active, `displayed` already is the
            // current interpolated on-screen position, so the new segment
            // continues smoothly from exactly where the mower is visible.
            startSegment(displayState, arrival);
        }

        function loadState() {
            if (!STATE_URL) return;
            const script = document.createElement("script");
            script.src = cacheBuster(STATE_URL);
            script.async = true;
            script.onload = function () { script.remove(); };
            script.onerror = function () { script.remove(); };
            document.head.appendChild(script);
        }

        function refreshMap() {
            if (!MAP_URL) return;
            mapImage.src = cacheBuster(MAP_URL);
        }

        function animate(now) {
            if (active) {
                const t = Math.max(0, Math.min(1, (now - active.start) / active.duration));
                draw(interpolate(active.from, active.to, t));
                if (t >= 1) active = null;
            }
            rafId = global.requestAnimationFrame(animate);
        }

        stage.addEventListener("wheel", function (event) {
            event.preventDefault();
            const factor = event.deltaY < 0 ? ZOOM_STEP : 1.0 / ZOOM_STEP;
            setZoom(viewScale * factor, event.clientX, event.clientY);
        }, { passive: false });

        stage.addEventListener("mousedown", function (event) {
            if (event.button !== 0 || viewScale <= MIN_ZOOM + 0.0001) return;
            event.preventDefault();

            dragging = true;
            dragStartX = event.clientX;
            dragStartY = event.clientY;
            dragOriginX = viewX;
            dragOriginY = viewY;
            stage.style.cursor = "grabbing";
        });

        document.addEventListener("mousemove", function (event) {
            if (!dragging) return;
            event.preventDefault();

            viewX = dragOriginX + event.clientX - dragStartX;
            viewY = dragOriginY + event.clientY - dragStartY;
            clampPan();
            applyViewTransform();
        });

        document.addEventListener("mouseup", function () {
            if (!dragging) return;
            dragging = false;
            stage.style.cursor = "grab";
        });

        
        /*
         * Mobile gestures:
         * - one pointer: normal screen-aligned pan whenever the rotated map
         *   exceeds the viewport, even at zoom 1.0
         * - two pointers: pinch-to-zoom around the gesture center
         */
        stage.addEventListener("pointerdown", function (event) {
            activePointers.set(event.pointerId, { x:event.clientX, y:event.clientY });
            try { stage.setPointerCapture(event.pointerId); } catch (e) {}

            if (activePointers.size === 1) {
                dragging = true;
                dragStartX = event.clientX;
                dragStartY = event.clientY;
                dragOriginX = viewX;
                dragOriginY = viewY;
            } else if (activePointers.size === 2) {
                const points = Array.from(activePointers.values());
                const center = pointerCenter(points[0], points[1]);
                pinchStartDistance = Math.max(1.0, pointerDistance(points[0], points[1]));
                pinchStartScale = viewScale;
                pinchStartCenterX = center.x;
                pinchStartCenterY = center.y;
                dragging = false;
            }

            event.preventDefault();
            event.stopPropagation();
        }, { passive:false, capture:true });

        stage.addEventListener("pointermove", function (event) {
            if (!activePointers.has(event.pointerId)) return;
            activePointers.set(event.pointerId, { x:event.clientX, y:event.clientY });

            if (activePointers.size >= 2) {
                const points = Array.from(activePointers.values()).slice(0, 2);
                const center = pointerCenter(points[0], points[1]);
                const distance = Math.max(1.0, pointerDistance(points[0], points[1]));
                const factor = distance / pinchStartDistance;
                const targetScale = pinchStartScale * factor;

                setZoom(targetScale, center.x, center.y);
                event.preventDefault();
                return;
            }

            if (dragging && canPanAtCurrentScale()) {
                viewX = dragOriginX + (event.clientX - dragStartX);
                viewY = dragOriginY + (event.clientY - dragStartY);
                clampPan();
                applyViewTransform();
                event.preventDefault();
            }
        }, { passive:false, capture:true });

        function releasePointer(event) {
            activePointers.delete(event.pointerId);
            try { stage.releasePointerCapture(event.pointerId); } catch (e) {}

            if (activePointers.size === 1) {
                const only = Array.from(activePointers.values())[0];
                dragging = true;
                dragStartX = only.x;
                dragStartY = only.y;
                dragOriginX = viewX;
                dragOriginY = viewY;
            } else if (activePointers.size === 0) {
                dragging = false;
            } else if (activePointers.size === 2) {
                const points = Array.from(activePointers.values()).slice(0, 2);
                pinchStartDistance = Math.max(1.0, pointerDistance(points[0], points[1]));
                pinchStartScale = viewScale;
            }
        }

        stage.addEventListener("pointerup", releasePointer, { passive:false, capture:true });
        stage.addEventListener("pointercancel", releasePointer, { passive:false, capture:true });

stage.addEventListener("dblclick", function (event) {
            event.preventDefault();
            resetView();
        });

        mapImage.addEventListener("load", function () {
            stage.style.height = mapImage.clientHeight + "px";
            clampPan();
            applyViewTransform();
            if (displayed) draw(displayed);
        });

        function handleResize() {
            stage.style.height = mapImage.clientHeight + "px";
            clampPan();
            applyViewTransform();
            if (displayed) draw(displayed);
        }

        global.addEventListener("resize", handleResize);

        let resizeObserver = null;
        if (typeof ResizeObserver !== "undefined") {
            resizeObserver = new ResizeObserver(function () {
                window.requestAnimationFrame(reflowView);
            });
            resizeObserver.observe(stage);
            if (stage.parentElement) resizeObserver.observe(stage.parentElement);
        } else {
            window.addEventListener("resize", reflowView);
        }


        resetView();
        loadState();
        stateTimer = global.setInterval(loadState, STATE_POLL_MS);
        mapTimer = global.setInterval(refreshMap, MAP_REFRESH_MS);
        rafId = global.requestAnimationFrame(animate);

        return {
            accept: accept,
            resetView: resetView,
            setZoom: setZoom,
            destroy: function () {
                if (stateTimer) global.clearInterval(stateTimer);
                if (mapTimer) global.clearInterval(mapTimer);
                if (rafId) global.cancelAnimationFrame(rafId);
                global.removeEventListener("resize", handleResize);
            }
        };
    }

    global.NavimowLive = {
        version: "1.6.0",
        init: function (options) {
            const instance = createInstance(options || {});
            instances.push(instance);
            return instance;
        }
    };

})(window);
