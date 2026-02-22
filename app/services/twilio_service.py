from twilio.rest import Client
from app.core.config import settings
import logging

class TwilioService:
    def __init__(self):
        self.client = None
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
    def send_whatsapp_message(self, to_number: str, body: str):
        if not self.client:
            logging.error("Twilio client not initialized")
            return False
            
        try:
            # Twilio WhatsApp numbers require 'whatsapp:' prefix
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
                
            from_number = settings.TWILIO_WHATSAPP_NUMBER
            if not from_number.startswith("whatsapp:"):
                # Default or user provided might vary, best to ensure prefix if missing in config or strict
                # Config default has it, but let's be safe
                from_number = f"whatsapp:{from_number}"

            message = self.client.messages.create(
                from_=from_number,
                body=body,
                to=to_number
            )
            return message.sid
        except Exception as e:
            logging.error(f"Failed to send WhatsApp message to {to_number}: {str(e)}", exc_info=True)
            return None

    # For Email, if using SendGrid, we usually use sendgrid library, NOT twilio client.
    # But if they want to use Twilio for everything, maybe they mean Twilio's SendGrid integration.
    # I'll add a helper here but likely we'd use a separate EmailService with sendgrid lib.
    # For now, I'll stick to WhatsApp here.

twilio_service = TwilioService()
