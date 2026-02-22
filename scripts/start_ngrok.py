from pyngrok import ngrok
import time
import uuid

ngrok.set_auth_token('35nMuzxn7e5xO6YXIdRIiHo0f0U_4pd1En2wpEzL4QfGQTuhr')

# Try to use ngrok CLI to kill old tunnels
import subprocess
try:
    subprocess.run(["ngrok", "http", "8000", "--inspect=false"], timeout=2)
except:
    pass

time.sleep(2)

# Connect with a unique session
session_id = str(uuid.uuid4())[:8]
try:
    t = ngrok.connect(8000)
    print('NGROK_URL=' + t.public_url)
    time.sleep(3600)
except Exception as e:
    print(f"Failed to connect: {e}")
    # Try alternate region
    print("Trying US-west region...")
    t = ngrok.connect(8000, region='us-west')
    print('NGROK_URL=' + t.public_url)
    time.sleep(3600)
