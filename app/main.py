
from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging
import sys
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import db
from app.routers import auth, shop, products, orders, customers, ai, insights, billing, notifications, whatsapp, knowledge_base, admin


# --- SlowAPI Rate Limiter ---
from app.core.limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[INFO] Application starting up...")
    yield
    print("[INFO] Application shutting down...")
    try:
        db.close()
    except Exception:
        pass


# Environment variable check at startup
required_env_vars = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "WHATSAPP_CLIENT_ID",
    "WHATSAPP_CLIENT_SECRET",
    "WHATSAPP_REDIRECT_URI"
]
missing_vars = [var for var in required_env_vars if not getattr(settings, var, None)]
if missing_vars:
    logging.error(f"Missing required environment variables: {missing_vars}")
    sys.exit(1)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)



app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://shoptalkai.app",
        "https://www.shoptalkai.app",
        "https://admin.shoptalkai.app",
        "https://v0-shopkeeper-ai-setup.vercel.app",
        "https://v0-admin-panel-for-shop-talk.vercel.app",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(customers.router, prefix="/api/customers", tags=["Customers"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(insights.router, prefix="/api/insights", tags=["Insights"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(shop.router, prefix="/api/shop", tags=["Shop"])
app.include_router(whatsapp.router, prefix="/api/whatsapp", tags=["WhatsApp"])
app.include_router(knowledge_base.router, prefix="/api/knowledge-base", tags=["Knowledge Base"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])

@app.get("/health")
async def health_check():
    return {"status": "ok", "app_name": settings.APP_NAME}

@app.get("/debug/routes")
async def list_routes():
    routes = []
    for route in app.routes:
        if hasattr(route, "path"):
            routes.append({"path": route.path, "methods": list(getattr(route, "methods", []))})
    return {"routes": routes}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)