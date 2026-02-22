from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import db
from app.routers import auth, shop, products, orders, customers, ai, insights, billing, notifications

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - Database connection happens lazily on first use
    print("[INFO] Application starting up...")
    yield
    # Shutdown
    print("[INFO] Application shutting down...")
    try:
        db.close()
    except Exception:
        pass

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing; restrict in production
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

@app.get("/health")
async def health_check():
    return {"status": "ok", "app_name": settings.APP_NAME}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
