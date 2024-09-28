from sqlalchemy import Column, Integer, String, Date, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm.collections import InstrumentedList

from wrolpi.common import Base, ModelHelper
from wrolpi.dates import now, TZDateTime


class Item(Base, ModelHelper):
    __tablename__ = 'item'
    id = Column(Integer, primary_key=True)

    brand = Column(String)
    category = Column(String)
    count = Column(DECIMAL)
    created_at = Column(TZDateTime, default=now)
    deleted_at = Column(TZDateTime)
    expiration_date = Column(Date)
    item_size = Column(DECIMAL)
    name = Column(String)
    purchase_date = Column(Date)
    serving = Column(Integer)
    subcategory = Column(String)
    unit = Column(String)

    inventory_id = Column(Integer, ForeignKey('inventory.id'))
    inventory = relationship('Inventory', primaryjoin="Item.inventory_id==Inventory.id", back_populates='items')

    def __repr__(self):
        return f'<Item id={self.id}, name={self.name}, brand={self.brand}, ' \
               f'count={self.count}, item_size={self.item_size}, unit={self.unit}, inventory={self.inventory_id} >'


class Inventory(Base, ModelHelper):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True)

    name = Column(String, unique=True)
    viewed_at = Column(TZDateTime)
    created_at = Column(TZDateTime, default=now)
    deleted_at = Column(TZDateTime)

    items: InstrumentedList = relationship('Item', foreign_keys='Item.inventory_id')

    def __repr__(self):
        return f'<Inventory id={self.id}, name={self.name!r}, deleted={self.deleted_at} >'

    def dict(self):
        d = super().dict()
        d['items'] = [i.dict() for i in self.items]
        return d

    def delete(self):
        """
        Delete all Items of this Inventory.  Then delete this inventory.
        """
        self.deleted_at = now()

    @staticmethod
    def find_by_name(session: Session, name: str) -> 'Inventory':
        return session.query(Inventory).filter_by(name=name).one()


class InventoriesVersion(Base, ModelHelper):
    __tablename__ = 'inventories_version'
    version = Column(Integer, primary_key=True)
