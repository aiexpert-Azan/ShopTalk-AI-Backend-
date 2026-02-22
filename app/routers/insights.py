from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserInDB
from app.models.insight import InsightResponse, InsightInDB
from app.services.ai_service import ai_service

router = APIRouter()

@router.get("/weekly", response_model=InsightResponse)
async def get_weekly_insights(
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
        
    # Check if we have cached insights for this week
    # For now, generate dummy or fetch latest
    
    # Mock data for demonstration
    mock_insight = InsightInDB(
        shopId=str(shop["_id"]),
        weekStartDate=datetime.utcnow() - timedelta(days=7),
        topQuestions=[
            {"question": "What is the price of...", "count": 15},
            {"question": "Do you deliver to...", "count": 8}
        ],
        busiestHours=[
            {"label": "10:00 AM", "messages": 45},
            {"label": "2:00 PM", "messages": 60}
        ],
        popularProducts=[
            {"name": "Awesome Shirt", "inquiries": 20, "demand": "High"}
        ],
        automatedSales=[
            {"customerName": "Ali Khan", "interaction": "Bought via chat", "value": 1500.0}
        ],
        aiInsight="Sales are up 20% this week. Consider stocking more shirts."
    )
    
    # In production, we would query orders/conversations and aggregate stats here,
    # then call ai_service.generate_insight(stats)
    
    mock_insight.id = "mock_id"
    return mock_insight

@router.post("/export/report")
async def export_report(
    current_user: UserInDB = Depends(get_current_user)
):
    # Logic to generate PDF/CSV
    return {"url": "https://example.com/report.pdf"}
