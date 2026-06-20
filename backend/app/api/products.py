from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.pancake.product_sync import DEMO_TENANT_ID, pancake_product_sync_service

router = APIRouter(prefix="/api/products", tags=["products"])


class PancakeProductSyncRequest(BaseModel):
    tenant_id: str = DEMO_TENANT_ID
    pancake_shop_id: str | None = None
    shop_id: str | None = None
    api_key: str | None = None
    shop_name: str | None = None
    search: str = ""
    product_ids: list[str] | None = None


class PancakeShopConnectRequest(BaseModel):
    tenant_id: str = DEMO_TENANT_ID
    shop_id: str
    api_key: str
    shop_name: str | None = None


@router.get("")
async def list_products(tenant_id: str = DEMO_TENANT_ID) -> dict:
    return {"items": await pancake_product_sync_service.list_catalog(tenant_id)}


@router.get("/pancake/shops")
async def list_pancake_shops(tenant_id: str = DEMO_TENANT_ID) -> dict:
    return {"items": await pancake_product_sync_service.list_shops(tenant_id)}


@router.post("/pancake/shops")
async def connect_pancake_shop(payload: PancakeShopConnectRequest) -> dict:
    shop = await pancake_product_sync_service.save_shop(
        tenant_id=payload.tenant_id,
        shop_id=payload.shop_id,
        api_key=payload.api_key,
        shop_name=payload.shop_name,
    )
    return {"shop": shop}


@router.post("/pancake/preview")
async def preview_pancake_products(payload: PancakeProductSyncRequest) -> dict:
    shop_id = payload.shop_id
    api_key = payload.api_key
    if payload.pancake_shop_id:
        shop_id, api_key = await pancake_product_sync_service.get_shop_credentials(
            payload.tenant_id,
            payload.pancake_shop_id,
        )
    if not shop_id or not api_key:
        raise HTTPException(status_code=400, detail="pancake_shop_id or request shop_id/api_key is required")
    try:
        items = await pancake_product_sync_service.preview_products(shop_id, api_key, payload.search)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pancake POS preview failed: {exc}") from exc
    return {"items": items, "count": len(items)}


@router.post("/pancake/sync")
async def sync_pancake_products(payload: PancakeProductSyncRequest) -> dict:
    shop_id = payload.shop_id
    api_key = payload.api_key
    if payload.pancake_shop_id:
        shop_id, api_key = await pancake_product_sync_service.get_shop_credentials(
            payload.tenant_id,
            payload.pancake_shop_id,
        )
    if not shop_id or not api_key:
        raise HTTPException(status_code=400, detail="pancake_shop_id or request shop_id/api_key is required")
    try:
        stats = await pancake_product_sync_service.sync(
            tenant_id=payload.tenant_id,
            shop_id=shop_id,
            api_key=api_key,
            search=payload.search,
            product_ids=payload.product_ids,
            shop_name=payload.shop_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pancake POS sync failed: {exc}") from exc
    return {
        "status": "ok",
        "products": stats.products,
        "variations": stats.variations,
        "inventory_items": stats.inventory_items,
    }
