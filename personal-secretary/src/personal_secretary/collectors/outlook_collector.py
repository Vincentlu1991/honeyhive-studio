from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

import msal
import requests

from personal_secretary.config import SecretaryConfig
from personal_secretary.models import IngestedFile
from personal_secretary.storage import SecretaryStorage


class OutlookCollector:
    def __init__(self, config: SecretaryConfig, storage: SecretaryStorage) -> None:
        self.config = config
        self.storage = storage
        self.cache_path = self.storage.base / "outlook_token_cache.json"

    def collect(self) -> list[IngestedFile]:
        if not self.config.outlook_enabled or not self.config.outlook_client_id:
            return []

        token = self._acquire_token()
        if not token:
            return []

        headers = {"Authorization": f"Bearer {token}"}
        since = datetime.now(timezone.utc) - timedelta(days=self.config.outlook_attachment_days)
        since_iso = since.isoformat().replace("+00:00", "Z")

        messages_url = (
            "https://graph.microsoft.com/v1.0/me/messages"
            "?$select=id,subject,from,receivedDateTime,hasAttachments"
            f"&$filter=hasAttachments eq true and receivedDateTime ge {since_iso}"
            "&$top=50"
        )

        items: list[IngestedFile] = []
        resp = requests.get(messages_url, headers=headers, timeout=60)
        resp.raise_for_status()

        for msg in resp.json().get("value", []):
            msg_id = msg.get("id", "")
            if not msg_id:
                continue

            att_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments"
            att_resp = requests.get(att_url, headers=headers, timeout=60)
            att_resp.raise_for_status()

            for att in att_resp.json().get("value", []):
                if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                    continue

                attachment_id = att.get("id", "")
                source_id = f"{msg_id}:{attachment_id}"
                if self.storage.has_source_item("outlook", source_id):
                    continue

                content_b64 = att.get("contentBytes", "")
                name = att.get("name", "attachment.bin")
                if not content_b64:
                    continue

                target_dir = self.storage.inbox / "outlook"
                target_dir.mkdir(parents=True, exist_ok=True)
                local_path = self._dedupe_path(target_dir / name)
                local_path.write_bytes(base64.b64decode(content_b64))

                sender = ((msg.get("from") or {}).get("emailAddress") or {}).get("address", "")
                item = IngestedFile(
                    source="outlook",
                    source_id=source_id,
                    file_name=name,
                    local_path=local_path,
                    created_at=msg.get("receivedDateTime", datetime.utcnow().isoformat()),
                    sender=sender,
                    subject=msg.get("subject", ""),
                )
                self.storage.register_ingested(item)
                items.append(item)

        return items

    def connect(
        self,
        client_id: str | None = None,
        tenant_id: str | None = None,
        account_email: str | None = None,
    ) -> dict:
        resolved_client_id = (client_id or self.config.outlook_client_id).strip()
        resolved_tenant_id = (tenant_id or self.config.outlook_tenant_id or "common").strip() or "common"
        resolved_email = (account_email or self.config.outlook_account_email).strip()

        if not resolved_client_id:
            return {
                "connected": False,
                "message": "OUTLOOK_CLIENT_ID is empty. Please set it in .env first.",
                "method": "none",
            }

        token, method, message = self._acquire_token_with_details(
            interactive_first=True,
            client_id=resolved_client_id,
            tenant_id=resolved_tenant_id,
            account_email=resolved_email,
            allow_device_flow=True,
        )
        return {
            "connected": bool(token),
            "message": message,
            "method": method,
        }

    def status(
        self,
        client_id: str | None = None,
        tenant_id: str | None = None,
        account_email: str | None = None,
    ) -> dict:
        resolved_client_id = (client_id or self.config.outlook_client_id).strip()
        resolved_tenant_id = (tenant_id or self.config.outlook_tenant_id or "common").strip() or "common"
        resolved_email = (account_email or self.config.outlook_account_email).strip()

        if not self.config.outlook_enabled:
            return {
                "connected": False,
                "message": "OUTLOOK_ENABLED is false.",
                "method": "disabled",
            }
        if not resolved_client_id:
            return {
                "connected": False,
                "message": "OUTLOOK_CLIENT_ID is empty.",
                "method": "none",
            }

        token, method, message = self._acquire_token_with_details(
            interactive_first=False,
            client_id=resolved_client_id,
            tenant_id=resolved_tenant_id,
            account_email=resolved_email,
            allow_device_flow=False,
        )
        if token:
            return {"connected": True, "message": "Connected (token available).", "method": method}
        return {"connected": False, "message": message, "method": method}

    def _acquire_token(self) -> str:
        token, _, _ = self._acquire_token_with_details(
            interactive_first=False,
            client_id=self.config.outlook_client_id,
            tenant_id=self.config.outlook_tenant_id,
            account_email=self.config.outlook_account_email,
            allow_device_flow=True,
        )
        return token

    def _acquire_token_with_details(
        self,
        interactive_first: bool,
        client_id: str,
        tenant_id: str,
        account_email: str,
        allow_device_flow: bool,
    ) -> tuple[str, str, str]:
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        app = msal.PublicClientApplication(client_id=client_id, authority=authority, token_cache=cache)
        scopes = ["Mail.Read"]

        accounts = app.get_accounts(username=account_email or None)
        if accounts:
            result = app.acquire_token_silent(scopes=scopes, account=accounts[0])
            if result and result.get("access_token"):
                self._persist_cache(cache)
                return str(result["access_token"]), "silent", "Connected using cached token."

        if interactive_first:
            try:
                result = app.acquire_token_interactive(scopes=scopes)
                if result and result.get("access_token"):
                    self._persist_cache(cache)
                    return str(result["access_token"]), "interactive", "Outlook authorization succeeded."
            except Exception:
                pass

        if not allow_device_flow:
            return "", "silent", "No valid cached token. Click Connect Outlook to authenticate."

        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            return "", "device", "Unable to start device login flow."

        print("[Outlook] Device login required:")
        print(flow.get("message", "Open browser and login to continue."))
        result = app.acquire_token_by_device_flow(flow)
        token = str(result.get("access_token", ""))
        if token:
            self._persist_cache(cache)
            return token, "device", "Outlook authorization succeeded via device flow."
        return "", "device", str(result.get("error_description", "Outlook authorization failed."))

    def _persist_cache(self, cache: msal.SerializableTokenCache) -> None:
        if not cache.has_state_changed:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(cache.serialize(), encoding="utf-8")

    @staticmethod
    def _dedupe_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        idx = 1
        while True:
            candidate = path.with_name(f"{stem}_{idx}{suffix}")
            if not candidate.exists():
                return candidate
            idx += 1
