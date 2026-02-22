from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserInDB
from app.models.shop import ShopCreate, ShopUpdate, ShopResponse, ShopInDB, BusinessHours, DeliverySettings, AIConfig

router = APIRouter()

async def get_current_shop(current_user: UserInDB = Depends(get_current_user)):
    shop_data = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if shop_data:
        shop_data["_id"] = str(shop_data["_id"])
        return ShopInDB(**shop_data)
    return None

@router.post("/profile", response_model=ShopResponse)
async def create_or_update_shop_profile(
    shop_in: ShopCreate,
    current_user: UserInDB = Depends(get_current_user)
):
    existing_shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    
    if existing_shop:
        update_data = shop_in.model_dump(exclude_unset=True, by_alias=True)
        update_data["updatedAt"] = datetime.utcnow()
        
        await db.get_db().shops.update_one(
            {"_id": existing_shop["_id"]},
            {"$set": update_data}
        )
        existing_shop.update(update_data)
        existing_shop["_id"] = str(existing_shop["_id"])
        return ShopInDB(**existing_shop)
    else:
        new_shop = ShopInDB(
            userId=str(current_user.id),
            **shop_in.model_dump(by_alias=True)
        )
        result = await db.get_db().shops.insert_one(new_shop.model_dump(by_alias=True, exclude={"id"}))
        new_shop.id = str(result.inserted_id)
        return new_shop

@router.get("/settings", response_model=ShopResponse)
async def get_shop_settings(
    current_user: UserInDB = Depends(get_current_user)
):
    existing_shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not existing_shop:
        # Create default shop if not exists (lazy creation) or 404
        # For this app, maybe 404 or return empty defaults. 
        # Let's return empty defaults for smoother onboarding
        default_shop = ShopInDB(userId=str(current_user.id), name="My Shop")
        result = await db.get_db().shops.insert_one(default_shop.model_dump(by_alias=True, exclude={"id"}))
        default_shop.id = str(result.inserted_id)
        return default_shop
        
    existing_shop["_id"] = str(existing_shop["_id"])
    return ShopInDB(**existing_shop)

@router.post("/business-hours", response_model=ShopResponse)
async def update_business_hours(
    hours: BusinessHours,
    current_user: UserInDB = Depends(get_current_user)
):
    result = await db.get_db().shops.find_one_and_update(
        {"userId": str(current_user.id)},
        {"$set": {"businessHours": hours.model_dump(by_alias=True), "updatedAt": datetime.utcnow()}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shop not found")
    result["_id"] = str(result["_id"])
    return ShopInDB(**result)

@router.post("/delivery-settings", response_model=ShopResponse)
async def update_delivery_settings(
    delivery: DeliverySettings,
    current_user: UserInDB = Depends(get_current_user)
):
    result = await db.get_db().shops.find_one_and_update(
        {"userId": str(current_user.id)},
        {"$set": {"deliverySettings": delivery.model_dump(by_alias=True), "updatedAt": datetime.utcnow()}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shop not found")
    result["_id"] = str(result["_id"])
    return ShopInDB(**result)

@router.post("/ai-config", response_model=ShopResponse)
async def update_ai_config(
    ai_config: AIConfig,
    current_user: UserInDB = Depends(get_current_user)
):
    result = await db.get_db().shops.find_one_and_update(
        {"userId": str(current_user.id)},
        {"$set": {"aiConfig": ai_config.model_dump(by_alias=True), "updatedAt": datetime.utcnow()}},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Shop not found")
    result["_id"] = str(result["_id"])
    return ShopInDB(**result)
