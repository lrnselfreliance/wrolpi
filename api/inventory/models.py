from sqlalchemy import Column, Integer, String, DateTime, Date, func

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
    created_at = Column(DateTime)
    deleted_at = Column(DateTime)

    inventory_id = Column(Integer)


class Inventory(Base):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True)

    name = Column(String)
    viewed_at = Column(DateTime)
    created_at = Column(DateTime)
    deleted_at = Column(DateTime)
