import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')

if not account_sid or not auth_token:
    raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in .env file")

client = Client(account_sid, auth_token)

message = client.messages.create(
  from_='whatsapp:+14155238886',
  content_sid='HXb5b62575e6e4ff6129ad7c8efe1f983e',
  content_variables='{"1":"12/1","2":"3pm"}',
  to='whatsapp:+923269157985'
)

print(message.sid)
