from uuid import UUID

from app.core.database import db_connection
from app.services.media.publisher import DEMO_TENANT_ID


class ProductQueueService:
    async def add_product(
        self,
        *,
        live_id: str,
        product_id: str,
        product_variant_id: str | None = None,
        display_order: int | None = None,
        is_featured: bool = False,
        tenant_id: str = DEMO_TENANT_ID,
    ) -> dict:
        async with db_connection() as conn:
            order = display_order
            if order is None:
                order = await conn.fetchval(
                    """
                    SELECT COALESCE(MAX(display_order), 0) + 1
                    FROM live_session_products
                    WHERE tenant_id = $1 AND live_session_id = $2
                    """,
                    UUID(str(tenant_id)),
                    UUID(str(live_id)),
                )
            row = await conn.fetchrow(
                """
                INSERT INTO live_session_products (
                    tenant_id, live_session_id, product_id, product_variant_id,
                    display_order, is_featured, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, now())
                ON CONFLICT (live_session_id, product_id, product_variant_id) DO UPDATE SET
                    display_order = EXCLUDED.display_order,
                    is_featured = EXCLUDED.is_featured,
                    updated_at = now()
                RETURNING *
                """,
                UUID(str(tenant_id)),
                UUID(str(live_id)),
                UUID(str(product_id)),
                UUID(str(product_variant_id)) if product_variant_id else None,
                order,
                is_featured,
            )
            return dict(row)

    async def list_products(self, *, live_id: str, tenant_id: str = DEMO_TENANT_ID) -> list[dict]:
        async with db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    lsp.*,
                    p.code,
                    p.name,
                    p.description,
                    p.category,
                    v.sku_code,
                    v.color,
                    v.size,
                    v.price_vnd,
                    v.compare_at_price_vnd,
                    v.image_url,
                    i.on_hand_quantity,
                    i.reserved_quantity,
                    i.safety_stock_quantity
                FROM live_session_products lsp
                JOIN products p ON p.id = lsp.product_id
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM product_variants pv
                    WHERE pv.tenant_id = lsp.tenant_id
                      AND pv.product_id = lsp.product_id
                      AND (lsp.product_variant_id IS NULL OR pv.id = lsp.product_variant_id)
                    ORDER BY CASE WHEN pv.id = lsp.product_variant_id THEN 0 ELSE 1 END,
                             pv.created_at ASC
                    LIMIT 1
                ) v ON true
                LEFT JOIN inventory i ON i.product_variant_id = v.id
                WHERE lsp.tenant_id = $1 AND lsp.live_session_id = $2
                ORDER BY lsp.display_order ASC, lsp.created_at ASC
                """,
                UUID(str(tenant_id)),
                UUID(str(live_id)),
            )
            return [dict(row) for row in rows]

    async def reorder(self, *, live_id: str, items: list[dict], tenant_id: str = DEMO_TENANT_ID) -> list[dict]:
        async with db_connection() as conn:
            async with conn.transaction():
                for item in items:
                    await conn.execute(
                        """
                        UPDATE live_session_products
                        SET display_order = $4, updated_at = now()
                        WHERE tenant_id = $1 AND live_session_id = $2 AND id = $3
                        """,
                        UUID(str(tenant_id)),
                        UUID(str(live_id)),
                        UUID(str(item["item_id"])),
                        int(item["display_order"]),
                    )
        return await self.list_products(live_id=live_id, tenant_id=tenant_id)

    async def delete_product(self, *, live_id: str, item_id: str, tenant_id: str = DEMO_TENANT_ID) -> None:
        async with db_connection() as conn:
            await conn.execute(
                """
                DELETE FROM live_session_products
                WHERE tenant_id = $1 AND live_session_id = $2 AND id = $3
                """,
                UUID(str(tenant_id)),
                UUID(str(live_id)),
                UUID(str(item_id)),
            )

    async def prepare(self, *, live_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
        products = await self.list_products(live_id=live_id, tenant_id=tenant_id)
        async with db_connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM live_script_segments WHERE tenant_id = $1 AND live_session_id = $2",
                    UUID(str(tenant_id)),
                    UUID(str(live_id)),
                )
                display_order = 1
                created: list[dict] = []
                for item in products:
                    segments = self._segments_for_product(item)
                    for segment in segments:
                        row = await conn.fetchrow(
                            """
                            INSERT INTO live_script_segments (
                                tenant_id, live_session_id, live_session_product_id, product_id,
                                segment_type, display_order, speech_text, motion_code, overlay_json, status
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft')
                            RETURNING *
                            """,
                            UUID(str(tenant_id)),
                            UUID(str(live_id)),
                            item["id"],
                            item["product_id"],
                            segment["segment_type"],
                            display_order,
                            segment["speech_text"],
                            segment["motion_code"],
                            segment["overlay_json"],
                        )
                        created.append(dict(row))
                        display_order += 1
                first_segment = created[0] if created else None
                await conn.execute(
                    """
                    UPDATE live_sessions
                    SET current_product_id = $3,
                        current_segment_id = $4,
                        segment_offset_ms = 0,
                        previous_action = 'prepare',
                        director_state_json = jsonb_build_object('prepared_segments', $5::int),
                        updated_at = now()
                    WHERE tenant_id = $1 AND id = $2
                    """,
                    UUID(str(tenant_id)),
                    UUID(str(live_id)),
                    first_segment["product_id"] if first_segment else None,
                    first_segment["id"] if first_segment else None,
                    len(created),
                )
        return {"segments": created, "count": len(created)}

    def _segments_for_product(self, item: dict) -> list[dict]:
        product_name = item["name"]
        sku = item.get("sku_code") or item.get("code")
        price = item.get("price_vnd")
        on_hand = item.get("on_hand_quantity")
        reserved = item.get("reserved_quantity") or 0
        safety = item.get("safety_stock_quantity") or 0
        available = max(0, (on_hand or 0) - reserved - safety) if on_hand is not None else None
        overlay = {
            "type": "product_card",
            "product_id": str(item["product_id"]),
            "product_variant_id": str(item["product_variant_id"]) if item["product_variant_id"] else None,
            "position": "right",
        }
        segments = [
            {
                "segment_type": "introduction",
                "speech_text": f"Tiếp theo là {product_name}, mã {sku}.",
                "motion_code": "present_product",
                "overlay_json": overlay,
            }
        ]
        if price is not None:
            segments.append(
                {
                    "segment_type": "price",
                    "speech_text": f"Mẫu này đang có giá {int(price):,} đồng.".replace(",", "."),
                    "motion_code": "point_right",
                    "overlay_json": overlay,
                }
            )
        if available is not None:
            segments.append(
                {
                    "segment_type": "stock",
                    "speech_text": f"Hiện sản phẩm còn khoảng {available} sản phẩm sẵn để chốt.",
                    "motion_code": "talk_calm",
                    "overlay_json": overlay,
                }
            )
        segments.append(
            {
                "segment_type": "call_to_action",
                "speech_text": f"Anh chị muốn chốt {product_name} thì bình luận mã {sku} kèm màu và size giúp em.",
                "motion_code": "wave",
                "overlay_json": overlay,
            }
        )
        return segments


product_queue_service = ProductQueueService()
