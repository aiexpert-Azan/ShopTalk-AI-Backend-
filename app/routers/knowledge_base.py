from fastapi import APIRouter, Depends, HTTPException, status, Body
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.shop import Shop
from app.models.user import User
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

router = APIRouter()

# Helper to convert MongoDB document to dict

def qa_to_dict(qa):
    qa["id"] = str(qa["_id"])
    qa.pop("_id", None)
    return qa

@router.get("/", response_model=List[dict])
async def get_knowledge_base(current_user: User = Depends(get_current_user), db=Depends(get_db)):
    shop = await db.shop.find_one({"ownerPhone": current_user.phone})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    qa_pairs = await db.knowledge_base.find({"shopId": str(shop["_id"])}).to_list(100)
    return [qa_to_dict(qa) for qa in qa_pairs]

@router.post("/", response_model=dict)
async def add_qa_pair(
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    shop = await db.shop.find_one({"ownerPhone": current_user.phone})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    qa_doc = {
        "shopId": str(shop["_id"]),
        "question": body.get("question"),
        "answer": body.get("answer"),
        "category": body.get("category"),
        "is_active": True,
        "created_at": datetime.utcnow()
    }
    result = await db.knowledge_base.insert_one(qa_doc)
    qa_doc["_id"] = result.inserted_id
    return qa_to_dict(qa_doc)

@router.put("/{qa_id}", response_model=dict)
async def update_qa_pair(
    qa_id: str,
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    update_fields = {k: v for k, v in body.items() if k in ["question", "answer", "category", "is_active"]}
    result = await db.knowledge_base.update_one({"_id": ObjectId(qa_id)}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Q&A pair not found")
    qa = await db.knowledge_base.find_one({"_id": ObjectId(qa_id)})
    return qa_to_dict(qa)

@router.delete("/{qa_id}", response_model=dict)
async def delete_qa_pair(
    qa_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db)
):
    result = await db.knowledge_base.delete_one({"_id": ObjectId(qa_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Q&A pair not found")
    return {"id": qa_id, "deleted": True}
