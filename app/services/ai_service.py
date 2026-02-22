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
            # support different history shapes and be defensive against missing keys
            if not isinstance(msg, dict):
                continue
            role = msg.get("role") or msg.get("sender") or msg.get("from")
            # normalize common role names
            if role:
                role = role.lower()
                if role in ("customer", "user"):
                    role = "user"
                elif role in ("ai", "assistant", "bot", "system"):
                    role = "assistant"
                else:
                    # default to user for unknown roles
                    role = "user"
            else:
                role = "user"

            content = msg.get("content") or msg.get("text") or msg.get("message")
            if content is None:
                # skip entries with no content
                continue

            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=messages,
                temperature=0.7,
                max_tokens=300
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling Azure OpenAI: {e}", exc_info=True)
            raise

ai_service = AIService()
