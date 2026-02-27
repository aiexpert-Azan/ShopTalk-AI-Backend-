from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import db
from app.routers import auth, shop, products, orders, customers, ai, insights, billing, notifications

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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
    lifespan=lifespan,
    # Ye line redirects ke CORS errors ko khatam karegi
    redirect_slashes=False 
)

# CORS Middleware - Updated for Production
app.add_middleware(
    CORSMiddleware,
    # Specific origin dena behtar he lekin credentials ke liye "*" allow nahi hota agar allow_credentials=True ho
    allow_origins=[
        "https://v0-shopkeeper-ai-setup.vercel.app",
        "http://localhost:3000"
    ],
    allow_credentials=True,  # Isay True hona chahiye taake headers (tokens) pass ho sakein
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
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