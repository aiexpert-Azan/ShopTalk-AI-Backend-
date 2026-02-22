from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserInDB
from app.models.product import ProductCreate, ProductUpdate, ProductResponse, ProductListResponse, ProductInDB
from bson import ObjectId

router = APIRouter()

@router.get("/", response_model=ProductListResponse)
async def list_products(
    page: int = 1,
    limit: int = 8,
    category: Optional[str] = None,
    sort: Optional[str] = None, # NEWEST_FIRST, PRICE_HIGH, PRICE_LOW
    current_user: UserInDB = Depends(get_current_user)
):
    skip = (page - 1) * limit
    
    # Get shop ID for current user
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        return {"products": [], "total": 0, "page": page, "limit": limit}
    
    shop_id = str(shop["_id"])
    query = {"shopId": shop_id}
    if category:
        query["category"] = category
        
    cursor = db.get_db().products.find(query)
    
    # Sorting
    if sort == "PRICE_HIGH":
        cursor.sort("price", -1)
    elif sort == "PRICE_LOW":
        cursor.sort("price", 1)
    else: # NEWEST_FIRST or default
        cursor.sort("createdAt", -1)
        
    total = await db.get_db().products.count_documents(query)
    cursor.skip(skip).limit(limit)
    
    products = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["shopId"] = str(doc["shopId"])
        products.append(ProductResponse(**doc))
        
    return {
        "products": products,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.post("/", response_model=ProductResponse)
async def create_product(
    product_in: ProductCreate,
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        # Auto-create shop if missing? Or error. Let's error for strictness.
        raise HTTPException(status_code=400, detail="Shop profile must be created first")
    
    shop_id = str(shop["_id"])
    
    # Create product document for database
    product_data = product_in.model_dump(by_alias=True)
    product_data["shopId"] = shop_id
    product_data["createdAt"] = datetime.utcnow()
    product_data["updatedAt"] = datetime.utcnow()
    
    result = await db.get_db().products.insert_one(product_data)
    
    # Fetch the created product and return it
    created_product = await db.get_db().products.find_one({"_id": result.inserted_id})
    created_product["_id"] = str(created_product["_id"])
    created_product["shopId"] = str(created_product["shopId"])
    
    return ProductResponse(**created_product)

@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product_in: ProductUpdate,
    current_user: UserInDB = Depends(get_current_user)
):
    # Verify ownership
    try:
        product = await db.get_db().products.find_one({"_id": ObjectId(product_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid product ID")
        
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop or str(product["shopId"]) != str(shop["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to update this product")
        
    update_data = product_in.model_dump(exclude_unset=True, by_alias=True)
    update_data["updatedAt"] = datetime.utcnow()
    
    await db.get_db().products.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": update_data}
    )
    
    updated_product = await db.get_db().products.find_one({"_id": ObjectId(product_id)})
    updated_product["_id"] = str(updated_product["_id"])
    updated_product["shopId"] = str(updated_product["shopId"])
    return ProductResponse(**updated_product)

@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    # Verify ownership
    try:
        product = await db.get_db().products.find_one({"_id": ObjectId(product_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid product ID")
        
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop or str(product["shopId"]) != str(shop["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this product")

    await db.get_db().products.delete_one({"_id": ObjectId(product_id)})
    return {"message": "Product deleted successfully"}
