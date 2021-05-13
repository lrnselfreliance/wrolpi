from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship

from api.db import Base


class Item(Base):
    __tablename__ = 'item'
    id = Column(Integer, primary_key=True)

    brand = Column(String)
    name = Column(String)
    count = Column(Integer)
    item_size = Column(Integer)
    unit = Column(String)
    serving = Column(Integer)
    category = Column(String)
    subcategory = Column(String)
    expiration_date = Column(Date)
    purchase_date = Column(Date)
    created_at = Column(DateTime, default=datetime.now)
    deleted_at = Column(DateTime)

    inventory_id = Column(Integer, ForeignKey('inventory.id'))
    inventory = relationship('Inventory', primaryjoin="Item.inventory_id==Inventory.id")


class Inventory(Base):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True)

    name = Column(String, unique=True)
    viewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    deleted_at = Column(DateTime)

    items = relationship('Item', foreign_keys='Item.inventory_id')

    def __repr__(self):
        return f'<Inventory(id={self.id}, name={self.name}, deleted={self.deleted_at})>'
