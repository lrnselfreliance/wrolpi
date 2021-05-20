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

    def __repr__(self):
        return f'<Item(id={self.id}, name={self.name}, brand={self.brand}, inventory={self.inventory_id})>'


class Inventory(Base):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True)

    name = Column(String, unique=True)
    viewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    deleted_at = Column(DateTime)

    items = relationship('Item', foreign_keys='Item.inventory_id')

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
