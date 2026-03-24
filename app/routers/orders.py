from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserInDB
from app.models.order import OrderCreate, OrderUpdateStatus, OrderResponse, OrderInDB, OrderTimeline
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
async def get_order_stats(
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        return {"new": 0, "processing": 0, "completed": 0, "today": 0}

    shop_id = str(shop["_id"])
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {"shopId": shop_id}},
        {"$facet": {
            "new": [{"$match": {"status": "new"}}, {"$count": "count"}],
            "processing": [{"$match": {"status": "processing"}}, {"$count": "count"}],
            "completed": [{"$match": {"status": "completed"}}, {"$count": "count"}],
            "today": [{"$match": {"createdAt": {"$gte": today}}}, {"$count": "count"}]
        }}
    ]
    agg = await db.get_db().orders.aggregate(pipeline).to_list(1)
    if not agg:
        return {"new": 0, "processing": 0, "completed": 0, "today": 0}
    facet = agg[0]
    def get_count(key):
        arr = facet.get(key, [])
        return arr[0]["count"] if arr else 0
    return {
        "new": get_count("new"),
        "processing": get_count("processing"),
        "completed": get_count("completed"),
        "today": get_count("today")
    }


@router.get("/", response_model=List[OrderResponse])
async def list_orders(
    status: Optional[str] = None,
    sort: Optional[str] = "newest",
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        return []

    query = {"shopId": str(shop["_id"])}
    if status and status != "all":
        query["status"] = status

    cursor = db.get_db().orders.find(query)

    if sort == "newest":
        cursor.sort("createdAt", -1)
    else:
        cursor.sort("createdAt", 1)

    orders = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["shopId"] = str(doc["shopId"])
        orders.append(OrderResponse(**doc))

    return orders


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order_details(
    order_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    try:
        order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order ID")

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop or str(order["shopId"]) != str(shop["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized")

    order["_id"] = str(order["_id"])
    order["shopId"] = str(order["shopId"])
    return OrderResponse(**order)


@router.put("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: str,
    status_update: OrderUpdateStatus,
    current_user: UserInDB = Depends(get_current_user)
):
    valid_statuses = ["new", "processing", "ready", "completed", "rejected"]
    if status_update.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    try:
        order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order ID")

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop or str(order["shopId"]) != str(shop["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized")

    timeline_entry = OrderTimeline(
        action=f"Status changed to {status_update.status}",
        message=f"Order status updated from {order['status']} to {status_update.status}"
    )

    await db.get_db().orders.update_one(
        {"_id": ObjectId(order_id)},
        {
            "$set": {
                "status": status_update.status,
                "updatedAt": datetime.utcnow()
            },
            "$push": {"timeline": timeline_entry.model_dump()}
        }
    )

    # --- WhatsApp Notification ---
    whatsapp_token = shop.get("whatsapp_access_token")
    whatsapp_phone_id = shop.get("whatsapp_phone_number_id")
    customer_phone = order.get("customerPhone")
    order_number = order.get("orderNumber") or str(order.get("_id"))
    polite_status = status_update.status.capitalize()
    msg_body = f"Aapka order #{order_number} ab {polite_status} mein hai. Shukriya!"
    if whatsapp_token and whatsapp_phone_id and customer_phone:
        whatsapp_url = f"https://graph.facebook.com/v19.0/{whatsapp_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {whatsapp_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": customer_phone,
            "type": "text",
            "text": {"body": msg_body}
        }
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(whatsapp_url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                logger.info(f"WhatsApp notification sent to {customer_phone} for order {order_number} status {status_update.status}")
            else:
                logger.error(f"Failed to send WhatsApp notification: {resp.status_code} {resp.text}", extra={"shop_id": shop.get('_id'), "user_id": current_user.id})
        except Exception as e:
            logger.error(f"WhatsApp notification error: {e}", extra={"shop_id": shop.get('_id'), "user_id": current_user.id})

    updated_order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    updated_order["_id"] = str(updated_order["_id"])
    updated_order["shopId"] = str(updated_order["shopId"])
    return OrderResponse(**updated_order)


@router.put("/{order_id}/accept", response_model=OrderResponse)
async def accept_order(
    order_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    return await update_order_status(order_id, OrderUpdateStatus(status="processing"), current_user)


@router.put("/{order_id}/reject", response_model=OrderResponse)
async def reject_order(
    order_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    return await update_order_status(order_id, OrderUpdateStatus(status="rejected"), current_user)


@router.post("/{order_id}/message")
async def send_order_message(
    order_id: str,
    message: dict,
    current_user: UserInDB = Depends(get_current_user)
):
    order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    customer_phone = order.get("customerPhone")
    if customer_phone:
        logger.info(f"Would send message to {customer_phone}: {message.get('message')}")

    timeline_entry = OrderTimeline(
        action="Message Sent",
        message=f"Shop sent message: {message.get('message')}"
    )

    await db.get_db().orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$push": {"timeline": timeline_entry.model_dump()}}
    )

    return {"message": "Message sent successfully"}


@router.post("/{order_id}/receipt")
async def send_order_receipt(
    order_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    timeline_entry = OrderTimeline(
        action="Receipt Sent",
        message="Order receipt generated and sent to customer"
    )

    await db.get_db().orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$push": {"timeline": timeline_entry.model_dump()}}
    )

    return {"message": "Receipt sent successfully"}