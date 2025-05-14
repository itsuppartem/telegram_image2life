from datetime import datetime
from typing import List, Optional, Dict

from pydantic import BaseModel, Field


class PaymentInfo(BaseModel):
    item_name: str
    quantity: int
    price: float
    status: str
    created_at: datetime
    generations_added: Optional[bool] = False
    cancellation_details: Optional[dict] = None


class User(BaseModel):
    chat_id: int
    username: str
    ozhivashki: int = 1
    generation_count: int = 0
    last_generation_time: Optional[datetime] = None
    registered_at: datetime = Field(default_factory=datetime.now)
    referral_code: Optional[str] = None
    referred_by: Optional[int] = None
    referral_bonus_claimed: bool = False
    first_generation_time: Optional[datetime] = None
    daily_bonus_claimed_today: bool = False
    daily_bonus_streak: int = 0
    discount_offered: bool = False
    last_activity_time: Optional[datetime] = Field(default_factory=datetime.now)
    advertising_source: Optional[str] = None
    yookassa_payments: Dict[str, PaymentInfo] = {}

    class Config:
        orm_mode = True


class UserCreate(BaseModel):
    chat_id: int
    username: str
    referral_code: Optional[str] = None
    advertising_source: Optional[str] = None


class PaymentRequestBody(BaseModel):
    item_name: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class GenerationResponse(BaseModel):
    main_images: List[str]
    bonus_images: List[str]
    ozhivashki_spent: int
    new_balance: Optional[int] = None


class SourceCreate(BaseModel):
    campaign_name: str
