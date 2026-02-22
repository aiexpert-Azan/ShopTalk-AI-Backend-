import sys
from pathlib import Path
# Ensure project root is on sys.path
proj_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj_root))

from app.services.twilio_service import twilio_service
from app.core.config import settings

print('Twilio client initialized:', bool(twilio_service.client))
if twilio_service.client:
    try:
        acc = twilio_service.client.api.accounts(settings.TWILIO_ACCOUNT_SID).fetch()
        print('Account SID:', acc.sid)
        print('Account friendly_name:', getattr(acc, 'friendly_name', 'n/a'))
        print('Account status:', getattr(acc, 'status', 'n/a'))
    except Exception as e:
        print('Twilio API error:', str(e))
else:
    print('No Twilio client configured')
