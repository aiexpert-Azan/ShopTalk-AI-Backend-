from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.deps import get_current_user
from app.core.database import db
from app.core.config import settings
from app.models.user import UserInDB
from app.models.conversation import ChatRequest, ConversationResponse, ConversationInDB, Message
from app.services.ai_service import ai_service
from datetime import datetime
from bson import ObjectId
import logging
from fastapi import Body

# Dummy client for testing (returns a static response)
class _DummyResp:
    class Choice:
        class Message:
            content = 'This is a mocked AI response.'
        message = Message()
    choices = [Choice()]

class _DummyClient:
    class chat:
        class completions:
            @staticmethod
            async def create(**kwargs):
                return _DummyResp()

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    # current_user: UserInDB = Depends(get_current_user) # Optional: make public for widget, or require key
):
    shop_context = "You are a helpful assistant for a general store."
    
    try:
        response_text = await ai_service.generate_response(
            shop_context=shop_context,
            history=request.conversation_history or [],
            user_message=request.message
        )
        return {"response": response_text, "shouldEscalate": False}
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"AI service error: {str(e)}"
        )


@router.post("/_internal/mock-ai")
async def set_mock_ai(enabled: bool = Body(True)):
    """Temporary endpoint to set a dummy AI client for safe local testing.
    POST {"enabled": true} will set a mock client; false restores real client by re-importing.
    """
    global ai_service
    if enabled:
        ai_service.client = _DummyClient()
        return {"mock": True}
    else:
        # reload the module to restore original client (best-effort)
        try:
            from importlib import reload
            import app.services.ai_service as mod
            reload(mod)
            ai_service = mod.ai_service
            return {"mock": False}
        except Exception as e:
            return {"error": str(e)}

@router.get("/conversations/{customer_id}", response_model=List[Message])
async def get_conversation_history(
    customer_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
        
    conversation = await db.get_db().conversations.find_one({
        "shopId": str(shop["_id"]),
        "customerId": customer_id
    })
    
    if not conversation:
        return []
        
    return conversation.get("messages", [])

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    form_data = await request.form()
    incoming_msg = form_data.get('Body', '').strip()
    sender = form_data.get('From', '')
    
    if not incoming_msg:
        return {"status": "no message"}
    
    logger.info(f"Received message from {sender}: {incoming_msg}")
    
    # 1. Customer phone number extract karo
    customer_phone = sender.replace("whatsapp:", "")
    
    # 2. Database se shop dhundo
    # Abhi sirf pehli shop use kar rahe hain testing ke liye
    shop = await db.get_db().shops.find_one({})
    
    if shop:
        shop_name = shop.get("name", "Our Shop")
        shop_description = shop.get("description", "")
        products = shop.get("products", [])
        
        shop_context = f"""You are a helpful WhatsApp assistant for {shop_name}.
{shop_description}

You help customers with:
- Product inquiries and availability
- Taking orders
- Answering questions about the shop
- Providing pricing information

Always be polite, helpful and respond in the same language the customer uses.
If customer writes in Urdu, respond in Urdu. If in English, respond in English."""
    else:
        shop_context = "You are a helpful shop assistant. Help customers with their orders and inquiries."
    
    # 3. Conversation history fetch karo
    conversation = await db.get_db().conversations.find_one({
        "customerPhone": customer_phone
    })
    history = conversation.get("messages", []) if conversation else []
    
    # 4. AI response generate karo
    try:
        response_text = await ai_service.generate_response(
            shop_context=shop_context,
            history=history,
            user_message=incoming_msg
        )
    except Exception as e:
        logger.error(f"AI error: {e}")
        response_text = "Sorry, I'm having trouble right now. Please try again later."
    
    # 5. Conversation history save karo
    new_messages = history + [
        {"role": "user", "content": incoming_msg},
        {"role": "assistant", "content": response_text}
    ]
    
    await db.get_db().conversations.update_one(
        {"customerPhone": customer_phone},
        {"$set": {
            "customerPhone": customer_phone,
            "messages": new_messages[-20:],  # Last 20 messages rakhna
            "updatedAt": datetime.utcnow()
        }},
        upsert=True
    )
    
    # 6. Twilio se reply bhejo
    from app.services.twilio_service import twilio_service
    twilio_service.send_whatsapp_message(sender, response_text)
    
    return {"status": "ok"}