import openai
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.client = openai.AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

    async def generate_response(self, shop_context: str, history: list, user_message: str):
        messages = [{"role": "system", "content": shop_context}]
        # Add history (limit to last 5-10 messages)
        for msg in history[-10:]:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role") or msg.get("sender") or msg.get("from")
            if role:
                role = role.lower()
                if role in ("customer", "user"):
                    role = "user"
                elif role in ("ai", "assistant", "bot", "system"):
                    role = "assistant"
                else:
                    role = "user"
            else:
                role = "user"
            content = msg.get("content") or msg.get("text") or msg.get("message")
            if content is None:
                continue
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        retries = 3
        for attempt in range(retries):
            try:
                response = await self.client.chat.completions.create(
                    model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=300
                )
                content = response.choices[0].message.content
                if not content or not isinstance(content, str) or not content.strip():
                    logger.error("AI returned empty/null response", extra={"shop_context": shop_context})
                    return "Sorry, I couldn't generate a response right now."
                return content
            except Exception as e:
                if hasattr(e, "status_code") and e.status_code in (429, 500) and attempt < retries - 1:
                    logger.warning(f"Azure OpenAI retry {attempt+1} due to {e}", extra={"shop_context": shop_context})
                    import asyncio
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                logger.error(f"Error calling Azure OpenAI: {e}", exc_info=True, extra={"shop_context": shop_context})
                raise

ai_service = AIService()
