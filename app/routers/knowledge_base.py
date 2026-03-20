from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File
from pypdf import PdfReader
import json
import io
from app.core.database import db
from app.core.deps import get_current_user
from app.models.user import UserInDB
from app.services.ai_service import ai_service
from app.core.config import settings
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

router = APIRouter()

# --- Knowledge Base PDF Import Endpoint ---
@router.post("/import-pdf")
async def import_knowledge_base_pdf(
    file: UploadFile = File(...),
    current_user: UserInDB = Depends(get_current_user)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF allowed.")
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop_id = str(shop["_id"])

    content = await file.read()
    try:
        reader = PdfReader(io.BytesIO(content))
        extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read PDF: {e}")
    
    if not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No text found in PDF.")

    prompt = (
        "Extract FAQ question and answer pairs from this document. "
        "Return ONLY a valid JSON array like: "
        '[{"question": "...", "answer": "..."}, ...] '
        "Extract as many relevant Q&A pairs as possible. "
        "Do not include any text before or after the JSON array.\n"
        f"Document text: {extracted_text[:6000]}"
    )
    
    try:
        response = await ai_service.client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1200
        )
        answer = response.choices[0].message.content.strip()
        # Clean up response
        if answer.startswith("```"):
            answer = answer.split("```")[1]
            if answer.startswith("json"):
                answer = answer[4:]
        answer = answer.strip()
        qa_pairs = json.loads(answer)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="AI returned invalid JSON. Try a different PDF.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {str(e)}")

    if not isinstance(qa_pairs, list):
        raise HTTPException(status_code=500, detail="AI did not return a list of Q&A pairs.")

    imported = 0
    questions = []
    for qa in qa_pairs:
        try:
            question = qa.get("question")
            answer = qa.get("answer")
            if not question or not answer:
                continue
            doc = {
                "shopId": shop_id,
                "question": question,
                "answer": answer,
                "is_active": True,
                "source": "pdf_import",
                "created_at": datetime.utcnow()
            }
            await db.get_db().knowledge_base.insert_one(doc)
            imported += 1
            questions.append(question)
        except Exception:
            continue

    return {"imported": imported, "questions": questions}

def qa_to_dict(qa):
    qa["id"] = str(qa["_id"])
    qa.pop("_id", None)
    return qa

@router.get("/", response_model=List[dict])
async def get_knowledge_base(current_user: UserInDB = Depends(get_current_user)):
    shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"owner_phone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    qa_pairs = await db.get_db().knowledge_base.find({"shopId": str(shop["_id"])}).to_list(100)
    return [qa_to_dict(qa) for qa in qa_pairs]

@router.post("/", response_model=dict)
async def add_qa_pair(
    body: dict = Body(...),
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"owner_phone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
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
    result = await db.get_db().knowledge_base.insert_one(qa_doc)
    qa_doc["_id"] = result.inserted_id
    return qa_to_dict(qa_doc)

@router.put("/{qa_id}", response_model=dict)
async def update_qa_pair(
    qa_id: str,
    body: dict = Body(...),
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"owner_phone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    update_fields = {k: v for k, v in body.items() if k in ["question", "answer", "category", "is_active"]}
    result = await db.get_db().knowledge_base.update_one(
        {"_id": ObjectId(qa_id)}, {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Q&A pair not found")
    qa = await db.get_db().knowledge_base.find_one({"_id": ObjectId(qa_id)})
    return qa_to_dict(qa)

@router.delete("/{qa_id}", response_model=dict)
async def delete_qa_pair(
    qa_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"owner_phone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    result = await db.get_db().knowledge_base.delete_one({"_id": ObjectId(qa_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Q&A pair not found")
    return {"id": qa_id, "deleted": True}