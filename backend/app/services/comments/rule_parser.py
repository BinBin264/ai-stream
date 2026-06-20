import re

from app.core.config import settings
from app.models.domain import CommerceIntent, ParsedCommerceIntent


class PurchaseIntentRuleParser:
    order_words = {"chốt", "lấy", "mua", "cho", "đặt"}
    cancel_words = {"hủy", "huỷ", "cancel"}
    human_words = {"tư vấn viên", "người thật", "nhân viên", "gặp shop"}
    price_words = {"giá", "bao nhiêu", "nhiêu tiền"}
    shipping_words = {"ship", "giao", "vận chuyển"}
    color_words = {"đỏ", "đen", "trắng", "vàng", "xanh", "hồng", "tím", "nâu", "be"}

    def parse(self, text: str) -> ParsedCommerceIntent:
        normalized = text.lower()
        sku_codes = [match.upper() for match in re.findall(r"\b[a-zA-Z]\d{2,}\b", normalized)]
        quantity = self._extract_quantity(normalized)
        color = self._extract_color(normalized)
        size = self._extract_size(normalized)

        if any(word in normalized for word in self.human_words):
            return ParsedCommerceIntent(
                intent=CommerceIntent.HUMAN_HANDOVER,
                confidence=0.9,
                raw_text=text,
                requires_human=True,
                reason_code="CUSTOMER_REQUEST",
            )
        if any(word in normalized for word in self.cancel_words):
            return ParsedCommerceIntent(
                intent=CommerceIntent.CANCEL_ORDER,
                confidence=0.8,
                sku_codes=sku_codes,
                raw_text=text,
            )
        if any(word in normalized for word in self.shipping_words):
            return ParsedCommerceIntent(intent=CommerceIntent.SHIPPING_QUESTION, confidence=0.75, raw_text=text)
        if any(word in normalized for word in self.price_words):
            return ParsedCommerceIntent(
                intent=CommerceIntent.PRICE_QUESTION,
                confidence=0.75,
                sku_codes=sku_codes,
                raw_text=text,
            )

        starts_like_order = any(word in normalized.split()[:3] for word in self.order_words)
        if starts_like_order or sku_codes:
            missing = []
            if not sku_codes:
                missing.append("sku_code")
            if quantity is None:
                quantity = 1
            if quantity > settings.MAX_ORDER_QUANTITY_PER_ITEM:
                return ParsedCommerceIntent(
                    intent=CommerceIntent.HUMAN_HANDOVER,
                    confidence=0.85,
                    sku_codes=sku_codes,
                    color=color,
                    size=size,
                    quantity=quantity,
                    missing_fields=[],
                    requires_human=True,
                    reason_code="QUANTITY_LIMIT",
                    raw_text=text,
                )
            confidence = 0.9 if starts_like_order and sku_codes else 0.65
            return ParsedCommerceIntent(
                intent=CommerceIntent.CREATE_ORDER if starts_like_order else CommerceIntent.PRODUCT_QUESTION,
                confidence=confidence,
                sku_codes=sku_codes,
                color=color,
                size=size,
                quantity=quantity,
                missing_fields=missing,
                raw_text=text,
            )

        return ParsedCommerceIntent(intent=CommerceIntent.UNKNOWN, confidence=0.2, raw_text=text)

    def _extract_quantity(self, text: str) -> int | None:
        match = re.search(r"\b(\d+)\s*(cái|c)\b", text)
        if match:
            return int(match.group(1))
        match = re.search(r"\b(\d+)\b", text)
        if match and not re.search(r"\b[a-zA-Z]\d+\b", text):
            return int(match.group(1))
        return None

    def _extract_color(self, text: str) -> str | None:
        for color in self.color_words:
            if re.search(rf"\b{re.escape(color)}\b", text):
                return color
        return None

    def _extract_size(self, text: str) -> str | None:
        match = re.search(r"\b(?:size\s*)?(xs|s|m|l|xl|xxl)\b", text, re.IGNORECASE)
        return match.group(1).upper() if match else None


purchase_intent_rule_parser = PurchaseIntentRuleParser()
