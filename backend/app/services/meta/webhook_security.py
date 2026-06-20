import hashlib
import hmac

from app.core.config import settings


class WebhookSecurity:
    def payload_hash(self, body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    def verify_signature(self, body: bytes, signature_header: str | None) -> bool:
        if not settings.WEBHOOK_SIGNATURE_REQUIRED:
            return True
        secret = settings.META_WEBHOOK_SECRET or settings.META_APP_SECRET
        if not secret or not signature_header:
            return False
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    def event_id_from_payload(self, payload: dict, payload_hash: str) -> str:
        entry_ids: list[str] = []
        for entry in payload.get("entry", []):
            if entry.get("id"):
                entry_ids.append(str(entry["id"]))
            for change in entry.get("changes", []):
                value = change.get("value") or {}
                external_id = value.get("comment_id") or value.get("id") or value.get("post_id")
                if external_id:
                    entry_ids.append(str(external_id))
        return ":".join(entry_ids) if entry_ids else payload_hash


webhook_security = WebhookSecurity()
