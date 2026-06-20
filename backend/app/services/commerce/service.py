import hashlib

from app.core.config import settings
from app.models.domain import (
    AuditLog,
    CommerceIntent,
    CommercePipelineResult,
    CommentStatus,
    ConversationStatus,
    LiveComment,
    ModerationStatus,
    OrderStatus,
)
from app.services.comments.normalizer import comment_normalizer
from app.services.comments.rule_parser import purchase_intent_rule_parser
from app.services.media.publisher import media_publisher
from app.services.moderation.service import moderation_service
from app.services.reply.policy import reply_policy
from app.services.store import store


class CommercePipelineService:
    async def process_comment(self, comment: LiveComment) -> CommercePipelineResult:
        live = store.get_live(comment.live_id)
        viewer_hash = self._viewer_hash(comment.facebook_comment_id or comment.user_name)
        viewer = store.get_or_create_viewer(live, comment.user_name, viewer_hash)
        comment.viewer_profile_id = viewer.id
        conversation = store.get_or_create_conversation(comment.live_id, viewer.id)

        comment.status = CommentStatus.PROCESSING
        comment.normalized_text = comment_normalizer.normalize(comment.text)
        comment.moderation_status = moderation_service.moderate_inbound(comment.normalized_text)
        store.save_comment(comment)

        parsed = purchase_intent_rule_parser.parse(comment.normalized_text)
        conversation.last_intent = parsed.intent
        conversation.last_context_json = parsed.model_dump()

        if comment.moderation_status in {ModerationStatus.BLOCK, ModerationStatus.FLAG, ModerationStatus.HUMAN_REVIEW}:
            conversation.status = ConversationStatus.HUMAN_TAKEOVER
            conversation.ai_enabled = False
            reply = reply_policy.human_handover()
            comment.status = CommentStatus.SKIPPED
            store.save_comment(comment)
            return CommercePipelineResult(
                comment=comment,
                conversation=conversation,
                parsed_intent=parsed,
                reply_text=reply,
            )

        if not conversation.ai_enabled or conversation.status == ConversationStatus.HUMAN_TAKEOVER:
            reply = reply_policy.human_handover()
            comment.status = CommentStatus.SKIPPED
            store.save_comment(comment)
            return CommercePipelineResult(
                comment=comment,
                conversation=conversation,
                parsed_intent=parsed,
                reply_text=reply,
            )

        if parsed.requires_human or parsed.confidence < settings.AI_HUMAN_HANDOVER_CONFIDENCE_THRESHOLD:
            store.take_over_conversation(conversation.id)
            reply = reply_policy.human_handover() if parsed.requires_human else reply_policy.low_confidence()
            comment.status = CommentStatus.ANSWERED
            store.save_comment(comment)
            return CommercePipelineResult(
                comment=comment,
                conversation=conversation,
                parsed_intent=parsed,
                reply_text=reply,
            )

        if parsed.intent == CommerceIntent.CREATE_ORDER:
            return await self._create_order(comment, conversation, parsed)

        if parsed.intent in {CommerceIntent.PRODUCT_QUESTION, CommerceIntent.PRICE_QUESTION, CommerceIntent.SHIPPING_QUESTION}:
            reply = reply_policy.product_question(parsed.sku_codes[0] if parsed.sku_codes else None)
        elif parsed.intent == CommerceIntent.CANCEL_ORDER:
            reply = "Em đã nhận yêu cầu hủy. Tư vấn viên sẽ kiểm tra đơn đang hoạt động và hỗ trợ mình ạ."
        else:
            reply = reply_policy.low_confidence()

        comment.status = CommentStatus.ANSWERED
        store.save_comment(comment)
        speech_item = await self._queue_speech_if_allowed(comment, reply, "P4")
        return CommercePipelineResult(
            comment=comment,
            conversation=conversation,
            parsed_intent=parsed,
            reply_text=reply,
            speech_item=speech_item,
        )

    async def _create_order(self, comment, conversation, parsed):
        sku = parsed.sku_codes[0] if parsed.sku_codes else ""
        if parsed.missing_fields or not sku:
            reply = reply_policy.missing_variant(sku or "sản phẩm", parsed.missing_fields)
            comment.status = CommentStatus.ANSWERED
            store.save_comment(comment)
            return CommercePipelineResult(comment=comment, conversation=conversation, parsed_intent=parsed, reply_text=reply)

        variant = store.find_variant(sku, parsed.color, parsed.size)
        if not variant:
            missing = []
            if not parsed.color:
                missing.append("màu")
            if not parsed.size:
                missing.append("size")
            reply = reply_policy.missing_variant(sku, missing or ["biến thể"])
            comment.status = CommentStatus.ANSWERED
            store.save_comment(comment)
            return CommercePipelineResult(comment=comment, conversation=conversation, parsed_intent=parsed, reply_text=reply)

        quantity = parsed.quantity or 1
        try:
            reservation = store.reserve_inventory(
                product_variant_id=variant.id,
                quantity=quantity,
                idempotency_key=f"comment:{comment.id}:variant:{variant.id}",
                ttl_minutes=settings.DEFAULT_RESERVATION_TTL_MINUTES,
            )
        except ValueError:
            reply = reply_policy.out_of_stock(sku)
            store.take_over_conversation(conversation.id)
            comment.status = CommentStatus.ANSWERED
            store.save_comment(comment)
            return CommercePipelineResult(comment=comment, conversation=conversation, parsed_intent=parsed, reply_text=reply)

        cart, order = store.create_cart_and_order(
            live_id=comment.live_id,
            viewer_id=conversation.viewer_profile_id,
            variant=variant,
            quantity=quantity,
            reservation=reservation,
        )
        if order.total_vnd >= settings.ORDER_HIGH_VALUE_REVIEW_THRESHOLD_VND:
            order.status = OrderStatus.MANUAL_REVIEW
            store.take_over_conversation(conversation.id)

        reply = reply_policy.order_reserved(variant, quantity)
        outbound_status = moderation_service.moderate_outbound(reply)
        if outbound_status == ModerationStatus.BLOCK:
            reply = reply_policy.human_handover()

        store.audit(
            AuditLog(
                actor_type="system",
                action="inventory.reserved",
                entity_type="order",
                entity_id=order.id,
                after_json={"reservation_id": reservation.id, "comment_id": comment.id},
            )
        )
        comment.status = CommentStatus.ANSWERED
        store.save_comment(comment)
        speech_item = await self._queue_speech_if_allowed(comment, reply, "P1")
        return CommercePipelineResult(
            comment=comment,
            conversation=conversation,
            parsed_intent=parsed,
            cart=cart,
            order=order,
            reservation=reservation,
            reply_text=reply,
            speech_item=speech_item,
        )

    async def _queue_speech_if_allowed(self, comment: LiveComment, reply: str, priority: str):
        if comment.moderation_status != ModerationStatus.ALLOW:
            return None
        return await media_publisher.queue_speech(
            live_session_id=comment.live_id,
            source_comment_id=comment.id,
            text=reply,
            priority=priority,
        )

    def _viewer_hash(self, raw: str) -> str:
        value = f"{settings.PII_HASH_SALT}:{raw}"
        return hashlib.sha256(value.encode()).hexdigest()


commerce_pipeline = CommercePipelineService()
