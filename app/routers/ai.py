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
import json
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
    limit = PLAN_LIMITS.get(plan, 200)
    used = shop.get("messages_this_month", 0)
    if limit == float('inf'):
        return True, used, -1
    return used < limit, used, int(limit)


async def detect_order_intent(ai_service, incoming_msg: str) -> dict:
    """
    Ask AI if message is an order or general chat.
    Returns {"type": "order", "items": [...]} or {"type": "chat"}
    """
    detection_prompt = """
An ORDER means customer wants to BUY something.
If ORDER detected, return ONLY this JSON:
{
  'type': 'order',
  'items': [
    {
      'name': 'exact product name customer said',
      'quantity': 2,
      'variation': 'size/color/variant if mentioned',
      'special_instructions': 'any special notes'
    }
  ],
  'delivery_method': 'delivery or pickup',
  'special_note': 'any overall order note'
}
If NOT an order: {'type': 'chat'}
IMPORTANT: Respond with JSON only. No explanation. No extra text.
"""
    try:
        raw = await ai_service.generate_response(
            shop_context=detection_prompt,
            history=[],
            user_message=incoming_msg
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        result = json.loads(cleaned.replace("'", '"'))
        return result
    except Exception as e:
        logger.warning(f"Order detection failed, defaulting to chat: {e}")
        return {"type": "chat"}


async def enrich_order_items(items: list, shop_id: str) -> tuple[list, float]:
    """Match items to products in DB and calculate total"""
    enriched = []
    total = 0.0
    for item in items:
        product = await db.get_db().products.find_one({
            "shopId": shop_id,
            "name": {"$regex": item.get("name", ""), "$options": "i"}
        })
        price = float(product["price"]) if product and "price" in product else 0.0
        qty = int(item.get("quantity", 1))
        enriched.append({
            "name": item.get("name", "Unknown"),
            "quantity": qty,
            "variation": item.get("variation", ""),
            "special_instructions": item.get("special_instructions", ""),
            "price": price,
            "productId": str(product["_id"]) if product else "",
            "unit": product.get("unit", "piece") if product else "piece"
        })
        total += price * qty
    return enriched, total


@router.post("/chat", response_model=dict)
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
        shop_id = getattr(request, 'shop_id', None)
        user_id = getattr(request, 'user_id', None)
        logger.error(f"Chat endpoint error: {e}", exc_info=True, extra={"shop_id": shop_id, "user_id": user_id})
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
    print(f"Expected token: {settings.WEBHOOK_VERIFY_TOKEN}")
    print(f"Received token: {hub_verify_token}")
    if hub_mode == "subscribe" and hub_verify_token == settings.WEBHOOK_VERIFY_TOKEN:
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

        # ── FIND SHOP ──
        shop = await db.get_db().shops.find_one({"whatsapp_phone_number_id": phone_number_id})
        if not shop:
            logger.critical(f"Data isolation: No shop found for phone_number_id {phone_number_id}. Message ignored.")
            return {"status": "ok"}

        # ── MESSAGE LIMIT CHECK ──
        shop = await reset_monthly_if_needed(shop)
        can_send, used, limit = await check_message_limit(shop)

        if not can_send:
            plan = shop.get("plan", "free")
            limit_msg = (
                f"Aapki is maah ki {limit} messages ki limit khatam ho gayi hai. "
                f"Behtar service ke liye apna plan upgrade karein. "
                f"Abhi upgrade karein: https://shoptalkai.app/billing"
            )
            logger.warning(f"Shop {shop.get('name')} exceeded {plan} plan limit ({used}/{limit})")

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

        # ── BUILD SHOP CONTEXT ──
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

        # ── GET CONVERSATION HISTORY ──
        conversation = await db.get_db().conversations.find_one({
            "customerPhone": sender_phone,
            "shopId": shop_id
        }) if shop_id else await db.get_db().conversations.find_one({
            "customerPhone": sender_phone
        })
        history = conversation.get("messages", []) if conversation else []


        # ── 2-STEP ORDER FLOW ──
        # Step 2: Check for pending_address order
        pending_order = await db.get_db().orders.find_one({
            "customerPhone": sender_phone,
            "shopId": shop_id,
            "status": "pending_address"
        })
        if pending_order:
            # Treat incoming message as address
            address = incoming_msg
            enriched_items = pending_order.get("items", [])
            delivery_fee = pending_order.get("deliveryFee", 200)
            total = pending_order.get("totalAmount", 0)
            items_text = "\n".join([
                f"- {i['quantity']}x {i['name']}" + (f" ({i.get('variation','')})" if i.get('variation') else "") + f" — Rs.{int(i['price'] * i['quantity'])}"
                + (f"\n  Note: {i.get('special_instructions','')}" if i.get('special_instructions') else "")
                for i in enriched_items
            ])
            await db.get_db().orders.update_one(
                {"_id": pending_order["_id"]},
                {"$set": {
                    "status": "new",
                    "deliveryAddress": address,
                    "updatedAt": datetime.utcnow()
                },
                "$push": {"timeline": {
                    "action": "address_provided",
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": f"Delivery address provided: {address}"
                }}}
            )
            response_text = (
                f"✅ Order confirm ho gaya!\n\n"
                f"📦 Order Details:\n"
                f"{items_text}\n\n"
                f"📍 Address: {address}\n"
                f"🚚 Delivery Fee: Rs.{delivery_fee}\n"
                f"💰 Total: Rs.{int(total)}\n"
                f"⏰ Expected delivery: 45-60 minutes\n\n"
                f"Hum jald aapko update karenge. Shukriya! 🙏"
            )
        else:
            # Step 1: Order detection
            intent_data = await detect_order_intent(ai_service, incoming_msg)
            logger.info(f"Intent detection result: {intent_data}")
            if intent_data.get("type") == "order":
                items = intent_data.get("items", [])
                special_note = intent_data.get("special_note", "")
                if not items:
                    # AI said order but no items parsed — fall back to chat
                    response_text = await ai_service.generate_response(
                        shop_context=shop_context,
                        history=history,
                        user_message=incoming_msg
                    )
                else:
                    enriched_items, total = await enrich_order_items(items, shop_id)
                    delivery_fee = 200
                    # Save order to DB with pending_address status
                    order_doc = {
                        "shopId": shop_id,
                        "customerPhone": sender_phone,
                        "customerName": sender_phone,
                        "items": enriched_items,
                        "totalAmount": round(total + delivery_fee, 2),
                        "deliveryFee": delivery_fee,
                        "status": "pending_address",
                        "deliveryMethod": intent_data.get("delivery_method", "delivery"),
                        "paymentMethod": "COD",
                        "createdAt": datetime.utcnow(),
                        "updatedAt": datetime.utcnow(),
                        "timeline": [{
                            "action": "pending_address",
                            "timestamp": datetime.utcnow().isoformat(),
                            "message": "Order placed, waiting for address"
                        }],
                        "specialNote": special_note
                    }
                    await db.get_db().orders.insert_one(order_doc)
                    logger.info(f"New order (pending address) saved for {sender_phone} — Total: Rs.{total + delivery_fee}")
                    items_text = "\n".join([
                        f"- {i['quantity']}x {i['name']}" + (f" ({i['variation']})" if i.get('variation') else "") + f" — Rs.{int(i['price'] * i['quantity'])}"
                        + (f"\n  Note: {i['special_instructions']}" if i.get('special_instructions') else "")
                        for i in enriched_items
                    ])
                    response_text = (
                        f"✅ Aapka order note kar liya!\n\n"
                        f"📦 Order Details:\n"
                        f"{items_text}\n"
                        f"💰 Total: Rs.{int(total + delivery_fee)}\n\n"
                        f"🏠 Delivery ke liye apna address share karein?\n(Ghar ka address, gali, area, city)"
                    )
            else:
                # ── NORMAL Q&A FLOW ──
                try:
                    response_text = await ai_service.generate_response(
                        shop_context=shop_context,
                        history=history,
                        user_message=incoming_msg
                    )
                except Exception as e:
                    logger.error(f"AI error: {e}")
                    response_text = "Sorry, I'm having trouble right now. Please try again later."

        # ── SAVE CONVERSATION ──
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

        # ── INCREMENT MESSAGE COUNTER ──
        await db.get_db().shops.update_one(
            {"_id": shop["_id"]},
            {"$inc": {"messages_this_month": 1}}
        )

        # ── SEND WHATSAPP REPLY ──
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