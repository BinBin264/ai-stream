import unicodedata
import json
from dataclasses import dataclass
from uuid import UUID

import asyncpg
import httpx

from app.core.config import settings

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@dataclass
class PancakeProductSyncStats:
    products: int
    variations: int
    inventory_items: int


class PancakeProductSyncService:
    """Sync Pancake POS product variations into live commerce Postgres tables."""

    def _db_url(self) -> str:
        return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

    def _tenant_uuid(self, tenant_id: str) -> UUID:
        return UUID(str(tenant_id))

    async def preview_products(self, shop_id: str, api_key: str, search: str = "") -> list[dict]:
        variations = await self._fetch_variations(shop_id, api_key, search)
        summary: dict[str, dict] = {}
        for item in variations:
            if item.get("is_removed") or item.get("is_hidden"):
                continue
            product_id = str(item.get("product_id") or "").strip()
            if not product_id:
                continue
            product = item.get("product") or {}
            if product_id not in summary:
                summary[product_id] = {
                    "product_id": product_id,
                    "product_name": product.get("name", ""),
                    "display_id": product.get("display_id", ""),
                    "custom_id": product.get("custom_id", ""),
                    "category": ", ".join(c.get("name", "") for c in product.get("categories", [])),
                    "variation_count": 0,
                    "base_price": item.get("retail_price", 0),
                }
            summary[product_id]["variation_count"] += 1
        return list(summary.values())

    async def list_shops(self, tenant_id: str) -> list[dict]:
        conn = await asyncpg.connect(self._db_url())
        try:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, shop_id, shop_name, sync_status,
                       last_synced_at, last_sync_error, created_at, updated_at
                FROM pancake_shops
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                """,
                self._tenant_uuid(tenant_id),
            )
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    async def list_catalog(self, tenant_id: str) -> list[dict]:
        conn = await asyncpg.connect(self._db_url())
        try:
            rows = await conn.fetch(
                """
                SELECT
                    p.id AS product_id,
                    p.external_product_id,
                    p.source,
                    p.code,
                    p.name,
                    p.display_id AS product_display_id,
                    p.custom_id AS product_custom_id,
                    p.description,
                    p.category,
                    v.id AS variant_id,
                    v.external_variation_id,
                    v.sku_code,
                    v.display_id AS variant_display_id,
                    v.custom_id AS variant_custom_id,
                    v.color,
                    v.size,
                    v.price_vnd,
                    v.barcode,
                    v.image_url,
                    i.on_hand_quantity,
                    i.reserved_quantity,
                    i.safety_stock_quantity
                FROM products p
                LEFT JOIN product_variants v ON v.product_id = p.id
                LEFT JOIN inventory i ON i.product_variant_id = v.id
                WHERE p.tenant_id = $1
                ORDER BY p.name, v.color, v.size
                """,
                self._tenant_uuid(tenant_id),
            )
            products: dict[str, dict] = {}
            for row in rows:
                product_id = str(row["product_id"])
                product = products.setdefault(
                    product_id,
                    {
                        "id": product_id,
                        "external_product_id": row["external_product_id"],
                        "source": row["source"],
                        "code": row["code"],
                        "name": row["name"],
                        "display_id": row["product_display_id"],
                        "custom_id": row["product_custom_id"],
                        "description": row["description"],
                        "category": row["category"],
                        "variants": [],
                    },
                )
                if row["variant_id"]:
                    product["variants"].append(
                        {
                            "id": str(row["variant_id"]),
                            "external_variation_id": row["external_variation_id"],
                            "sku_code": row["sku_code"],
                            "display_id": row["variant_display_id"],
                            "custom_id": row["variant_custom_id"],
                            "color": row["color"],
                            "size": row["size"],
                            "price_vnd": row["price_vnd"],
                            "barcode": row["barcode"],
                            "image_url": row["image_url"],
                            "inventory": {
                                "on_hand_quantity": row["on_hand_quantity"] or 0,
                                "reserved_quantity": row["reserved_quantity"] or 0,
                                "safety_stock_quantity": row["safety_stock_quantity"] or 0,
                            },
                        }
                    )
            return list(products.values())
        finally:
            await conn.close()

    async def save_shop(
        self,
        *,
        tenant_id: str,
        shop_id: str,
        api_key: str,
        shop_name: str | None = None,
    ) -> dict:
        conn = await asyncpg.connect(self._db_url())
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO pancake_shops (
                    tenant_id, shop_id, shop_name, encrypted_api_key, updated_at
                )
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (tenant_id, shop_id) DO UPDATE SET
                    shop_name = COALESCE(EXCLUDED.shop_name, pancake_shops.shop_name),
                    encrypted_api_key = EXCLUDED.encrypted_api_key,
                    updated_at = now()
                RETURNING id, tenant_id, shop_id, shop_name, sync_status,
                          last_synced_at, last_sync_error, created_at, updated_at
                """,
                self._tenant_uuid(tenant_id),
                shop_id,
                shop_name,
                self._encrypt_placeholder(api_key),
            )
            return dict(row)
        finally:
            await conn.close()

    async def get_shop_credentials(self, tenant_id: str, pancake_shop_id: str) -> tuple[str, str]:
        conn = await asyncpg.connect(self._db_url())
        try:
            row = await conn.fetchrow(
                """
                SELECT shop_id, encrypted_api_key
                FROM pancake_shops
                WHERE tenant_id = $1 AND id = $2
                """,
                self._tenant_uuid(tenant_id),
                UUID(str(pancake_shop_id)),
            )
            if not row:
                raise ValueError("Pancake shop not found")
            return row["shop_id"], self._decrypt_placeholder(row["encrypted_api_key"] or "")
        finally:
            await conn.close()

    async def sync(
        self,
        *,
        tenant_id: str,
        shop_id: str,
        api_key: str,
        search: str = "",
        product_ids: list[str] | None = None,
        shop_name: str | None = None,
    ) -> PancakeProductSyncStats:
        await self.save_shop(tenant_id=tenant_id, shop_id=shop_id, api_key=api_key, shop_name=shop_name)
        variations = await self._fetch_variations(shop_id, api_key, search)
        if product_ids:
            wanted = {str(item) for item in product_ids}
            variations = [item for item in variations if str(item.get("product_id") or "") in wanted]

        products, variants = self._transform(variations)
        conn = await asyncpg.connect(self._db_url())
        try:
            async with conn.transaction():
                for product in products.values():
                    product["id"] = await self._upsert_product(conn, tenant_id, product)
                inventory_count = 0
                for variant in variants:
                    product = products[variant["external_product_id"]]
                    variant_id = await self._upsert_variant(conn, tenant_id, product["id"], variant)
                    await self._upsert_inventory(conn, tenant_id, variant_id, variant["remain_quantity"])
                    inventory_count += 1
                await self._mark_shop_sync(conn, tenant_id, shop_id, "synced", None)
        finally:
            await conn.close()

        return PancakeProductSyncStats(
            products=len(products),
            variations=len(variants),
            inventory_items=inventory_count,
        )

    def _encrypt_placeholder(self, value: str) -> str:
        return value

    def _decrypt_placeholder(self, value: str) -> str:
        return value

    async def _mark_shop_sync(
        self,
        conn,
        tenant_id: str,
        shop_id: str,
        status: str,
        error: str | None,
    ) -> None:
        await conn.execute(
            """
            UPDATE pancake_shops
            SET sync_status = $3,
                last_synced_at = CASE WHEN $3 = 'synced' THEN now() ELSE last_synced_at END,
                last_sync_error = $4,
                updated_at = now()
            WHERE tenant_id = $1 AND shop_id = $2
            """,
            self._tenant_uuid(tenant_id),
            shop_id,
            status,
            error,
        )

    async def _fetch_variations(self, shop_id: str, api_key: str, search: str = "") -> list[dict]:
        all_data: list[dict] = []
        page = 1
        base_url = settings.PANCAKE_POS_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                response = await client.get(
                    f"{base_url}/shops/{shop_id}/products/variations",
                    params={
                        "api_key": api_key,
                        "page_size": 1000,
                        "page_number": page,
                        **({"search": search} if search else {}),
                    },
                )
                response.raise_for_status()
                body = response.json()
                if not body.get("success"):
                    raise ValueError("Pancake POS API returned success=false")
                all_data.extend(body.get("data") or [])
                if page >= int(body.get("total_pages") or 1):
                    break
                page += 1
        return all_data

    def _transform(self, variations_data: list[dict]) -> tuple[dict[str, dict], list[dict]]:
        products: dict[str, dict] = {}
        variants: list[dict] = []
        for item in variations_data:
            if item.get("is_removed") or item.get("is_hidden"):
                continue
            product_id = str(item.get("product_id") or "").strip()
            variation_id = str(item.get("id") or "").strip()
            if not product_id or not variation_id:
                continue

            product_info = item.get("product") or {}
            if product_id not in products:
                attrs = product_info.get("product_attributes") or []
                attr_summary = []
                for attr in attrs:
                    name = attr.get("name", "")
                    values = attr.get("values") or []
                    if name and values:
                        attr_summary.append(f"{name}: {', '.join(values)}")
                code = (
                    str(product_info.get("custom_id") or "").strip()
                    or str(product_info.get("display_id") or "").strip()
                    or product_id
                )
                products[product_id] = {
                    "external_product_id": product_id,
                    "code": code,
                    "name": product_info.get("name") or code,
                    "display_id": product_info.get("display_id") or "",
                    "custom_id": product_info.get("custom_id") or "",
                    "category": ", ".join(c.get("name", "") for c in product_info.get("categories", [])),
                    "description": "; ".join(attr_summary),
                }

            field_values = self._field_values(item.get("fields") or [])
            sku_code = (
                str(item.get("custom_id") or "").strip()
                or str(item.get("display_id") or "").strip()
                or products[product_id]["code"]
            )
            variants.append(
                {
                    "external_product_id": product_id,
                    "external_variation_id": variation_id,
                    "sku_code": sku_code,
                    "display_id": item.get("display_id") or "",
                    "custom_id": item.get("custom_id") or "",
                    "color": field_values.get("color") or "",
                    "size": field_values.get("size") or "",
                    "attributes_json": field_values,
                    "price_vnd": int(item.get("retail_price") or 0),
                    "barcode": item.get("barcode") or "",
                    "image_url": (item.get("images") or [""])[0] if item.get("images") else "",
                    "remain_quantity": int(item.get("remain_quantity") or 0),
                }
            )
        return products, variants

    def _field_values(self, fields: list[dict]) -> dict:
        values: dict[str, str] = {}
        for field in fields:
            name = unicodedata.normalize("NFC", str(field.get("name") or "")).lower()
            value = str(field.get("value") or "")
            if name in {"màu", "mau"}:
                values["color"] = value
            elif name == "size":
                values["size"] = value
            elif name:
                values[name] = value
        return values

    async def _upsert_product(self, conn, tenant_id: str, product: dict) -> str:
        return await conn.fetchval(
            """
            INSERT INTO products (
                tenant_id, external_product_id, source, code, name, display_id,
                custom_id, description, category, updated_at
            )
            VALUES ($1, $2, 'pancake', $3, $4, $5, $6, $7, $8, now())
            ON CONFLICT (tenant_id, code) DO UPDATE SET
                external_product_id = EXCLUDED.external_product_id,
                source = EXCLUDED.source,
                name = EXCLUDED.name,
                display_id = EXCLUDED.display_id,
                custom_id = EXCLUDED.custom_id,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                updated_at = now()
            RETURNING id
            """,
            self._tenant_uuid(tenant_id),
            product["external_product_id"],
            product["code"],
            product["name"],
            product["display_id"],
            product["custom_id"],
            product["description"],
            product["category"],
        )

    async def _upsert_variant(self, conn, tenant_id: str, product_id: str, variant: dict) -> str:
        return await conn.fetchval(
            """
            INSERT INTO product_variants (
                tenant_id, product_id, external_variation_id, sku_code, display_id,
                custom_id, color, size, attributes_json, price_vnd, barcode,
                image_url, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, now())
            ON CONFLICT (tenant_id, sku_code, color, size) DO UPDATE SET
                product_id = EXCLUDED.product_id,
                external_variation_id = EXCLUDED.external_variation_id,
                display_id = EXCLUDED.display_id,
                custom_id = EXCLUDED.custom_id,
                attributes_json = EXCLUDED.attributes_json,
                price_vnd = EXCLUDED.price_vnd,
                barcode = EXCLUDED.barcode,
                image_url = EXCLUDED.image_url,
                updated_at = now()
            RETURNING id
            """,
            self._tenant_uuid(tenant_id),
            product_id,
            variant["external_variation_id"],
            variant["sku_code"],
            variant["display_id"],
            variant["custom_id"],
            variant["color"],
            variant["size"],
            json.dumps(variant["attributes_json"], ensure_ascii=False),
            variant["price_vnd"],
            variant["barcode"],
            variant["image_url"],
        )

    async def _upsert_inventory(self, conn, tenant_id: str, variant_id: str, remain_quantity: int) -> None:
        await conn.execute(
            """
            INSERT INTO inventory (
                tenant_id, product_variant_id, on_hand_quantity, reserved_quantity,
                safety_stock_quantity, updated_at
            )
            VALUES ($1, $2, $3, 0, 0, now())
            ON CONFLICT (tenant_id, product_variant_id) DO UPDATE SET
                on_hand_quantity = EXCLUDED.on_hand_quantity,
                updated_at = now()
            """,
            self._tenant_uuid(tenant_id),
            variant_id,
            remain_quantity,
        )


pancake_product_sync_service = PancakeProductSyncService()
