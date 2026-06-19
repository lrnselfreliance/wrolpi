from dataclasses import dataclass
from typing import Optional


@dataclass
class InventoryPostRequest:
    name: str
    type: Optional[str] = 'food'


@dataclass
class InventoryRestoreRequest:
    backup_date: str
    mode: str
