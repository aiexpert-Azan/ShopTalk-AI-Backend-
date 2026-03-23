from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserInDB
from datetime import datetime

router = APIRouter()

PLAN_LIMITS = {
    "free": 200,
    "starter": 1000,
    "growth": 5000,
    "business": 999999
}

PLAN_PRICES = {
    "free": 0,
    "starter": 4000,
    "growth": 10000,
    "business": 20000
}

@router.get("/plan")
async def get_plan(current_user: UserInDB = Depends(get_current_user)):
    # Plan shops collection se lo — admin wahan update karta hai
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    plan = shop.get("plan", "free") if shop else "free"
    messages_used = shop.get("messages_this_month", 0) if shop else 0
    messages_limit = PLAN_LIMITS.get(plan, 200)
    
    # Upgrade options
    all_plans = ["free", "starter", "growth", "business"]
    current_index = all_plans.index(plan) if plan in all_plans else 0
    upgrade_options = all_plans[current_index + 1:]
    
    # Reset date — 1st of next month
    now = datetime.utcnow()
    if now.month == 12:
        reset_date = f"{now.year + 1}-01-01"
    else:
        reset_date = f"{now.year}-{now.month + 1:02d}-01"
    
    return {
        "plan": plan,
        "messages_used": messages_used,
        "messages_limit": messages_limit,
        "price_pkr": PLAN_PRICES.get(plan, 0),
        "reset_date": reset_date,
        "upgrade_options": upgrade_options
    }

@router.post("/upgrade")
async def upgrade_plan(plan_id: str, current_user: UserInDB = Depends(get_current_user)):
    return {"message": f"Upgraded to {plan_id}"}