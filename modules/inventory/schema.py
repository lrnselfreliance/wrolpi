from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass
class ItemPostRequest:
    brand: str
    name: str
    item_size: Decimal
    unit: str
    count: Decimal
    category: str
    subcategory: str
    expiration_date: date


@dataclass
class ItemPutRequest:
    id: int  # Ignored in favor of URL
    brand: str
    name: str
    item_size: Decimal
    unit: str
    count: Decimal
    serving: Decimal
    category: str
    subcategory: str
    expiration_date: date
    purchase_date: date
    created_at: datetime
    deleted_at: datetime
    inventory_id: int


@dataclass
class InventoryPostRequest:
    name: str


@dataclass
class InventoryPutRequest:
    name: str
