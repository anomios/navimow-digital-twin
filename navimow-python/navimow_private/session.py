"""Persistent session management for the Navimow private cloud.

The session file contains refreshable Passport tokens, the private-cloud uid,
a stable app device id and discovered vehicles.  It is always written atomically
with mode 0600.  Passwords are never stored.
"""
from __future__ import annotations

import inspect
import json
import os
import time
from pathlib import Path
from typing import Any


class NavimowSessionError(RuntimeError):
    """Invalid or incomplete persistent session."""


class NavimowSession:
    """Load, create, refresh and persist one Navimow private-cloud session."""

    VERSION = 2

    def __init__(self, filename: str | Path, *, client_path: str | Path | None = None) -> None:
        self.path = Path(filename)
        self.client_path = str(client_path) if client_path else ""
        self.data: dict[str, Any] = {}

    @staticmethod
    def _masked_email(email: str) -> str:
        if "@" not in email:
            return "***"
        local, domain = email.split("@", 1)
        return (local[:1] or "*") + "***@" + domain

    @staticmethod
    def _safe_vehicle(vehicle: dict[str, Any]) -> dict[str, Any]:
        return {
            "vehicle_sn": str(vehicle.get("vehicle_sn") or ""),
            "vehicle_type": str(vehicle.get("vehicle_type") or ""),
            "name": str(
                vehicle.get("selfDefinedName")
                or vehicle.get("vehicle_name")
                or vehicle.get("subType")
                or ""
            ),
            "model": str(vehicle.get("subType") or ""),
            "shared": bool(vehicle.get("vehicle_share_type") not in (None, 0, "0")),
        }

    def _imports(self) -> tuple[Any, Any, Any]:
        import sys

        if self.client_path and self.client_path not in sys.path:
            sys.path.insert(0, self.client_path)
        from navimow_private.api.client import NavimowCloudClient
        from navimow_private.api import passport
        from navimow_private.api.passport import Tokens

        return NavimowCloudClient, passport, Tokens

    @staticmethod
    def _make_tokens(tokens_type: Any, values: dict[str, Any]) -> Any:
        available = {
            "access_token": str(values.get("access_token") or ""),
            "refresh_token": str(values.get("refresh_token") or ""),
            "uuid": str(values.get("uuid") or ""),
            "region": str(values.get("region") or ""),
        }
        try:
            signature = inspect.signature(tokens_type)
            kwargs = {name: available[name] for name in signature.parameters if name in available}
            return tokens_type(**kwargs)
        except Exception:
            # Compatibility with an older two-argument Tokens class.
            return tokens_type(available["access_token"], available["refresh_token"])

    def load(self) -> "NavimowSession":
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise NavimowSessionError(f"session file not found: {self.path}") from exc
        except (OSError, ValueError) as exc:
            raise NavimowSessionError(f"cannot read session file: {exc}") from exc
        if not isinstance(payload, dict):
            raise NavimowSessionError("session file does not contain a JSON object")

        # Accept the original version-1 bootstrap format and normalise it.
        if int(payload.get("version") or 1) == 1:
            old = payload.get("session") if isinstance(payload.get("session"), dict) else {}
            vehicles = payload.get("vehicles") if isinstance(payload.get("vehicles"), list) else []
            payload = {
                "version": self.VERSION,
                "account": {
                    "email": str(payload.get("email") or ""),
                    "email_masked": self._masked_email(str(payload.get("email") or "")),
                },
                "tokens": {
                    "access_token": str(old.get("access_token") or ""),
                    "refresh_token": str(old.get("refresh_token") or ""),
                    "uuid": str(old.get("uuid") or ""),
                },
                "cloud": {
                    "uid": str(old.get("uid") or ""),
                    "region": str(old.get("region") or "fra"),
                    "host": str(old.get("host") or "navimow-fra.ninebot.com"),
                    "device_id": str(old.get("device_id") or ""),
                    "language": "de",
                },
                "vehicles": vehicles,
                "selected_vehicle_sn": str(vehicles[0].get("vehicle_sn") or "") if len(vehicles) == 1 else "",
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            }
            self.data = payload
            self.save()
        else:
            self.data = payload

        self._validate()
        return self

    def _validate(self) -> None:
        tokens = self.data.get("tokens")
        cloud = self.data.get("cloud")
        if not isinstance(tokens, dict) or not isinstance(cloud, dict):
            raise NavimowSessionError("session has no tokens/cloud section")
        required = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "uid": cloud.get("uid"),
            "device_id": cloud.get("device_id"),
        }
        missing = [key for key, value in required.items() if not str(value or "").strip()]
        if missing:
            raise NavimowSessionError("session is incomplete: " + ", ".join(missing))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["version"] = self.VERSION
        self.data["updated_at"] = int(time.time())
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def login(
        self,
        email: str,
        password: str,
        *,
        device_id: str,
        region: str = "fra",
        host: str = "navimow-fra.ninebot.com",
        language: str = "de",
    ) -> list[dict[str, Any]]:
        NavimowCloudClient, _passport, _Tokens = self._imports()
        client = NavimowCloudClient(
            device_id=device_id,
            region=region,
            language=language,
            host=host,
        )
        client.authenticate(email, password, region=region)
        client.mower_login()
        raw = client.auth_list()
        vehicles = [self._safe_vehicle(item) for item in raw if isinstance(item, dict)]
        self.data = {
            "version": self.VERSION,
            "account": {
                "email": email,
                "email_masked": self._masked_email(email),
            },
            "tokens": {},
            "cloud": {
                "language": language,
            },
            "vehicles": vehicles,
            "selected_vehicle_sn": str(vehicles[0].get("vehicle_sn") or "") if len(vehicles) == 1 else "",
            "created_at": int(time.time()),
        }
        self.sync_from_client(client, force=True)
        return vehicles

    def client(self) -> Any:
        self._validate()
        NavimowCloudClient, _passport, Tokens = self._imports()
        tokens_data = dict(self.data["tokens"])
        cloud = dict(self.data["cloud"])
        tokens_data["region"] = cloud.get("region")
        tokens = self._make_tokens(Tokens, tokens_data)
        return NavimowCloudClient(
            device_id=str(cloud["device_id"]),
            tokens=tokens,
            uid=str(cloud["uid"]),
            region=str(cloud.get("region") or "fra"),
            language=str(cloud.get("language") or "de"),
            host=str(cloud.get("host") or "navimow-fra.ninebot.com"),
        )

    def selected_vehicle(self) -> dict[str, Any]:
        vehicles = self.data.get("vehicles") if isinstance(self.data.get("vehicles"), list) else []
        selected = str(self.data.get("selected_vehicle_sn") or "")
        if selected:
            for vehicle in vehicles:
                if isinstance(vehicle, dict) and str(vehicle.get("vehicle_sn") or "") == selected:
                    return vehicle
        if len(vehicles) == 1 and isinstance(vehicles[0], dict):
            return vehicles[0]
        raise NavimowSessionError("no vehicle selected in session")

    def select_vehicle(self, vehicle_sn: str) -> dict[str, Any]:
        for vehicle in self.data.get("vehicles", []):
            if isinstance(vehicle, dict) and str(vehicle.get("vehicle_sn") or "") == vehicle_sn:
                self.data["selected_vehicle_sn"] = vehicle_sn
                self.save()
                return vehicle
        raise NavimowSessionError(f"vehicle not found in session: {vehicle_sn}")

    def sync_from_client(self, client: Any, *, force: bool = False) -> bool:
        tokens = client.tokens
        new_tokens = {
            "access_token": str(getattr(tokens, "access_token", "")),
            "refresh_token": str(getattr(tokens, "refresh_token", "")),
            "uuid": str(getattr(tokens, "uuid", "")),
        }
        new_cloud = {
            **(self.data.get("cloud") if isinstance(self.data.get("cloud"), dict) else {}),
            "uid": str(client.uid),
            "region": str(client.region),
            "host": str(client.host),
            "device_id": str(client.device_id),
        }
        changed = force or new_tokens != self.data.get("tokens") or new_cloud != self.data.get("cloud")
        if changed:
            self.data["tokens"] = new_tokens
            self.data["cloud"] = new_cloud
            self.data["last_token_sync"] = int(time.time())
            self.save()
        return changed

    def refresh(self) -> None:
        client = self.client()
        client.refresh_session()
        client.mower_login()
        self.sync_from_client(client, force=True)

    def summary(self) -> dict[str, Any]:
        vehicle = self.selected_vehicle()
        cloud = self.data.get("cloud", {})
        account = self.data.get("account", {})
        return {
            "email_masked": str(account.get("email_masked") or "***"),
            "region": str(cloud.get("region") or ""),
            "host": str(cloud.get("host") or ""),
            "vehicle": vehicle,
            "session_file": str(self.path),
        }
