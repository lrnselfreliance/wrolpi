from dataclasses import dataclass
from typing import Optional


@dataclass
class InventoryPostRequest:
    name: str
    type: Optional[str] = 'food'
