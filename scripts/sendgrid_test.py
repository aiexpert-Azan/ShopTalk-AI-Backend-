import sys
from pathlib import Path
proj_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj_root))

import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.core.config import settings

# Use settings if available, else fall back to env
api_key = getattr(settings, 'SENDGRID_API_KEY', None) or os.environ.get('SENDGRID_API_KEY')
from_email = getattr(settings, 'SENDGRID_FROM_EMAIL', None) or os.environ.get('SENDGRID_FROM_EMAIL')

to_email = from_email  # send to same address to verify delivery

if not api_key:
    print('SENDGRID_API_KEY not set; aborting')
    raise SystemExit(1)

message = Mail(
    from_email=from_email,
    to_emails=to_email,
    subject='Test email from ShopTalk AI (sendgrid_test)',
    html_content='<strong>This is a test email sent from the local SendGrid test script.</strong>'
)

try:
    sg = SendGridAPIClient(api_key)
    resp = sg.send(message)
    print('SendGrid response status:', resp.status_code)
    print('SendGrid body:', resp.body)
    print('SendGrid headers:', resp.headers)
except Exception as e:
    print('SendGrid error:', str(e))
    raise
