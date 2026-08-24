#!/usr/bin/env python3
"""Interactive Navimow account bootstrap using NavimowSession."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--client-path", default="/opt/fhem/navimow-python")
    parser.add_argument("--region", default="fra")
    parser.add_argument("--host", default="navimow-fra.ninebot.com")
    parser.add_argument("--language", default="de")
    parser.add_argument("--fhem-device", default="i210Pro")
    parser.add_argument("--vehicle-sn", default="")
    return parser.parse_args()


def stable_device_id(seed: str) -> str:
    return hashlib.sha256(("fhem-navimow-" + seed).encode()).hexdigest()[:32]


def load_input(args: argparse.Namespace) -> dict[str, Any]:
    if args.interactive:
        return {
            "email": input("Navimow E-Mail: ").strip(),
            "password": getpass.getpass("Navimow Passwort: "),
        }
    line = sys.stdin.readline()
    if not line:
        raise ValueError("no JSON input received")
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def main() -> int:
    args = parse_args()
    data = load_input(args)
    email = str(data.get("email") or "").strip()
    password = str(data.get("password") or "")
    if not email or not password:
        raise ValueError("email and password are required")

    if args.client_path not in sys.path:
        sys.path.insert(0, args.client_path)
    from navimow_private.session import NavimowSession

    session = NavimowSession(args.output, client_path=args.client_path)
    vehicles = session.login(
        email,
        password,
        device_id=str(data.get("device_id") or "").strip() or stable_device_id(args.fhem_device),
        region=args.region,
        host=args.host,
        language=args.language,
    )
    if args.vehicle_sn:
        session.select_vehicle(args.vehicle_sn)
    elif len(vehicles) > 1:
        # Do not silently select the first device.
        session.data["selected_vehicle_sn"] = ""
        session.save()

    print(json.dumps({
        "ok": True,
        "email_masked": session.data.get("account", {}).get("email_masked", "***"),
        "region": session.data.get("cloud", {}).get("region", ""),
        "host": session.data.get("cloud", {}).get("host", ""),
        "vehicle_count": len(vehicles),
        "vehicles": vehicles,
        "selected_vehicle_sn": session.data.get("selected_vehicle_sn", ""),
        "session_file": str(Path(args.output)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
