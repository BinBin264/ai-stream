from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.store import store

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class InventoryAdjustmentRequest(BaseModel):
    product_variant_id: str
    quantity_delta: int
    reason: str = "manual_adjustment"


@router.get("")
async def list_inventory() -> dict:
    return {
        "items": [
            {
                **item.model_dump(),
                "available_quantity": item.available_quantity,
                "variant": store.variants.get(item.product_variant_id),
            }
            for item in store.list_inventory()
        ]
    }


@router.post("/adjustments")
async def adjust_inventory(payload: InventoryAdjustmentRequest) -> dict:
    if payload.product_variant_id not in store.inventory:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    item = store.adjust_inventory(payload.product_variant_id, payload.quantity_delta)
    return {"inventory": item, "available_quantity": item.available_quantity}


@router.post("/reservations/release-expired")
async def release_expired_reservations() -> dict:
    return {"released": store.release_expired_reservations()}
