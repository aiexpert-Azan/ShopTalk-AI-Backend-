from fastapi import APIRouter, Depends, HTTPException, Body
from app.core.database import db
from app.core.deps import get_admin_user
from app.models.user import UserInDB
from bson import ObjectId
from datetime import datetime

router = APIRouter()

# 1. GET /stats - Overall system stats
@router.get("/stats")
async def get_stats(admin: UserInDB = Depends(get_admin_user)):
    total_users = await db.get_db().users.count_documents({})
    total_shops = await db.get_db().shops.count_documents({})
    active_subscriptions = await db.get_db().shops.count_documents({"plan": {"$ne": "free"}})
    shops = await db.get_db().shops.find({}).to_list(1000)
    total_messages_today = sum(shop.get("messages_today", 0) for shop in shops)
    total_messages_this_month = sum(shop.get("messages_this_month", 0) for shop in shops)
    plan_breakdown = {p: await db.get_db().shops.count_documents({"plan": p}) for p in ["free", "starter", "growth", "business"]}
    return {
        "total_users": total_users,
        "total_shops": total_shops,
        "active_subscriptions": active_subscriptions,
        "total_messages_today": total_messages_today,
        "total_messages_this_month": total_messages_this_month,
        "plan_breakdown": plan_breakdown
    }

# 2. GET /users - Get all users with their shop info
@router.get("/users")
async def get_all_users(admin: UserInDB = Depends(get_admin_user)):
    users = await db.get_db().users.find({}).to_list(1000)
    shops = await db.get_db().shops.find({}).to_list(1000)
    shop_map = {str(shop.get("userId")): shop for shop in shops}
    result = []
    for user in users:
        shop = shop_map.get(str(user.get("_id")))
        result.append({
            "user_id": str(user.get("_id")),
            "name": user.get("name"),
            "phone": user.get("phone"),
            "email": user.get("email"),
            "created_at": user.get("created_at"),
            "shop_name": shop.get("name") if shop else None,
            "plan": shop.get("plan") if shop else None,
            "messages_this_month": shop.get("messages_this_month") if shop else None,
            "whatsapp_connected": shop.get("whatsapp_connected") if shop else None,
            "is_active": user.get("is_active", True)
        })
    return result

# 3. GET /users/{user_id} - Get single user detail
@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin: UserInDB = Depends(get_admin_user)):
    user = await db.get_db().users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    shop = await db.get_db().shops.find_one({"userId": user_id})
    conversations_count = await db.get_db().conversations.count_documents({"shopId": str(shop["_id"])}) if shop else 0
    return {
        "user": user,
        "shop": shop,
        "recent_conversations_count": conversations_count
    }

# 4. PUT /users/{user_id}/plan - Update user plan
@router.put("/users/{user_id}/plan")
async def update_user_plan(user_id: str, body: dict = Body(...), admin: UserInDB = Depends(get_admin_user)):
    plan = body.get("plan")
    if plan not in ["free", "starter", "growth", "business"]:
        raise HTTPException(status_code=400, detail="Invalid plan")
    shop = await db.get_db().shops.find_one({"userId": user_id})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    await db.get_db().shops.update_one({"userId": user_id}, {"$set": {"plan": plan}})
    updated_shop = await db.get_db().shops.find_one({"userId": user_id})
    return updated_shop

# 5. PUT /users/{user_id}/status - Block/unblock user
@router.put("/users/{user_id}/status")
async def update_user_status(user_id: str, body: dict = Body(...), admin: UserInDB = Depends(get_admin_user)):
    is_active = body.get("is_active")
    if is_active not in [True, False]:
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.get_db().users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": is_active}})
    user = await db.get_db().users.find_one({"_id": ObjectId(user_id)})
    return user

# 6. GET /shops - Get all shops with WhatsApp status
@router.get("/shops")
async def get_all_shops(admin: UserInDB = Depends(get_admin_user)):
    shops = await db.get_db().shops.find({}).to_list(1000)
    result = []
    for shop in shops:
        result.append({
            "shop_id": str(shop.get("_id")),
            "name": shop.get("name"),
            "owner_phone": shop.get("ownerPhone", shop.get("owner_phone")),
            "plan": shop.get("plan"),
            "messages_this_month": shop.get("messages_this_month"),
            "whatsapp_connected": shop.get("whatsapp_connected"),
            "whatsapp_phone_number_id": shop.get("whatsapp_phone_number_id"),
            "created_at": shop.get("created_at")
        })
    return result

# 7. GET /conversations - Recent conversations across all shops
@router.get("/conversations")
async def get_recent_conversations(admin: UserInDB = Depends(get_admin_user)):
    conversations = await db.get_db().conversations.find({}).sort("updatedAt", -1).limit(50).to_list(50)
    shop_map = {str(shop["_id"]): shop.get("name") for shop in await db.get_db().shops.find({}).to_list(1000)}
    result = []
    for conv in conversations:
        result.append({
            "customer_phone": conv.get("customerPhone"),
            "shop_name": shop_map.get(conv.get("shopId")),
            "last_message": conv.get("messages", [{}])[-1].get("content") if conv.get("messages") else None,
            "updated_at": conv.get("updatedAt"),
            "message_count": len(conv.get("messages", []))
        })
    return result

# 8. DELETE /users/{user_id} - Delete user and their shop data
@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: UserInDB = Depends(get_admin_user)):
    await db.get_db().users.delete_one({"_id": ObjectId(user_id)})
    await db.get_db().shops.delete_many({"userId": user_id})
    await db.get_db().conversations.delete_many({"shopId": user_id})
    await db.get_db().knowledge_base.delete_many({"shopId": user_id})
    return {"deleted": True, "user_id": user_id}
