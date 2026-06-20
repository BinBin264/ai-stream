from fastapi import APIRouter, HTTPException

from app.models.domain import OrderStatus, PaymentStatus, ReservationStatus
from app.services.store import store

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("")
async def list_orders() -> dict:
    return {"items": sorted(store.orders.values(), key=lambda item: item.created_at, reverse=True)}


@router.get("/{order_id}")
async def get_order(order_id: str) -> dict:
    order = store.orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    cart = store.carts.get(order.cart_id)
    return {"order": order, "cart": cart}


@router.post("/{order_id}/approve")
async def approve_order(order_id: str) -> dict:
    order = store.orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = OrderStatus.COD_CONFIRMED
    order.payment_status = PaymentStatus.PENDING
    for reservation in store.reservations.values():
        if reservation.order_id == order.id and reservation.status == ReservationStatus.ACTIVE:
            reservation.status = ReservationStatus.CONSUMED
    return {"order": order}


@router.post("/{order_id}/cancel")
async def cancel_order(order_id: str) -> dict:
    order = store.orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = OrderStatus.CANCELLED
    for reservation in store.reservations.values():
        if reservation.order_id != order.id or reservation.status != ReservationStatus.ACTIVE:
            continue
        inventory = store.inventory[reservation.product_variant_id]
        inventory.reserved_quantity = max(0, inventory.reserved_quantity - reservation.quantity)
        reservation.status = ReservationStatus.CANCELLED
    return {"order": order}


@router.post("/{order_id}/create-checkout")
async def create_checkout(order_id: str) -> dict:
    order = store.orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = OrderStatus.WAITING_PAYMENT
    return {"order": order, "checkout": {"status": "not_configured"}}
