import re

from app.models.domain import ModerationStatus


class ModerationService:
    blocked_words = {"lừa đảo", "scam"}
    suspicious_patterns = [
        re.compile(r"https?://", re.IGNORECASE),
        re.compile(r"\b\d{9,11}\b"),
    ]

    def moderate_inbound(self, text: str) -> ModerationStatus:
        value = text.lower()
        if any(word in value for word in self.blocked_words):
            return ModerationStatus.HUMAN_REVIEW
        if sum(1 for pattern in self.suspicious_patterns if pattern.search(value)) >= 2:
            return ModerationStatus.FLAG
        return ModerationStatus.ALLOW

    def moderate_outbound(self, text: str) -> ModerationStatus:
        if re.search(r"\b\d{9,11}\b", text):
            return ModerationStatus.BLOCK
        if "http" in text.lower() and "checkout" in text.lower():
            return ModerationStatus.BLOCK
        return ModerationStatus.ALLOW


moderation_service = ModerationService()
