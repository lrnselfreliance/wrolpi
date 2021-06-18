from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.orm.collections import InstrumentedList

from api.common import Base


class Item(Base):
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

    def dict(self):
        d = dict(
            id=self.id,
            brand=self.brand,
            category=self.category,
            count=self.count,
            created_at=self.created_at,
            deleted_at=self.deleted_at,
            expiration_date=self.expiration_date,
            inventory_id=self.inventory_id,
            item_size=self.item_size,
            name=self.name,
            purchase_date=self.purchase_date,
            serving=self.serving,
            subcategory=self.subcategory,
            unit=self.unit,
        )
        return d


class Inventory(Base):
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
        # TODO surely there is a better way to do this?
        d = dict(
            id=self.id,
            name=self.name,
            viewed_at=self.viewed_at,
            created_at=self.created_at,
            deleted_at=self.deleted_at,
            items=[i.dict() for i in self.items]
        )
        return d
