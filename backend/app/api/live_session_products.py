from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.director.live_director import live_director
from app.services.director.product_queue import product_queue_service
from app.services.media.publisher import DEMO_TENANT_ID

router = APIRouter(prefix="/api/live-sessions", tags=["live-session-products"])


class AddLiveProductRequest(BaseModel):
    tenant_id: str = DEMO_TENANT_ID
    product_id: str
    product_variant_id: str | None = None
    display_order: int | None = None
    is_featured: bool = False


class ReorderLiveProductsRequest(BaseModel):
    tenant_id: str = DEMO_TENANT_ID
    items: list[dict]


@router.post("/{live_id}/products")
async def add_live_product(live_id: str, payload: AddLiveProductRequest) -> dict:
    try:
        item = await product_queue_service.add_product(
            tenant_id=payload.tenant_id,
            live_id=live_id,
            product_id=payload.product_id,
            product_variant_id=payload.product_variant_id,
            display_order=payload.display_order,
            is_featured=payload.is_featured,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.get("/{live_id}/products")
async def list_live_products(live_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
    return {"items": await product_queue_service.list_products(live_id=live_id, tenant_id=tenant_id)}


@router.patch("/{live_id}/products/reorder")
async def reorder_live_products(live_id: str, payload: ReorderLiveProductsRequest) -> dict:
    try:
        items = await product_queue_service.reorder(live_id=live_id, tenant_id=payload.tenant_id, items=payload.items)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items}


@router.delete("/{live_id}/products/{item_id}")
async def delete_live_product(live_id: str, item_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
    await product_queue_service.delete_product(live_id=live_id, tenant_id=tenant_id, item_id=item_id)
    return {"deleted": True}


@router.post("/{live_id}/prepare")
async def prepare_live(live_id: str, tenant_id: str = DEMO_TENANT_ID) -> dict:
    try:
        return await live_director.prepare_live(live_id=live_id, tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
