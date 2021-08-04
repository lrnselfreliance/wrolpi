from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.orm.collections import InstrumentedList

from api.common import Base, ModelHelper


class Item(Base, ModelHelper):
    __tablename__ = 'item'
    id = Column(Integer, primary_key=True)

    brand = Column(String)
    category = Column(String)
    count = Column(DECIMAL)
    created_at = Column(DateTime, default=datetime.now)
    deleted_at = Column(DateTime)
    expiration_date = Column(Date)
    item_size = Column(DECIMAL)
    name = Column(String)
    purchase_date = Column(Date)
    serving = Column(Integer)
    subcategory = Column(String)
    unit = Column(String)

    inventory_id = Column(Integer, ForeignKey('inventory.id'))
    inventory = relationship('Inventory', primaryjoin="Item.inventory_id==Inventory.id")

    def __repr__(self):
        return f'<Item(id={self.id}, name={self.name}, brand={self.brand}, ' \
               f'count={self.count}, item_size={self.item_size}, unit={self.unit}, inventory={self.inventory_id})>'


class Inventory(Base, ModelHelper):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True)

    name = Column(String, unique=True)
    viewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    deleted_at = Column(DateTime)

    items: InstrumentedList = relationship('Item', foreign_keys='Item.inventory_id')

    def __repr__(self):
        return f'<Inventory(id={self.id}, name={self.name!r}, deleted={self.deleted_at})>'

    def dict(self):
        d = super().dict()
        d['items'] = [i.dict() for i in self.items]
        return d


class InventoriesVersion(Base, ModelHelper):
    __tablename__ = 'inventory_version'
    version = Column(Integer, primary_key=True)
