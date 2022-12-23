from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Union, Optional

from wrolpi.dates import from_timestamp


@dataclass
class ItemPostRequest:
    brand: str
    name: str
    item_size: Union[str, Decimal]
    unit: str
    count: Union[str, Decimal]
    category: str
    subcategory: str
    expiration_date: Optional[str]

    def __post_init__(self):
        self.item_size = Decimal(self.item_size) if self.item_size else None
        self.count = Decimal(self.count) if self.count else None
        self.expiration_date = datetime.fromisoformat(self.expiration_date) if self.expiration_date else None


@dataclass
class ItemPutRequest:
    id: int  # Ignored in favor of URL
    brand: Optional[str]
    name: Optional[str]
    item_size: Union[str, Decimal]
    unit: Optional[str]
    count: Union[str, Decimal]
    serving: Union[str, Decimal, None]
    category: Optional[str]
    subcategory: Optional[str]
    expiration_date: Optional[str]
    purchase_date: Optional[float]
    inventory_id: int
    created_at: Optional[str]
    deleted_at: Optional[str]

    def __post_init__(self):
        self.item_size = Decimal(self.item_size) if self.item_size else None
        self.count = Decimal(self.count) if self.count else None
        self.serving = Decimal(self.serving) if self.serving else None
        self.expiration_date = datetime.fromisoformat(self.expiration_date) if self.expiration_date else None
        self.created_at = datetime.fromisoformat(self.created_at) if self.created_at else None
        self.deleted_at = datetime.fromisoformat(self.deleted_at) if self.deleted_at else None


@dataclass
class InventoryPostRequest:
    name: str


@dataclass
class InventoryPutRequest:
    name: str
