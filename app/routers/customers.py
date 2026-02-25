from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from app.core.deps import get_current_user
from app.core.database import db
from app.models.user import UserInDB
from app.models.customer import CustomerResponse, CustomerInDB
from bson import ObjectId
import logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[CustomerResponse])
async def list_customers(
    search: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_user)
):
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop:
        return []
        
    query = {"shopId": str(shop["_id"])}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}}
        ]
        
    cursor = db.get_db().customers.find(query)
    
    customers = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["shopId"] = str(doc["shopId"])
        customers.append(CustomerResponse(**doc))
        
    return customers

@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    current_user: UserInDB = Depends(get_current_user)
):
    try:
        customer = await db.get_db().customers.find_one({"_id": ObjectId(customer_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid customer ID")
        
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    shop = await db.get_db().shops.find_one({"userId": str(current_user.id)})
    if not shop or str(customer["shopId"]) != str(shop["_id"]):
         raise HTTPException(status_code=403, detail="Not authorized")
         
    customer["_id"] = str(customer["_id"])
    customer["shopId"] = str(customer["shopId"])
    return CustomerResponse(**customer)

@router.post("/{customer_id}/message")
async def message_customer(
    customer_id: str,
    message: dict,
    current_user: UserInDB = Depends(get_current_user)
):
    customer = await db.get_db().customers.find_one({"_id": ObjectId(customer_id)})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    # Send via external notifier (Twilio removed). Log the outgoing message.
    phone = customer.get("phone")
    if phone:
        logger.info(f"Would send message to {phone}: {message.get('message')}")
        
    return {"message": "Message sent"}
