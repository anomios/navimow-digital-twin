#!/opt/fhem/navimow-python/venv/bin/python3
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

CLIENT_PATH = "/opt/fhem/navimow-python"
SESSION_FILE = Path("/opt/fhem/navimow-python/cache/navimow_private_session.json")

KEYWORDS = (
    "wifi", "wlan", "rssi", "signal", "network", "net",
    "bluetooth", "ble", "bt", "connect", "online"
)

def walk(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            p = f"{path}.{key}" if path else str(key)
            yield p, child
            yield from walk(child, p)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            p = f"{path}[{idx}]"
            yield p, child
            yield from walk(child, p)

def keyword_hits(data: Any):
    hits = []
    for path, value in walk(data):
        low = path.lower()
        if any(k in low for k in KEYWORDS):
            if isinstance(value, (dict, list)):
                shown = f"<{type(value).__name__}>"
            else:
                shown = value
            hits.append((path, shown))
    return hits

def call_and_report(name: str, fn, *args):
    print(f"\n========== {name} ==========")
    try:
        data = fn(*args)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return

    print("type:", type(data).__name__)
    if isinstance(data, dict):
        print("top-level keys:", ", ".join(sorted(map(str, data.keys()))))
    elif isinstance(data, list):
        print("items:", len(data))

    hits = keyword_hits(data)
    if hits:
        print("CONNECTIVITY HITS:")
        for path, value in hits:
            print(f"  {path} = {value!r}")
    else:
        print("CONNECTIVITY HITS: none")

    # Keep a local raw copy for later inspection without flooding the terminal.
    out = Path(f"/tmp/navimow_diag_{name}.json")
    try:
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print("raw saved:", out)
    except Exception as e:
        print("raw save failed:", e)

def main():
    if CLIENT_PATH not in sys.path:
        sys.path.insert(0, CLIENT_PATH)

    from navimow_private.session import NavimowSession

    session = NavimowSession(SESSION_FILE, client_path=CLIENT_PATH).load()
    client = session.client()
    vehicle = session.selected_vehicle()

    vehicle_sn = str(vehicle.get("vehicle_sn") or "").strip()
    vehicle_type = int(vehicle.get("vehicle_type") or 801)

    print("vehicle_sn:", vehicle_sn)
    print("vehicle_type:", vehicle_type)
    print("client:", type(client).__name__)

    # Show candidate API methods so we can see whether the private client
    # exposes a dedicated connectivity endpoint we have not used yet.
    print("\n========== candidate client methods ==========")
    for name in sorted(dir(client)):
        low = name.lower()
        if name.startswith("_"):
            continue
        if any(k in low for k in KEYWORDS):
            obj = getattr(client, name, None)
            if callable(obj):
                try:
                    sig = inspect.signature(obj)
                except Exception:
                    sig = "(signature unavailable)"
                print(f"  {name}{sig}")

    # Known read-only methods already used by the current bridge.
    call_and_report("index2", client.index2, vehicle_sn)
    call_and_report("set_list", client.set_list, vehicle_sn)
    call_and_report("location", client.location, vehicle_sn, vehicle_type)
    call_and_report("today_plan", client.today_plan, vehicle_sn, vehicle_type)

    try:
        session.sync_from_client(client)
    except Exception as e:
        print("\nsession sync warning:", e)

if __name__ == "__main__":
    main()
