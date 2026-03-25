from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File
from pypdf import PdfReader
import json
import io
import logging
import re
import time
import requests
from bs4 import BeautifulSoup
from app.core.database import db
from app.core.deps import get_current_user
from app.models.user import UserInDB
from app.services.ai_service import ai_service
from app.core.config import settings
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

router = APIRouter()
logger = logging.getLogger(__name__)

# === Helper: Category Detection ===
def detect_category(question: str, answer: str) -> str:
    text = f"{question} {answer}".lower()
    if any(k in text for k in ["price", "cost", "fee", "charges", "rate", "kitna", "payment"]):
        return "Billing"
    if any(k in text for k in ["deliver", "shipping", "courier", "send", "bhejo"]):
        return "Delivery"
    if any(k in text for k in ["return", "refund", "exchange", "wapas", "cancel"]):
        return "Returns"
    if any(k in text for k in ["time", "hour", "open", "close", "timing", "schedule", "waqt"]):
        return "Timing"
    if any(k in text for k in ["product", "item", "available", "stock", "menu", "dish"]):
        return "Products"
    if any(k in text for k in ["location", "address", "where", "kahan", "direction"]):
        return "Location"
    if any(k in text for k in ["book", "reserve", "reservation", "table"]):
        return "Reservations"
    return "General"

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
        "Also assign a category to each pair from these options ONLY: "
        "General, Products, Delivery, Returns, Timing, Billing, Other. "
        "Return ONLY a valid JSON array like: "
        '[{"question": "...", "answer": "...", "category": "General"}, ...] '
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
    skipped = 0
    questions = []

    for qa in qa_pairs:
        try:
            question = qa.get("question")
            answer = qa.get("answer")
            category = qa.get("category", "General")

            if not question or not answer:
                continue

            existing = await db.get_db().knowledge_base.find_one({
                "shopId": shop_id,
                "question": question
            })
            if existing:
                skipped += 1
                continue

            doc = {
                "shopId": shop_id,
                "question": question,
                "answer": answer,
                "category": category,
                "is_active": True,
                "source": "pdf_import",
                "created_at": datetime.utcnow()
            }
            await db.get_db().knowledge_base.insert_one(doc)
            imported += 1
            questions.append(question)
        except Exception:
            continue

    return {"imported": imported, "skipped": skipped, "questions": questions}


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
    qa_pairs = await db.get_db().knowledge_base.find(
        {"shopId": str(shop["_id"])}
    ).to_list(100)
    return [qa_to_dict(qa) for qa in qa_pairs]

# === CHANGE 1: Prevent Duplicate Questions (Upsert) ===
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
    shop_id = str(shop["_id"])
    question = body.get("question")
    answer = body.get("answer")
    category = body.get("category", "General")
    if not question or not answer:
        raise HTTPException(status_code=400, detail="Question and answer required.")
    # Auto-detect category if missing or General
    if not category or category == "General":
        category = detect_category(question, answer)
    # Check for duplicate (case-insensitive exact match)
    existing = await db.get_db().knowledge_base.find_one({
        "shopId": shop_id,
        "question": {"$regex": f"^{re.escape(question)}$", "$options": "i"}
    })
    if existing:
        # Update answer/category
        await db.get_db().knowledge_base.update_one(
            {"_id": existing["_id"]},
            {"$set": {"answer": answer, "category": category, "updated_at": datetime.utcnow()}}
        )
        return {"message": "Q&A updated (duplicate prevented)", "id": str(existing["_id"])}
    # Insert new
    qa_doc = {
        "shopId": shop_id,
        "question": question,
        "answer": answer,
        "category": category,
        "is_active": True,
        "created_at": datetime.utcnow()
    }
    result = await db.get_db().knowledge_base.insert_one(qa_doc)
    qa_doc["_id"] = result.inserted_id
    return qa_to_dict(qa_doc)

# === CHANGE 1: Bulk Upsert Endpoint ===
@router.post("/bulk-upsert", response_model=dict)
async def bulk_upsert_qa_pairs(
    body: List[dict] = Body(...),
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"ownerPhone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"owner_phone": current_user.phone})
    if not shop:
        shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop_id = str(shop["_id"])
    inserted = 0
    updated = 0
    for item in body:
        question = item.get("question")
        answer = item.get("answer")
        category = item.get("category", "General")
        if not question or not answer:
            continue
        if not category or category == "General":
            category = detect_category(question, answer)
        existing = await db.get_db().knowledge_base.find_one({
            "shopId": shop_id,
            "question": {"$regex": f"^{re.escape(question)}$", "$options": "i"}
        })
        if existing:
            await db.get_db().knowledge_base.update_one(
                {"_id": existing["_id"]},
                {"$set": {"answer": answer, "category": category, "updated_at": datetime.utcnow()}}
            )
            updated += 1
        else:
            doc = {
                "shopId": shop_id,
                "question": question,
                "answer": answer,
                "category": category,
                "is_active": True,
                "created_at": datetime.utcnow()
            }
            await db.get_db().knowledge_base.insert_one(doc)
            inserted += 1
    total = inserted + updated
    return {"inserted": inserted, "updated": updated, "total": total}

# === CHANGE 3: Delete All Endpoint ===
@router.delete("/clear-all", response_model=dict)
async def clear_knowledge_base(current_user: UserInDB = Depends(get_current_user)):
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop_id = str(shop["_id"])
    result = await db.get_db().knowledge_base.delete_many({"shopId": shop_id})
    return {"message": "Knowledge base cleared", "deleted_count": result.deleted_count}

# === CHANGE 4: Website Scraping Endpoint ===
@router.post("/scrape-website", response_model=dict)
async def scrape_website(
    body: dict = Body(...),
    current_user: UserInDB = Depends(get_current_user)
):
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL required")
    if not url.startswith("http"):
        url = "https://" + url
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop_id = str(shop["_id"])
    from urllib.parse import urljoin, urlparse
    scraped_content = ""
    base_url = url
    logger.info(f"Scraping URL: {base_url}")
    session = requests.Session()
    headers1 = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    session.headers.update(headers1)
    homepage_html = ""
    try:
        response = session.get(base_url, timeout=30)
        logger.info(f"Homepage status: {response.status_code}")
        logger.info(f"Response length: {len(response.text)}")
        logger.info(f"First 500 chars: {response.text[:500]}")
        if response.status_code == 200:
            homepage_html = response.text
        elif response.status_code in [403, 429]:
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
            })
            response = session.get(base_url, timeout=30)
            logger.info(f"Homepage status (fallback UA): {response.status_code}")
            logger.info(f"Response length (fallback UA): {len(response.text)}")
            logger.info(f"First 500 chars (fallback UA): {response.text[:500]}")
            if response.status_code == 200:
                homepage_html = response.text
            else:
                raise HTTPException(status_code=400, detail="Could not access website")
        elif response.status_code == 404:
            raise HTTPException(status_code=400, detail="Website returned 404 Not Found")
        else:
            raise HTTPException(status_code=400, detail=f"Website returned {response.status_code}")
    except requests.Timeout:
        raise HTTPException(status_code=400, detail="Website took too long to respond")
    except Exception as e:
        logger.error(f"Error scraping homepage: {e}")
        raise HTTPException(status_code=400, detail="Could not access homepage of website")
    # Parse homepage HTML and improved text extraction
    soup = BeautifulSoup(homepage_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "path"]):
        tag.decompose()

    important_text = []
    # Headings
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        t = tag.get_text(strip=True)
        if t:
            important_text.append(t)
    # Paragraphs
    for tag in soup.find_all("p"):
        t = tag.get_text(strip=True)
        if t:
            important_text.append(t)
    # List items
    for tag in soup.find_all("li"):
        t = tag.get_text(strip=True)
        if t:
            important_text.append(t)
    # Table cells
    for tag in soup.find_all(["td", "th"]):
        t = tag.get_text(strip=True)
        if t:
            important_text.append(t)
    # Divs with short text (menu items, prices)
    for tag in soup.find_all("div"):
        t = tag.get_text(strip=True)
        if t and len(t) < 200:
            important_text.append(t)
    # Combine and deduplicate
    seen = set()
    unique_text = []
    for t in important_text:
        if t not in seen:
            seen.add(t)
            unique_text.append(t)
    clean_text = "\n".join(unique_text)
    logger.info(f"Extracted {len(clean_text)} chars from {url}")
    logger.info(f"Preview: {clean_text[:300]}")
    if not clean_text or len(clean_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Could not extract content")
    scraped_content = clean_text
    # --- Find internal links for further scraping (optional, can keep or remove) ---
    links = soup.find_all("a", href=True)
    internal_links = []
    for link in links:
        href = link["href"]
        full_url = urljoin(base_url, href)
        if urlparse(full_url).netloc == urlparse(base_url).netloc:
            if full_url not in internal_links and full_url != base_url:
                internal_links.append(full_url)
    # (Optional: scrape internal links as before, or skip for simplicity)
    # --- AI Extraction ---
    logger.info(f"Sending to OpenAI, content length: {len(scraped_content)}")
    system_prompt = """
You are helping build a WhatsApp chatbot for a Pakistani business.
You must respond with ONLY a valid JSON array. No explanations. No markdown. No code fences. Start your response with [ and end with ]
"""
    user_prompt = """
Extract all useful information from this business website and generate 25-35 Question & Answer pairs.

Focus on:
- Prices, charges, fees
- Menu items / products / services
- Timing and hours
- Location and directions
- Reservation / booking process
- Delivery information
- Contact details
- Special offers or packages
- FAQs

Write questions in Pakistani style (Urdu/English mix).
Examples: 'Price kya hai?', 'Delivery charges kitne hain?'

For each Q&A also detect its category from:
[General, Products, Delivery, Returns, Timing, Billing, Location, Reservations]

Return ONLY valid JSON array:
[
    {
        "question": "...",
        "answer": "...",
        "category": "..."
    }
]
"""
    try:
        response = await ai_service.client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt + "\n\nWebsite Content:\n" + scraped_content[:12000]}
            ],
            temperature=0.2,
            max_tokens=2000
        )
        raw_response = response.choices[0].message.content.strip()
        logger.info(f"OpenAI raw response: {raw_response[:500]}")
        # Remove markdown code fences and extract only the JSON array
        if "```" in raw_response:
            raw_response = raw_response.split("```", 1)[-1]
            if raw_response.startswith("json"):
                raw_response = raw_response[4:]
        # Extract only the JSON array
        start = raw_response.find("[")
        end = raw_response.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array found in response")
        raw_response = raw_response[start:end]
        qa_pairs = json.loads(raw_response)
    except json.JSONDecodeError:
        logger.error("AI returned invalid JSON for website scraping.")
        raise HTTPException(status_code=500, detail="AI returned invalid JSON.")
    except Exception as e:
        logger.error(f"AI extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI extraction failed: {e}")
    if not isinstance(qa_pairs, list):
        raise HTTPException(status_code=500, detail="AI did not return a list of Q&A pairs.")
    inserted = 0
    updated = 0
    for qa in qa_pairs:
        question = qa.get("question")
        answer = qa.get("answer")
        category = qa.get("category", "General")
        if not question or not answer:
            continue
        if not category or category == "General":
            category = detect_category(question, answer)
        existing = await db.get_db().knowledge_base.find_one({
            "shopId": shop_id,
            "question": {"$regex": f"^{re.escape(question)}$", "$options": "i"}
        })
        if existing:
            await db.get_db().knowledge_base.update_one(
                {"_id": existing["_id"]},
                {"$set": {"answer": answer, "category": category, "updated_at": datetime.utcnow()}}
            )
            updated += 1
        else:
            doc = {
                "shopId": shop_id,
                "question": question,
                "answer": answer,
                "category": category,
                "is_active": True,
                "created_at": datetime.utcnow()
            }
            await db.get_db().knowledge_base.insert_one(doc)
            inserted += 1
    total = inserted + updated
    return {
        "message": "Website scraped successfully",
        "inserted": inserted,
        "updated": updated,
        "total": total,
        "qa_pairs": qa_pairs
    }

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
    update_fields = {
        k: v for k, v in body.items()
        if k in ["question", "answer", "category", "is_active"]
    }
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
    return {"message": "Q&A pair deleted", "id": qa_id}