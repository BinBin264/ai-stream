from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class LiveStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PREPARING = "preparing"
    PREVIEW = "preview"
    LIVE = "live"
    DRAINING = "draining"
    ENDED = "ended"
    STOPPED = "stopped"
    FAILED = "failed"
    ERROR = "error"


class CommentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    FAILED = "failed"


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ProductStatus(StrEnum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    RELEASED = "released"
    CANCELLED = "cancelled"


class ConversationStatus(StrEnum):
    AI_ACTIVE = "ai_active"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_PAYMENT = "waiting_payment"
    HUMAN_TAKEOVER = "human_takeover"
    CLOSED = "closed"
    BLOCKED = "blocked"


class CommerceIntent(StrEnum):
    CREATE_ORDER = "CREATE_ORDER"
    UPDATE_ORDER = "UPDATE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    PRODUCT_QUESTION = "PRODUCT_QUESTION"
    PRICE_QUESTION = "PRICE_QUESTION"
    SHIPPING_QUESTION = "SHIPPING_QUESTION"
    PAYMENT_QUESTION = "PAYMENT_QUESTION"
    HUMAN_HANDOVER = "HUMAN_HANDOVER"
    SMALL_TALK = "SMALL_TALK"
    UNKNOWN = "UNKNOWN"


class ModerationStatus(StrEnum):
    ALLOW = "allow"
    FLAG = "flag"
    BLOCK = "block"
    HUMAN_REVIEW = "human_review"


class CartStatus(StrEnum):
    DRAFT = "draft"
    RESERVED = "reserved"
    WAITING_CONTACT = "waiting_contact"
    WAITING_PAYMENT = "waiting_payment"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OrderStatus(StrEnum):
    DRAFT = "draft"
    WAITING_VARIANT = "waiting_variant"
    WAITING_CONTACT = "waiting_contact"
    STOCK_RESERVED = "stock_reserved"
    WAITING_PAYMENT = "waiting_payment"
    PAID = "paid"
    COD_CONFIRMED = "cod_confirmed"
    FULFILLMENT = "fulfillment"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    MANUAL_REVIEW = "manual_review"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LiveSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    facebook_page_id: str | None = None
    title: str
    status: LiveStatus = LiveStatus.DRAFT
    facebook_live_video_id: str | None = None
    external_live_video_id: str | None = None
    rtmps_url: str | None = None
    stream_key: str | None = None
    media_provider: str = "ffmpeg"
    settings_json: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class LiveComment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    facebook_page_id: str | None = None
    live_id: str
    live_session_id: str | None = None
    facebook_comment_id: str | None = None
    external_comment_id: str | None = None
    external_parent_comment_id: str | None = None
    viewer_profile_id: str | None = None
    user_name: str
    text: str
    normalized_text: str | None = None
    moderation_status: ModerationStatus = ModerationStatus.ALLOW
    status: CommentStatus = CommentStatus.QUEUED
    priority: int = 0
    raw_payload_reference: str | None = None
    processing_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    processed_at: datetime | None = None


class ResponseJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    live_id: str
    comment_id: str
    prompt: str
    status: str = "queued"
    response_text: str | None = None
    media_path: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Tenant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class FacebookPage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    page_id: str
    page_name: str
    encrypted_page_access_token: str | None = None
    token_expires_at: datetime | None = None
    webhook_status: str = "not_connected"
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Product(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    code: str
    name: str
    description: str = ""
    status: ProductStatus = ProductStatus.ACTIVE
    category: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProductVariant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    product_id: str
    sku_code: str
    color: str | None = None
    size: str | None = None
    attributes_json: dict = Field(default_factory=dict)
    price_vnd: int
    compare_at_price_vnd: int | None = None
    status: ProductStatus = ProductStatus.ACTIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Inventory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    product_variant_id: str
    on_hand_quantity: int
    reserved_quantity: int = 0
    safety_stock_quantity: int = 0
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def available_quantity(self) -> int:
        return self.on_hand_quantity - self.reserved_quantity - self.safety_stock_quantity


class InventoryReservation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    product_variant_id: str
    cart_id: str | None = None
    order_id: str | None = None
    quantity: int
    status: ReservationStatus = ReservationStatus.ACTIVE
    expires_at: datetime
    released_at: datetime | None = None
    idempotency_key: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ViewerProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    facebook_page_id: str | None = None
    external_viewer_id_hash: str
    display_name: str
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)


class Customer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    viewer_profile_id: str
    phone_encrypted: str | None = None
    email_encrypted: str | None = None
    address_encrypted: str | None = None
    consent_status: str = "unknown"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    live_session_id: str
    viewer_profile_id: str
    status: ConversationStatus = ConversationStatus.AI_ACTIVE
    ai_enabled: bool = True
    human_owner_id: str | None = None
    last_intent: CommerceIntent | None = None
    last_context_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CartItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    cart_id: str
    product_variant_id: str
    quantity: int
    unit_price_vnd: int
    total_vnd: int
    price_snapshot_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class Cart(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    customer_id: str | None = None
    viewer_profile_id: str
    live_session_id: str
    status: CartStatus = CartStatus.DRAFT
    currency: str = "VND"
    subtotal_vnd: int = 0
    discount_vnd: int = 0
    shipping_fee_vnd: int = 0
    total_vnd: int = 0
    expires_at: datetime | None = None
    items: list[CartItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class OrderItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    product_variant_id: str
    sku_snapshot_json: dict
    quantity: int
    unit_price_vnd: int
    total_vnd: int
    created_at: datetime = Field(default_factory=utcnow)


class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    cart_id: str
    customer_id: str | None = None
    live_session_id: str
    order_number: str
    status: OrderStatus = OrderStatus.DRAFT
    total_vnd: int = 0
    payment_status: PaymentStatus = PaymentStatus.PENDING
    fulfillment_status: str = "pending"
    items: list[OrderItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class WebhookEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    provider: str = "meta"
    external_event_id: str | None = None
    event_type: str
    page_id: str | None = None
    payload_json: dict
    payload_hash: str
    status: str = "received"
    received_at: datetime = Field(default_factory=utcnow)
    processed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class AuditLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    actor_type: str
    actor_id: str | None = None
    action: str
    entity_type: str
    entity_id: str
    before_json: dict | None = None
    after_json: dict | None = None
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ParsedCommerceIntent(BaseModel):
    intent: CommerceIntent = CommerceIntent.UNKNOWN
    confidence: float = 0
    sku_codes: list[str] = Field(default_factory=list)
    color: str | None = None
    size: str | None = None
    quantity: int | None = None
    missing_fields: list[str] = Field(default_factory=list)
    requires_human: bool = False
    reason_code: str = "NONE"
    raw_text: str


class SpeechQueueItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    live_session_id: str | None = None
    source_comment_id: str | None = None
    text: str
    voice: str = "default"
    priority: str = "P4"
    status: str = "queued"
    audio_url: str | None = None
    error_message: str | None = None
    attempt_count: int = 0
    scheduled_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CommercePipelineResult(BaseModel):
    comment: LiveComment
    conversation: Conversation | None = None
    parsed_intent: ParsedCommerceIntent
    cart: Cart | None = None
    order: Order | None = None
    reservation: InventoryReservation | None = None
    reply_text: str
    speech_item: SpeechQueueItem | None = None


def default_reservation_expiry(minutes: int) -> datetime:
    return utcnow() + timedelta(minutes=minutes)
