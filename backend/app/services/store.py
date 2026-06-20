from datetime import timedelta

from app.models.domain import (
    AuditLog,
    Cart,
    CartItem,
    CartStatus,
    Conversation,
    ConversationStatus,
    Customer,
    FacebookPage,
    Inventory,
    InventoryReservation,
    LiveComment,
    LiveSession,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductVariant,
    ReservationStatus,
    ResponseJob,
    Tenant,
    ViewerProfile,
    WebhookEvent,
    default_reservation_expiry,
    utcnow,
)


class InMemoryStore:
    """Temporary MVP store.

    This keeps the scaffold runnable without migrations. Replace with Postgres
    repositories and row locks before production inventory/order handling.
    """

    def __init__(self) -> None:
        self.tenants: dict[str, Tenant] = {}
        self.facebook_pages: dict[str, FacebookPage] = {}
        self.live_sessions: dict[str, LiveSession] = {}
        self.comments: dict[str, LiveComment] = {}
        self.jobs: dict[str, ResponseJob] = {}
        self.products: dict[str, Product] = {}
        self.variants: dict[str, ProductVariant] = {}
        self.inventory: dict[str, Inventory] = {}
        self.reservations: dict[str, InventoryReservation] = {}
        self.viewers: dict[str, ViewerProfile] = {}
        self.customers: dict[str, Customer] = {}
        self.conversations: dict[str, Conversation] = {}
        self.carts: dict[str, Cart] = {}
        self.orders: dict[str, Order] = {}
        self.webhook_events: dict[str, WebhookEvent] = {}
        self.audit_logs: list[AuditLog] = []
        self.seed_demo_data()

    def seed_demo_data(self) -> None:
        tenant = Tenant(id="demo-tenant", name="Demo Store")
        self.tenants[tenant.id] = tenant
        page = FacebookPage(
            id="demo-facebook-page",
            tenant_id=tenant.id,
            page_id="demo-page",
            page_name="Demo Fashion Live",
            webhook_status="local",
        )
        self.facebook_pages[page.id] = page

        product_a12 = Product(id="product-a12", tenant_id=tenant.id, code="A12", name="Áo thun cotton")
        product_b08 = Product(id="product-b08", tenant_id=tenant.id, code="B08", name="Váy nữ basic")
        self.products[product_a12.id] = product_a12
        self.products[product_b08.id] = product_b08

        seed_variants = [
            ProductVariant(
                id="variant-a12-red-m",
                tenant_id=tenant.id,
                product_id=product_a12.id,
                sku_code="A12",
                color="đỏ",
                size="M",
                price_vnd=199_000,
            ),
            ProductVariant(
                id="variant-a12-red-l",
                tenant_id=tenant.id,
                product_id=product_a12.id,
                sku_code="A12",
                color="đỏ",
                size="L",
                price_vnd=199_000,
            ),
            ProductVariant(
                id="variant-a12-black-m",
                tenant_id=tenant.id,
                product_id=product_a12.id,
                sku_code="A12",
                color="đen",
                size="M",
                price_vnd=199_000,
            ),
            ProductVariant(
                id="variant-b08-black-s",
                tenant_id=tenant.id,
                product_id=product_b08.id,
                sku_code="B08",
                color="đen",
                size="S",
                price_vnd=349_000,
            ),
        ]
        for index, variant in enumerate(seed_variants):
            self.variants[variant.id] = variant
            self.inventory[variant.id] = Inventory(
                id=f"inventory-{variant.id}",
                tenant_id=tenant.id,
                product_variant_id=variant.id,
                on_hand_quantity=20 - index * 3,
                safety_stock_quantity=1,
            )

    def create_live(self, live: LiveSession) -> LiveSession:
        self.live_sessions[live.id] = live
        return live

    def list_lives(self) -> list[LiveSession]:
        return sorted(self.live_sessions.values(), key=lambda item: item.created_at, reverse=True)

    def get_live(self, live_id: str) -> LiveSession | None:
        return self.live_sessions.get(live_id)

    def save_comment(self, comment: LiveComment) -> LiveComment:
        comment.live_session_id = comment.live_session_id or comment.live_id
        comment.external_comment_id = comment.external_comment_id or comment.facebook_comment_id
        self.comments[comment.id] = comment
        return comment

    def find_comment_by_external_id(self, facebook_page_id: str | None, external_comment_id: str | None) -> LiveComment | None:
        if not external_comment_id:
            return None
        for comment in self.comments.values():
            if comment.facebook_page_id == facebook_page_id and comment.external_comment_id == external_comment_id:
                return comment
        return None

    def list_comments(self, live_id: str) -> list[LiveComment]:
        return sorted(
            [comment for comment in self.comments.values() if comment.live_id == live_id],
            key=lambda item: item.created_at,
        )

    def save_job(self, job: ResponseJob) -> ResponseJob:
        self.jobs[job.id] = job
        return job

    def list_jobs(self, live_id: str) -> list[ResponseJob]:
        return sorted(
            [job for job in self.jobs.values() if job.live_id == live_id],
            key=lambda item: item.created_at,
        )

    def save_webhook_event(self, event: WebhookEvent) -> tuple[WebhookEvent, bool]:
        key = event.external_event_id or event.payload_hash
        existing = self.webhook_events.get(key)
        if existing:
            return existing, False
        self.webhook_events[key] = event
        return event, True

    def list_products(self) -> list[Product]:
        return sorted(self.products.values(), key=lambda item: item.code)

    def list_variants(self, product_id: str | None = None) -> list[ProductVariant]:
        variants = self.variants.values()
        if product_id:
            variants = [variant for variant in variants if variant.product_id == product_id]
        return sorted(variants, key=lambda item: (item.sku_code, item.color or "", item.size or ""))

    def find_variant(self, sku_code: str, color: str | None = None, size: str | None = None) -> ProductVariant | None:
        sku = sku_code.upper()
        candidates = [variant for variant in self.variants.values() if variant.sku_code.upper() == sku]
        if color:
            candidates = [variant for variant in candidates if (variant.color or "").lower() == color.lower()]
        if size:
            candidates = [variant for variant in candidates if (variant.size or "").lower() == size.lower()]
        return candidates[0] if len(candidates) == 1 else None

    def list_inventory(self) -> list[Inventory]:
        return sorted(self.inventory.values(), key=lambda item: item.product_variant_id)

    def adjust_inventory(self, product_variant_id: str, quantity_delta: int) -> Inventory:
        item = self.inventory[product_variant_id]
        item.on_hand_quantity += quantity_delta
        item.updated_at = utcnow()
        return item

    def get_or_create_viewer(self, live: LiveSession | None, display_name: str, viewer_hash: str) -> ViewerProfile:
        for viewer in self.viewers.values():
            if viewer.external_viewer_id_hash == viewer_hash:
                viewer.last_seen_at = utcnow()
                return viewer
        viewer = ViewerProfile(
            tenant_id=live.tenant_id if live else "demo-tenant",
            facebook_page_id=live.facebook_page_id if live else "demo-facebook-page",
            external_viewer_id_hash=viewer_hash,
            display_name=display_name,
        )
        self.viewers[viewer.id] = viewer
        return viewer

    def get_or_create_conversation(self, live_id: str, viewer_id: str) -> Conversation:
        for conversation in self.conversations.values():
            if conversation.live_session_id == live_id and conversation.viewer_profile_id == viewer_id:
                return conversation
        conversation = Conversation(live_session_id=live_id, viewer_profile_id=viewer_id)
        self.conversations[conversation.id] = conversation
        return conversation

    def take_over_conversation(self, conversation_id: str, owner_id: str | None = "operator") -> Conversation | None:
        conversation = self.conversations.get(conversation_id)
        if not conversation:
            return None
        conversation.status = ConversationStatus.HUMAN_TAKEOVER
        conversation.ai_enabled = False
        conversation.human_owner_id = owner_id
        conversation.updated_at = utcnow()
        return conversation

    def release_conversation_ai(self, conversation_id: str) -> Conversation | None:
        conversation = self.conversations.get(conversation_id)
        if not conversation:
            return None
        conversation.status = ConversationStatus.AI_ACTIVE
        conversation.ai_enabled = True
        conversation.human_owner_id = None
        conversation.updated_at = utcnow()
        return conversation

    def reserve_inventory(
        self,
        *,
        product_variant_id: str,
        quantity: int,
        idempotency_key: str,
        ttl_minutes: int,
        cart_id: str | None = None,
        order_id: str | None = None,
    ) -> InventoryReservation:
        for reservation in self.reservations.values():
            if reservation.idempotency_key == idempotency_key:
                return reservation
        inventory = self.inventory[product_variant_id]
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")
        if inventory.available_quantity < quantity:
            raise ValueError("Insufficient inventory")
        inventory.reserved_quantity += quantity
        inventory.updated_at = utcnow()
        reservation = InventoryReservation(
            product_variant_id=product_variant_id,
            cart_id=cart_id,
            order_id=order_id,
            quantity=quantity,
            expires_at=default_reservation_expiry(ttl_minutes),
            idempotency_key=idempotency_key,
        )
        self.reservations[reservation.id] = reservation
        return reservation

    def release_expired_reservations(self) -> int:
        count = 0
        now = utcnow()
        for reservation in self.reservations.values():
            if reservation.status != ReservationStatus.ACTIVE or reservation.expires_at > now:
                continue
            inventory = self.inventory[reservation.product_variant_id]
            inventory.reserved_quantity = max(0, inventory.reserved_quantity - reservation.quantity)
            inventory.updated_at = now
            reservation.status = ReservationStatus.EXPIRED
            reservation.released_at = now
            reservation.updated_at = now
            count += 1
        return count

    def create_cart_and_order(
        self,
        *,
        live_id: str,
        viewer_id: str,
        variant: ProductVariant,
        quantity: int,
        reservation: InventoryReservation | None = None,
    ) -> tuple[Cart, Order]:
        total = variant.price_vnd * quantity
        cart = Cart(
            viewer_profile_id=viewer_id,
            live_session_id=live_id,
            status=CartStatus.RESERVED if reservation else CartStatus.DRAFT,
            subtotal_vnd=total,
            total_vnd=total,
            expires_at=reservation.expires_at if reservation else utcnow() + timedelta(minutes=10),
        )
        cart_item = CartItem(
            cart_id=cart.id,
            product_variant_id=variant.id,
            quantity=quantity,
            unit_price_vnd=variant.price_vnd,
            total_vnd=total,
            price_snapshot_json={"sku_code": variant.sku_code, "color": variant.color, "size": variant.size},
        )
        cart.items.append(cart_item)
        self.carts[cart.id] = cart

        order = Order(
            cart_id=cart.id,
            live_session_id=live_id,
            order_number=f"DTP-{len(self.orders) + 1:06d}",
            status=OrderStatus.STOCK_RESERVED if reservation else OrderStatus.DRAFT,
            total_vnd=total,
        )
        order_item = OrderItem(
            order_id=order.id,
            product_variant_id=variant.id,
            sku_snapshot_json={"sku_code": variant.sku_code, "color": variant.color, "size": variant.size},
            quantity=quantity,
            unit_price_vnd=variant.price_vnd,
            total_vnd=total,
        )
        order.items.append(order_item)
        self.orders[order.id] = order
        if reservation:
            reservation.cart_id = cart.id
            reservation.order_id = order.id
        return cart, order

    def audit(self, log: AuditLog) -> AuditLog:
        self.audit_logs.append(log)
        return log


store = InMemoryStore()
