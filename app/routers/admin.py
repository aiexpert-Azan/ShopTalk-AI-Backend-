
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import random
import os
from bson import ObjectId
from pydantic import BaseModel
from app.core.security import verify_password, create_access_token, create_refresh_token
from app.core.database import db
from app.middleware.adminAuth import isAdmin


router = APIRouter()

# --- ADMIN LOGIN ENDPOINT ---
class AdminLoginRequest(BaseModel):
    phone: str
    password: str

@router.post("/login")
async def admin_login(request: AdminLoginRequest):
    user = await db.get_db().users.find_one({"phone": request.phone})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    if not user.get("hashed_password"):
        raise HTTPException(status_code=401, detail="This account has no password set. Please set a password in database.")
    if not verify_password(request.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    role = user.get("role")
    admin_phone = os.getenv("ADMIN_PHONE_NUMBER", "")
    is_admin = (role == "admin") or (admin_phone and request.phone == admin_phone)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    access_token = create_access_token(data={
        "sub": user["phone"],
        "role": "admin",
        "phone": user["phone"]
    })
    refresh_token = create_refresh_token(data={"sub": user["phone"]})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "phone": user["phone"],
            "name": user.get("name"),
            "role": "admin"
        }
    }

# ==========================================
# NEW ROUTES FOR v0 ADMIN DASHBOARD
# ==========================================

# 1. GET /analytics
@router.get("/analytics")
async def admin_analytics(admin = Depends(isAdmin)):
    try:
        # Mock revenue calculation
        plans = ["free", "starter", "growth", "business"]
        plan_prices = {"free": 0, "starter": 49, "growth": 99, "business": 199}
        shops = await db.get_db().shops.find({}).to_list(1000)
        revenue_by_plan = {p: 0 for p in plans}
        for shop in shops:
            plan = shop.get("plan", "free")
            revenue_by_plan[plan] += plan_prices.get(plan, 0)
        total_revenue = sum(revenue_by_plan.values())

        # Messages processed over last 7 days
        today = datetime.utcnow()
        messages_time_series = []
        for i in range(7):
            day = today.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            count = await db.get_db().conversations.count_documents({"updatedAt": {"$gte": day, "$lt": day + timedelta(days=1)}})
            messages_time_series.append({"date": day.strftime("%Y-%m-%d"), "count": count})
        messages_time_series.reverse()

        # Revenue by plan breakdown
        plan_breakdown = {p: await db.get_db().shops.count_documents({"plan": p}) for p in plans}

        return JSONResponse({
            "total_revenue": total_revenue,
            "messages_time_series": messages_time_series,
            "revenue_by_plan": revenue_by_plan,
            "plan_breakdown": plan_breakdown
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# 2. GET /infrastructure
@router.get("/infrastructure")
async def admin_infrastructure(admin = Depends(isAdmin)):
    try:
        # Mock CPU/RAM usage
        cpu_usage = round(random.uniform(10, 60), 2)
        ram_usage = round(random.uniform(20, 80), 2)

        # External service status (mocked)
        services = {
            "MongoDB": "Operational",
            "MetaWhatsAppAPI": "Operational",
            "OpenAIAPI": "Operational"
        }

        # Mock logs
        logs = [
            {"timestamp": datetime.utcnow().isoformat(), "level": "INFO", "message": "System started."},
            {"timestamp": datetime.utcnow().isoformat(), "level": "ERROR", "message": "Mock error event."}
        ]

        return JSONResponse({
            "cpu_usage": cpu_usage,
            "ram_usage": ram_usage,
            "services": services,
            "logs": logs
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# 3. GET /subscriptions
@router.get("/subscriptions")
async def admin_subscriptions(admin = Depends(isAdmin)):
    try:
        plan_prices = {"free": 0, "starter": 49, "growth": 99, "business": 199}
        shops = await db.get_db().shops.find({}).to_list(1000)
        result = []
        for shop in shops:
            plan = shop.get("plan", "free")
            mrr = plan_prices.get(plan, 0)
            status = "active" if shop.get("is_active", True) else "inactive"
            result.append({
                "shop_id": str(shop.get("_id")),
                "shop_name": shop.get("name"),
                "owner_phone": shop.get("ownerPhone", shop.get("owner_phone")),
                "current_plan": plan,
                "status": status,
                "mrr": mrr
            })
        return JSONResponse({"subscriptions": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# 4. GET & PUT /settings
@router.get("/settings")
async def admin_settings(admin = Depends(isAdmin)):
    try:
        settings_doc = await db.get_db().global_settings.find_one({}) if hasattr(db.get_db(), "global_settings") else None
        if settings_doc:
            settings_doc.pop("_id", None)
            return JSONResponse(settings_doc)
        
        # Mocked settings
        return JSONResponse({
            "openai_model_version": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini"),
            "system_maintenance_mode": False
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.put("/settings")
async def update_admin_settings(body: dict = Body(...), admin = Depends(isAdmin)):
    try:
        if hasattr(db.get_db(), "global_settings"):
            await db.get_db().global_settings.update_one({}, {"$set": body}, upsert=True)
            return JSONResponse({"success": True, "updated": body})
        return JSONResponse({"success": True, "updated": body, "mocked": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ==========================================
# EXISTING CORE ADMIN ROUTES
# ==========================================

# 5. GET /stats - Overall system stats
@router.get("/stats")
async def get_stats(admin = Depends(isAdmin)):
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

# 6. GET /users - Get all users with their shop info
@router.get("/users")
async def get_all_users(admin = Depends(isAdmin)):
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

# 7. GET /users/{user_id} - Get single user detail
@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin = Depends(isAdmin)):
    user = await db.get_db().users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # ObjectId ko string me convert karna taake JSON easily parse ho jaye
    user["_id"] = str(user["_id"])
    
    shop = await db.get_db().shops.find_one({"userId": user_id})
    conversations_count = 0
    if shop:
        shop["_id"] = str(shop["_id"])
        conversations_count = await db.get_db().conversations.count_documents({"shopId": shop["_id"]})
        
    return {
        "user": user,
        "shop": shop,
        "recent_conversations_count": conversations_count
    }

# 8. PUT /users/{user_id}/plan - Update user plan
@router.put("/users/{user_id}/plan")
async def update_user_plan(user_id: str, body: dict = Body(...), admin = Depends(isAdmin)):
    plan = body.get("plan")
    if plan not in ["free", "starter", "growth", "business"]:
        raise HTTPException(status_code=400, detail="Invalid plan")
    shop = await db.get_db().shops.find_one({"userId": user_id})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    await db.get_db().shops.update_one({"userId": user_id}, {"$set": {"plan": plan}})
    updated_shop = await db.get_db().shops.find_one({"userId": user_id})
    updated_shop["_id"] = str(updated_shop["_id"])
    return updated_shop

# 9. PUT /users/{user_id}/status - Block/unblock user
@router.put("/users/{user_id}/status")
async def update_user_status(user_id: str, body: dict = Body(...), admin = Depends(isAdmin)):
    is_active = body.get("is_active")
    if is_active not in [True, False]:
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.get_db().users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": is_active}})
    user = await db.get_db().users.find_one({"_id": ObjectId(user_id)})
    user["_id"] = str(user["_id"])
    return user

# 10. GET /shops - Get all shops with WhatsApp status
@router.get("/shops")
async def get_all_shops(admin = Depends(isAdmin)):
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

# 11. GET /conversations - Recent conversations across all shops
@router.get("/conversations")
async def get_recent_conversations(admin = Depends(isAdmin)):
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

# 12. DELETE /users/{user_id} - Delete user and their shop data
@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin = Depends(isAdmin)):
    await db.get_db().users.delete_one({"_id": ObjectId(user_id)})
    await db.get_db().shops.delete_many({"userId": user_id})
    await db.get_db().conversations.delete_many({"shopId": user_id})
    await db.get_db().knowledge_base.delete_many({"shopId": user_id})
    return {"deleted": True, "user_id": user_id}

