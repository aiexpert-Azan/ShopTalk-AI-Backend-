import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj_root))

from app.services.twilio_service import twilio_service

print('Calling send_whatsapp_message...')
res = twilio_service.send_whatsapp_message('whatsapp:+14155551234', 'Test message from local sandbox check')
print('Result:', res)
