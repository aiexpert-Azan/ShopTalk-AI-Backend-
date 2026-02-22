import httpx, random, time
base='https://hyperbolic-unliberally-lucretia.ngrok-free.dev'
print('Base URL:', base)

client = httpx.Client(timeout=15)

# Health
try:
    r=client.get(base+'/health')
    print('[API] GET /health', r.status_code, r.json())
except Exception as e:
    print('[API] GET /health ERROR', e)

# Signup with random phone
phone = '999' + str(random.randint(1000000,9999999))
signup_payload = {"phone": phone, "password": "TestPass123", "name": "Smoke Tester"}
try:
    r=client.post(base+'/api/auth/signup', json=signup_payload)
    print('[API] POST /api/auth/signup', r.status_code, r.text)
except Exception as e:
    print('[API] POST /api/auth/signup ERROR', e)

# Login
login_payload = {"phone": phone, "password": "TestPass123"}
try:
    r=client.post(base+'/api/auth/login', json=login_payload)
    print('[API] POST /api/auth/login', r.status_code, r.text)
    token = None
    if r.status_code==200:
        token = r.json().get('access_token')
except Exception as e:
    print('[API] POST /api/auth/login ERROR', e)

# Get profile
if token:
    headers={'Authorization': f'Bearer {token}'}
    try:
        r=client.get(base+'/api/auth/profile', headers=headers)
        print('[API] GET /api/auth/profile', r.status_code, r.text)
    except Exception as e:
        print('[API] GET /api/auth/profile ERROR', e)

# Shop profile create (simulate onboarding)
shop_payload={'name':'Smoke Shop','category':'clothing','location':'Test City'}
try:
    # try without auth first
    r=client.post(base+'/api/shop/profile', json=shop_payload)
    print('[API] POST /api/shop/profile (unauth)', r.status_code, r.text)
except Exception as e:
    print('[API] POST /api/shop/profile ERROR', e)

# If token, try with auth
if token:
    try:
        r=client.post(base+'/api/shop/profile', json=shop_payload, headers=headers)
        print('[API] POST /api/shop/profile (auth)', r.status_code, r.text)
    except Exception as e:
        print('[API] POST /api/shop/profile (auth) ERROR', e)

client.close()
