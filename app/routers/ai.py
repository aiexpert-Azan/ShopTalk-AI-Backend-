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
    # Twilio sends form data, not JSON usually for creating messages, but for status callbacks it might vary.
    # Receiving messages: Twilio posts 'Body', 'From', 'To', etc. as Form Data.
    
    form_data = await request.form()
    incoming_msg = form_data.get('Body', '').strip()
    sender = form_data.get('From', '') # e.g., whatsapp:+1234567890
    
    # Verify signature if needed (X-Twilio-Signature header + auth token)
    # For MVP/Demo, skipping strict signature validation but it's recommended.
    
    if not incoming_msg:
        return {"status": "no message"}
        
    print(f"Received message from {sender}: {incoming_msg}")
    
    # 1. Identify shop/user (simplified: assumption or lookup)
    shop_context = "You are a helpful assistant." 
    
    # 2. Get history (mock or DB)
    history = []
    
    # 3. Generate AI response
    response_text = await ai_service.generate_response(shop_context, history, incoming_msg)
    
    # 4. Send response back via Twilio
    from app.services.twilio_service import twilio_service
    twilio_service.send_whatsapp_message(sender, response_text)
    
    return {"status": "ok"}
