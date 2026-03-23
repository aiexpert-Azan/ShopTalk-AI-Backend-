# --- Delete Single Upgrade Request (Admin) ---
@router.delete("/upgrade-requests/{request_id}")
async def delete_upgrade_request(
    request_id: str,
    admin = Depends(isAdmin)
):
    from bson import ObjectId
    result = await db.get_db().upgrade_requests.delete_one({"_id": ObjectId(request_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"deleted": True, "request_id": request_id}

# --- Bulk Delete Approved/Rejected Upgrade Requests (Admin) ---
@router.delete("/upgrade-requests")
async def clear_completed_upgrade_requests(
    admin = Depends(isAdmin)
):
    result = await db.get_db().upgrade_requests.delete_many({
        "status": {"$in": ["approved", "rejected"]}
    })
    return {"deleted_count": result.deleted_count, "message": f"Cleared {result.deleted_count} completed requests"}
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import random
import os
from bson import ObjectId
from pydantic import BaseModel
from typing import Optional
from app.core.security import verify_password, create_access_token, create_refresh_token
from app.core.database import db
from app.middleware.adminAuth import isAdmin
from app.core.deps import get_current_user
from app.models.user import UserInDB

router = APIRouter()

# --- Plan Upgrade Request Model ---
class PlanUpgradeRequest(BaseModel):
    requested_plan: str
    reason: Optional[str] = None

# --- Admin Login Model ---
class AdminLoginRequest(BaseModel):
    phone: str
    password: str

# --- ADMIN LOGIN ENDPOINT ---
@router.post("/login")
async def admin_login(request: AdminLoginRequest):
    user = await db.get_db().users.find_one({"phone": request.phone})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    if not user.get("hashed_password"):
        raise HTTPException(status_code=401, detail="This account has no password set.")
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

# --- Request Plan Upgrade Endpoint ---
@router.post("/upgrade-request")
async def request_plan_upgrade(
    request: PlanUpgradeRequest,
    current_user: UserInDB = Depends(get_current_user)
):
    if request.requested_plan not in ["starter", "growth", "business"]:
        raise HTTPException(status_code=400, detail="Invalid plan")
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    upgrade_request = {
        "userId": str(current_user.id),
        "shopId": str(shop["_id"]),
        "shop_name": shop.get("name"),
        "phone": current_user.phone,
        "current_plan": shop.get("plan", "free"),
        "requested_plan": request.requested_plan,
        "reason": request.reason,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    await db.get_db().upgrade_requests.insert_one(upgrade_request)
    return {"message": "Upgrade request submitted. Admin will review and activate your plan shortly."}

# --- Get All Upgrade Requests (Admin) ---
@router.get("/upgrade-requests")
async def get_upgrade_requests(admin = Depends(isAdmin)):
    requests = await db.get_db().upgrade_requests.find({}).sort("created_at", -1).to_list(100)
    result = []
    for req in requests:
        req["_id"] = str(req["_id"])
        result.append(req)
    return result

# --- Approve Upgrade Request (Admin) ---
@router.post("/upgrade-requests/{request_id}/approve")
async def approve_upgrade_request(
    request_id: str,
    admin = Depends(isAdmin)
):
    upgrade_req = await db.get_db().upgrade_requests.find_one({"_id": ObjectId(request_id)})
    if not upgrade_req:
        raise HTTPException(status_code=404, detail="Request not found")
    await db.get_db().shops.update_one(
        {"_id": ObjectId(upgrade_req["shopId"])},
        {"$set": {"plan": upgrade_req["requested_plan"]}}
    )
    await db.get_db().upgrade_requests.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": "approved", "approved_at": datetime.utcnow()}}
    )
    return {"message": f"Plan upgraded to {upgrade_req['requested_plan']} successfully"}

# --- Reject Upgrade Request (Admin) ---
@router.post("/upgrade-requests/{request_id}/reject")
async def reject_upgrade_request(
    request_id: str,
    admin = Depends(isAdmin)
):
    await db.get_db().upgrade_requests.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {"status": "rejected", "rejected_at": datetime.utcnow()}}
    )
    return {"message": "Request rejected"}

# --- Analytics ---
@router.get("/analytics")
async def admin_analytics(admin = Depends(isAdmin)):
    try:
        plans = ["free", "starter", "growth", "business"]
        plan_prices = {"free": 0, "starter": 49, "growth": 99, "business": 199}
        shops = await db.get_db().shops.find({}).to_list(1000)
        revenue_by_plan = {p: 0 for p in plans}
        for shop in shops:
            plan = shop.get("plan", "free")
            revenue_by_plan[plan] += plan_prices.get(plan, 0)
        total_revenue = sum(revenue_by_plan.values())
        today = datetime.utcnow()
        messages_time_series = []
        for i in range(7):
            day = today.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            count = await db.get_db().conversations.count_documents({"updatedAt": {"$gte": day, "$lt": day + timedelta(days=1)}})
            messages_time_series.append({"date": day.strftime("%Y-%m-%d"), "count": count})
        messages_time_series.reverse()
        plan_breakdown = {p: await db.get_db().shops.count_documents({"plan": p}) for p in plans}
        return JSONResponse({
            "total_revenue": total_revenue,
            "messages_time_series": messages_time_series,
            "revenue_by_plan": revenue_by_plan,
            "plan_breakdown": plan_breakdown
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# --- Infrastructure ---
@router.get("/infrastructure")
async def admin_infrastructure(admin = Depends(isAdmin)):
    try:
        cpu_usage = round(random.uniform(10, 60), 2)
        ram_usage = round(random.uniform(20, 80), 2)
        services = {
            "MongoDB": "Operational",
            "MetaWhatsAppAPI": "Operational",
            "OpenAIAPI": "Operational"
        }
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

# --- Subscriptions ---
@router.get("/subscriptions")
async def admin_subscriptions(admin = Depends(isAdmin)):
    try:
        plan_prices = {"free": 0, "starter": 4000, "growth": 10000, "business": 20000}
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

# --- Settings ---
@router.get("/settings")
async def admin_settings(admin = Depends(isAdmin)):
    try:
        return JSONResponse({
            "openai_model_version": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini"),
            "system_maintenance_mode": False
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.put("/settings")
async def update_admin_settings(body: dict = Body(...), admin = Depends(isAdmin)):
    try:
        return JSONResponse({"success": True, "updated": body})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# --- Stats ---
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

# --- Users ---
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

@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin = Depends(isAdmin)):
    user = await db.get_db().users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
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

@router.put("/users/{user_id}/status")
async def update_user_status(user_id: str, body: dict = Body(...), admin = Depends(isAdmin)):
    is_active = body.get("is_active")
    if is_active not in [True, False]:
        raise HTTPException(status_code=400, detail="Invalid status")
    await db.get_db().users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": is_active}})
    user = await db.get_db().users.find_one({"_id": ObjectId(user_id)})
    user["_id"] = str(user["_id"])
    return user

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

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin = Depends(isAdmin)):
    await db.get_db().users.delete_one({"_id": ObjectId(user_id)})
    await db.get_db().shops.delete_many({"userId": user_id})
    await db.get_db().conversations.delete_many({"shopId": user_id})
    await db.get_db().knowledge_base.delete_many({"shopId": user_id})
    return {"deleted": True, "user_id": user_id}