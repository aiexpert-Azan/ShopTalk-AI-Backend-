import requests
import json

# ngrok API base (local ngrok agent)
ngrok_api = 'http://localhost:4040'

# List all tunnels
try:
    resp = requests.get(f'{ngrok_api}/api/tunnels', timeout=5)
    tunnels = resp.json().get('tunnels', [])
    print(f"Found {len(tunnels)} active tunnels:")
    for t in tunnels:
        print(f"  - {t['name']}: {t['public_url']}")
        # DELETE old tunnel
        del_resp = requests.delete(f"{ngrok_api}/api/tunnels/{t['name']}", timeout=5)
        print(f"    Deleted: {del_resp.status_code}")
except Exception as e:
    print(f"API call failed: {e}")
