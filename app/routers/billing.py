from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import UserInDB

router = APIRouter()

@router.get("/plan")
async def get_plan(current_user: UserInDB = Depends(get_current_user)):
    return {
        "plan": current_user.plan,
        "messages_used": 150,
        "reset_date": "2024-03-01",
        "upgrade_options": ["growth", "business"]
    }

@router.post("/upgrade")
async def upgrade_plan(plan_id: str, current_user: UserInDB = Depends(get_current_user)):
    return {"message": f"Upgraded to {plan_id}"}
