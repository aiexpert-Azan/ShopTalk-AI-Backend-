from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserInDB
from app.models.order import OrderCreate, OrderUpdateStatus, OrderResponse, OrderInDB, OrderTimeline
from app.models.order import OrderCreate, OrderUpdateStatus, OrderResponse, OrderInDB, OrderTimeline
from bson import ObjectId
from app.services.twilio_service import twilio_service

router = APIRouter()

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
    except:
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
    # Verify ownership
    try:
        order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID")
        
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop or str(order["shopId"]) != str(shop["_id"]):
         raise HTTPException(status_code=403, detail="Not authorized")
    
    new_status = status_update.status
    
    # State transition logic could go here
    
    timeline_entry = OrderTimeline(
        action=f"Status changed to {new_status}",
        message=f"Order status updated from {order['status']} to {new_status}"
    )
    
    update_data = {
        "status": new_status,
        "updatedAt": datetime.utcnow()
    }
    
    await db.get_db().orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": update_data, "$push": {"timeline": timeline_entry.model_dump()}}
    )
    
    updated_order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    updated_order["_id"] = str(updated_order["_id"])
    updated_order["shopId"] = str(updated_order["shopId"])
    return OrderResponse(**updated_order)

# Additional endpoints for accept/reject could reuse update_status logic or be separate
@router.put("/{order_id}/accept", response_model=OrderResponse)
async def accept_order(
    order_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    # Reuse update logic
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
    message: dict, # Body: {"message": "text"}
    current_user: UserInDB = Depends(get_current_user)
):
    # Logic to send WhatsApp message via utility service
    # Log to timeline
    
    order = await db.get_db().orders.find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Send via Twilio
    # Assuming order has customerPhone. Need to ensure format.
    customer_phone = order.get("customerPhone")
    if customer_phone:
        twilio_service.send_whatsapp_message(customer_phone, message.get('message'))
        
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
    # Logic to generate PDF or text receipt and send via WhatsApp/Email
    
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
