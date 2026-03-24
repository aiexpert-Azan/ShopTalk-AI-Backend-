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
    shop_id = str(shop["_id"])
    week_start = datetime.utcnow() - timedelta(days=7)
    # Total Sales
    orders = await db.get_db().orders.find({
        "shopId": shop_id,
        "createdAt": {"$gte": week_start}
    }).to_list(1000)
    total_sales = sum(o.get("total", 0) for o in orders)
    # Top Questions (from conversations)
    conversations = await db.get_db().conversations.find({
        "shopId": shop_id,
        "createdAt": {"$gte": week_start}
    }).to_list(1000)
    question_freq = {}
    for conv in conversations:
        for msg in conv.get("messages", []):
            if msg.get("role") == "user":
                q = msg.get("content") or msg.get("text") or ""
                if q:
                    question_freq[q] = question_freq.get(q, 0) + 1
    top_questions = sorted(
        [{"question": k, "count": v} for k, v in question_freq.items()],
        key=lambda x: x["count"], reverse=True
    )[:5]
    # Busiest Hours
    hour_buckets = {}
    for conv in conversations:
        for msg in conv.get("messages", []):
            ts = msg.get("timestamp") or msg.get("createdAt")
            if ts:
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except Exception:
                        continue
                hour = ts.replace(minute=0, second=0, microsecond=0).strftime("%H:00")
                hour_buckets[hour] = hour_buckets.get(hour, 0) + 1
    busiest_hours = sorted(
        [{"label": h, "messages": c} for h, c in hour_buckets.items()],
        key=lambda x: x["messages"], reverse=True
    )[:5]
    # Popular Products (from orders)
    product_freq = {}
    for o in orders:
        for item in o.get("items", []):
            name = item.get("name")
            if name:
                product_freq[name] = product_freq.get(name, 0) + 1
    popular_products = sorted(
        [{"name": k, "inquiries": v, "demand": "High" if v > 5 else "Medium"} for k, v in product_freq.items()],
        key=lambda x: x["inquiries"], reverse=True
    )[:5]
    # Automated Sales (from orders)
    automated_sales = [
        {
            "customerName": o.get("customerName"),
            "interaction": o.get("status"),
            "value": o.get("total", 0)
        }
        for o in orders if o.get("status") == "completed"
    ]
    # AI Insight
    stats_summary = f"Total sales: {total_sales}. Top questions: {[q['question'] for q in top_questions]}. Busiest hours: {[h['label'] for h in busiest_hours]}."
    aiInsight = ""
    try:
        aiInsight = await ai_service.generate_response(
            shop_context=f"Shop: {shop.get('name', '')}",
            history=[],
            user_message=f"Generate a weekly insight summary for these stats: {stats_summary}"
        )
    except Exception as e:
        aiInsight = f"AI insight unavailable: {e}"
    insight = InsightInDB(
        shopId=shop_id,
        weekStartDate=week_start,
        topQuestions=top_questions,
        busiestHours=busiest_hours,
        popularProducts=popular_products,
        automatedSales=automated_sales,
        aiInsight=aiInsight
    )
    insight.id = str(shop_id) + "_" + week_start.strftime("%Y%m%d")
    return insight

@router.post("/export/report")
async def export_report(
    current_user: UserInDB = Depends(get_current_user)
):
    # Logic to generate PDF/CSV
    return {"url": "https://example.com/report.pdf"}
