from app.core.config import settings
from app.models.domain import ProductVariant


class ReplyPolicyService:
    def order_reserved(self, variant: ProductVariant, quantity: int) -> str:
        variant_label = " ".join(part for part in [variant.color, variant.size] if part)
        return (
            f"Em đã giữ {quantity} sản phẩm {variant.sku_code} {variant_label} "
            f"cho mình trong {settings.DEFAULT_RESERVATION_TTL_MINUTES} phút ạ."
        ).strip()

    def missing_variant(self, sku: str, missing: list[str]) -> str:
        fields = ", ".join(missing) if missing else "màu hoặc size"
        return f"Mẫu {sku} còn thiếu thông tin {fields}. Mình gửi lại giúp em để giữ hàng chính xác nhé."

    def out_of_stock(self, sku: str) -> str:
        return f"Dạ mẫu {sku} hiện không đủ số lượng để giữ hàng. Em chuyển tư vấn viên kiểm tra thêm cho mình ạ."

    def human_handover(self) -> str:
        return "Em đã chuyển thông tin cho tư vấn viên hỗ trợ mình ngay ạ."

    def low_confidence(self) -> str:
        return "Em chưa chắc thông tin sản phẩm của mình. Mình gửi lại mã sản phẩm, màu và size giúp em nhé."

    def product_question(self, sku: str | None = None) -> str:
        if sku:
            return f"Em đã nhận câu hỏi về mẫu {sku}. Em sẽ kiểm tra thông tin sản phẩm cho mình ạ."
        return "Em đã nhận câu hỏi của mình. Mình gửi thêm mã sản phẩm để em kiểm tra chính xác nhé."


reply_policy = ReplyPolicyService()
