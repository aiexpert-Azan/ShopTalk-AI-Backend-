from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse
from app.core.deps import get_current_user
from app.core.database import db
from app.core.config import settings
from app.models.user import UserInDB
from app.models.conversation import ChatRequest, ConversationResponse, ConversationInDB, Message
from app.services.ai_service import ai_service
from datetime import datetime
from bson import ObjectId
import logging
import httpx
from fastapi import Body

# Plan message limits
PLAN_LIMITS = {
    "free": 200,
    "starter": 1000,
    "growth": 5000,
    "business": float('inf')
}

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

async def reset_monthly_if_needed(shop):
    """Reset monthly counter if new month has started"""
    last_reset = shop.get("last_reset_date")
    now = datetime.utcnow()
    if not last_reset or last_reset.month != now.month or last_reset.year != now.year:
        await db.get_db().shops.update_one(
            {"_id": shop["_id"]},
            {"$set": {
                "messages_this_month": 0,
                "last_reset_date": now
            }}
        )
        shop["messages_this_month"] = 0
    return shop

async def check_message_limit(shop) -> tuple[bool, int, int]:
    """Returns (can_send, used, limit)"""
    plan = shop.get("plan", "free")
    limit = PLAN_LIMITS.get(plan, 100)
    used = shop.get("messages_this_month", 0)
    if limit == float('inf'):
        return True, used, -1
    return used < limit, used, int(limit)

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
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
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

@router.post("/_internal/mock-ai")
async def set_mock_ai(enabled: bool = Body(True)):
    global ai_service
    if enabled:
        ai_service.client = _DummyClient()
        return {"mock": True}
    else:
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

@router.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    logger.info(f"WhatsApp webhook verification: mode={hub_mode}, token={hub_verify_token}")
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(content=hub_challenge, status_code=200)
    logger.warning("WhatsApp webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        return {"status": "error", "message": "Invalid payload"}

    logger.info(f"WhatsApp webhook received: {payload}")

    try:
        entry = payload.get("entry", [])
        if not entry:
            return {"status": "ok"}
        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ok"}
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id", "")

        if not messages:
            return {"status": "ok"}

        message = messages[0]
        msg_type = message.get("type", "")
        sender_phone = message.get("from", "")

        if msg_type == "text":
            incoming_msg = message.get("text", {}).get("body", "").strip()
        elif msg_type == "button":
            incoming_msg = message.get("button", {}).get("text", "").strip()
        elif msg_type == "interactive":
            interactive = message.get("interactive", {})
            if "button_reply" in interactive:
                incoming_msg = interactive["button_reply"].get("title", "")
            elif "list_reply" in interactive:
                incoming_msg = interactive["list_reply"].get("title", "")
            else:
                incoming_msg = ""
        else:
            incoming_msg = ""

        if not incoming_msg or not sender_phone:
            return {"status": "ok"}

        logger.info(f"Received WhatsApp message from {sender_phone}: {incoming_msg}")

        # Find shop by phone_number_id
        shop = await db.get_db().shops.find_one({"whatsapp_phone_number_id": phone_number_id})
        if not shop:
            shop = await db.get_db().shops.find_one({})
            logger.warning(f"No shop found for phone_number_id {phone_number_id}, using fallback")

        if not shop:
            logger.error("No shop found at all")
            return {"status": "ok"}

        # ── MESSAGE LIMIT CHECK ──
        shop = await reset_monthly_if_needed(shop)
        can_send, used, limit = await check_message_limit(shop)

        if not can_send:
            plan = shop.get("plan", "free")
            limit_msg = (
                f"Aapki is maah ki {limit} messages ki limit khatam ho gayi hai. "
                f"Behtar service ke liye apna plan upgrade karein. "
                f"Abhi upgrade karein: https://v0-shopkeeper-ai-setup.vercel.app/billing"
            )
            logger.warning(f"Shop {shop.get('name')} exceeded {plan} plan limit ({used}/{limit})")

            # Send limit exceeded message
            access_token = shop.get("whatsapp_access_token") or settings.WHATSAPP_ACCESS_TOKEN
            send_phone_id = shop.get("whatsapp_phone_number_id") or phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID

            if access_token and send_phone_id:
                whatsapp_url = f"https://graph.facebook.com/v22.0/{send_phone_id}/messages"
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                message_payload = {
                    "messaging_product": "whatsapp",
                    "to": sender_phone,
                    "type": "text",
                    "text": {"body": limit_msg}
                }
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(whatsapp_url, json=message_payload, headers=headers, timeout=30)
                except Exception as e:
                    logger.error(f"Failed to send limit message: {e}")
            return {"status": "ok"}
        # ── END LIMIT CHECK ──

        # Build shop context
        shop_name = shop.get("name", "Our Shop")
        shop_description = shop.get("description", "")
        shop_id = str(shop.get("_id", ""))

        qa_pairs = await db.get_db().knowledge_base.find({
            "shopId": shop_id,
            "is_active": True
        }).to_list(50)

        knowledge_section = "\n".join([
            f"Q: {qa['question']}\nA: {qa['answer']}" for qa in qa_pairs
        ]) if qa_pairs else ""

        if knowledge_section:
            shop_context = f"""You are a helpful WhatsApp assistant for {shop_name}.
{shop_description}

IMPORTANT - Use these exact answers for these questions:
{knowledge_section}

If customer asks anything matching above questions, use the provided answer exactly.
For other questions, use your general knowledge about the shop.

You help customers with:
- Product inquiries and availability
- Taking orders
- Answering questions about the shop
- Providing pricing information

Always be polite, helpful and respond in the same language the customer uses.
If customer writes in Urdu, respond in Urdu. If in English, respond in English."""
        else:
            shop_context = f"""You are a helpful WhatsApp assistant for {shop_name}.
{shop_description}

You help customers with:
- Product inquiries and availability
- Taking orders
- Answering questions about the shop
- Providing pricing information

Always be polite, helpful and respond in the same language the customer uses.
If customer writes in Urdu, respond in Urdu. If in English, respond in English."""

        # Get conversation history
        conversation = await db.get_db().conversations.find_one({
            "customerPhone": sender_phone,
            "shopId": shop_id
        }) if shop_id else await db.get_db().conversations.find_one({
            "customerPhone": sender_phone
        })
        history = conversation.get("messages", []) if conversation else []

        # Generate AI response
        try:
            response_text = await ai_service.generate_response(
                shop_context=shop_context,
                history=history,
                user_message=incoming_msg
            )
        except Exception as e:
            logger.error(f"AI error: {e}")
            response_text = "Sorry, I'm having trouble right now. Please try again later."

        # Save conversation
        new_messages = history + [
            {"role": "user", "content": incoming_msg},
            {"role": "assistant", "content": response_text}
        ]
        await db.get_db().conversations.update_one(
            {"customerPhone": sender_phone, "shopId": shop_id} if shop_id else {"customerPhone": sender_phone},
            {"$set": {
                "customerPhone": sender_phone,
                "shopId": shop_id,
                "messages": new_messages[-20:],
                "updatedAt": datetime.utcnow()
            }},
            upsert=True
        )

        # ── INCREMENT COUNTER ──
        await db.get_db().shops.update_one(
            {"_id": shop["_id"]},
            {"$inc": {"messages_this_month": 1}}
        )
        # ── END INCREMENT ──

        # Send WhatsApp reply
        access_token = shop.get("whatsapp_access_token") or settings.WHATSAPP_ACCESS_TOKEN
        send_phone_id = shop.get("whatsapp_phone_number_id") or phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID

        if access_token and send_phone_id:
            whatsapp_url = f"https://graph.facebook.com/v22.0/{send_phone_id}/messages"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            message_payload = {
                "messaging_product": "whatsapp",
                "to": sender_phone,
                "type": "text",
                "text": {"body": response_text}
            }
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(whatsapp_url, json=message_payload, headers=headers, timeout=30)
                    if resp.status_code == 200:
                        logger.info(f"WhatsApp reply sent to {sender_phone}")
                    else:
                        logger.error(f"WhatsApp API error: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.error(f"Failed to send WhatsApp reply: {e}")
        else:
            logger.warning(f"No WhatsApp credentials, logging reply: {response_text}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}", exc_info=True)
        return {"status": "ok"}