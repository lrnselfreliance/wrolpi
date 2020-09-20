from decimal import Decimal
from itertools import zip_longest
from typing import List, Dict, Iterable

import psycopg2
import pytest
from dictorm import Table

from api.db import get_db_context
from api.test.common import wrap_test_db, ExtendedTestCase
from .. import init
from ..inventory import get_inventory_by_category, get_inventory_by_name, unit_registry, \
    compact_unit, human_units, get_inventory_by_subcategory, get_inventories, save_inventory, update_inventory, \
    delete_inventory

TEST_ITEMS_COLUMNS = (
    'inventory_id',
    'brand',
    'name',
    'item_size',
    'unit',
    'count',
    'category',
    'subcategory',
    'deleted_at',
    'serving',
    'expiration_date',
    'purchase_date',
)
TEST_ITEMS = [
    (1, 'Wheaters', 'Red Wheat', 45, 'pounds', 1, 'grains', 'wheat'),
    (1, 'Wheaters', 'Red Wheat', 55, 'pounds', 2, 'grains', 'wheat'),
    (1, 'Ricey', 'White Rice', 8, 'pounds', 1, 'grains', 'rice'),
    (1, 'Chewy', 'Chicken Breast', 16, 'oz', 8, 'meats', 'canned'),
    (1, 'Chewy', 'Beef', 16, 'oz', 12, 'meats', 'canned'),
    (1, 'Vibrant', 'Peaches', 24, 'oz', 2, 'fruits', 'canned'),
    (1, 'Vibrant', 'Pineapple', Decimal('22.3'), 'oz', 1, 'fruits', 'canned'),
    # This item is deleted, and should always be ignored.
    (1, 'deleted', 'deleted', Decimal('1'), 'oz', 1, 'fruits', 'canned', '2020-01-01'),
]
TEST_ITEMS = [dict(zip(TEST_ITEMS_COLUMNS, i)) for i in TEST_ITEMS]


def extract_items(lst: List[Dict], keys: Iterable[str]) -> List[Dict]:
    extracted = []
    for i in lst:
        extracted.append({j: i.pop(j) for j in keys})

    return extracted


class TestInventory(ExtendedTestCase):

    @staticmethod
    def prepare() -> None:
        init(force=True)

        with get_db_context(commit=True) as (db_conn, db):
            Item: Table = db['item']
            for item in TEST_ITEMS:
                Item(item).flush()

    @wrap_test_db
    def test_get_inventories(self):
        self.prepare()

        inventories = get_inventories()
        dates = extract_items(inventories, {'created_at', 'deleted_at', 'viewed_at', 'items'})
        self.assertItemsTruthyOrFalsey(dates, [{'created_at': True, 'deleted_at': False, 'viewed_at': False}])
        self.assertEqual(inventories, [{'id': 1, 'name': 'Food Storage'}])

    @wrap_test_db
    def test_inventory(self):
        self.prepare()

        # Insert a new Inventory.
        inventory = {
            'name': 'New Inventory',
            'viewed_at': 'asdf',  # This should be ignored.
        }
        save_inventory(inventory)

        with get_db_context() as (db_conn, db):
            Inventory: Table = db['inventory']
            i1, i2 = Inventory.get_where().order_by('name')
            self.assertDictContains(i2, {'name': 'New Inventory', 'viewed_at': None})

        # Inventories cannot share a name.
        with get_db_context() as (db_conn, db):
            with db.transaction():
                self.assertRaises(psycopg2.errors.UniqueViolation, save_inventory, inventory)

        # Insert a second inventory.
        inventory['name'] = 'Super Inventory'
        save_inventory(inventory)

        # Cannot update the name to a name that is already used.
        with get_db_context() as (db_conn, db):
            Inventory: Table = db['inventory']
            i = Inventory.get_one(name='Super Inventory')
            inventory['name'] = 'New Inventory'
            self.assertRaises(psycopg2.errors.UniqueViolation, update_inventory, i['id'], inventory)

        # Add some items to "New Inventory"
        with get_db_context(commit=True) as (db_conn, db):
            Item: Table = db['item']
            before_item_count = Item.count()
            Item(inventory_id=2, brand='Wheaters', name='Red Wheat', item_size=45, unit='pounds', count=1).flush()
            Item(inventory_id=2, brand='Wheaters', name='Red Wheat', item_size=45, unit='pounds', count=1).flush()
            Item(inventory_id=2, brand='Wheaters', name='Red Wheat', item_size=45, unit='pounds', count=1).flush()
            Item(inventory_id=2, brand='Wheaters', name='Red Wheat', item_size=45, unit='pounds', count=1).flush()

        # You can rename a inventory to a conflicting name, if the other inventory is marked as deleted.
        with get_db_context(commit=True) as (db_conn, db):
            delete_inventory(2)
            # Check that the items from the deleted Inventory were not deleted, YET.
            Item: Table = db['item']
            self.assertEqual(before_item_count + 4, Item.count())

        with get_db_context() as (db_conn, db):
            Inventory: Table = db['inventory']
            i = Inventory.get_one(name='Super Inventory')
            inventory['name'] = 'New Inventory'
            update_inventory(i['id'], inventory)

            # Check that the items from the deleted Inventory were really deleted.
            Item: Table = db['item']
            self.assertEqual(before_item_count, Item.count())

    @wrap_test_db
    def test_get_inventory_by_category(self):
        self.prepare()

        summary = get_inventory_by_category(1)

        self.assertEqual(
            summary,
            [
                dict(category='fruits', total_size=Decimal('70.3'), unit='oz'),
                dict(category='grains', total_size=Decimal('163'), unit='pounds'),
                dict(category='meats', total_size=Decimal('320'), unit='oz'),
            ])

    @wrap_test_db
    def test_get_inventory_by_subcategory(self):
        self.prepare()

        summary = get_inventory_by_subcategory(1)

        self.assertEqual(
            summary,
            [
                dict(category='fruits', subcategory='canned', total_size=Decimal('70.3'), unit='oz'),
                dict(category='grains', subcategory='rice', total_size=Decimal('8'), unit='pounds'),
                dict(category='grains', subcategory='wheat', total_size=Decimal('155'), unit='pounds'),
                dict(category='meats', subcategory='canned', total_size=Decimal('320'), unit='oz'),
            ])

    @wrap_test_db
    def test_get_inventory_by_name(self):
        self.prepare()

        expected = [
            dict(brand='Chewy', name='Beef', total_size=Decimal('192'), unit='oz'),
            dict(brand='Chewy', name='Chicken Breast', total_size=Decimal('128'), unit='oz'),
            dict(brand='Ricey', name='White Rice', total_size=Decimal('8'), unit='pounds'),
            dict(brand='Vibrant', name='Peaches', total_size=Decimal('48'), unit='oz'),
            dict(brand='Vibrant', name='Pineapple', total_size=Decimal('22.3'), unit='oz'),
            dict(brand='Wheaters', name='Red Wheat', total_size=Decimal('155'), unit='pounds'),
        ]

        inventory = get_inventory_by_name(1)

        for idx, (i, j) in enumerate(zip_longest(inventory, expected)):
            self.assertEqual(i, j, f'named inventory {idx} is not equal')


@pytest.mark.parametrize(
    'quantity,expected',
    [
        (Decimal(5) * unit_registry.ounce, unit_registry.ounce * 5),
        (Decimal(16) * unit_registry.ounce, unit_registry.pound * 1),
        (Decimal(500) * unit_registry.pound, unit_registry.pound * 500),
        (Decimal(2000) * unit_registry.pound, unit_registry.ton * 1),
        (Decimal(128000) * unit_registry.ounce, unit_registry.ton * 4),
    ]
)
def test_compact_unit(quantity, expected):
    # Round the result so we don't have to specify all those zeros for the test definition.
    assert round(compact_unit(quantity), 5) == expected


@pytest.mark.parametrize(
    'items,expected',
    [
        (
                [{'total_size': Decimal('0'), 'unit': 'oz'}],
                [{'total_size': Decimal('0'), 'unit': 'oz'}],
        ),
        (
                [{'total_size': Decimal('-500'), 'unit': 'oz'}],
                [{'total_size': Decimal('-500'), 'unit': 'oz'}],
        ),
        (
                [{'total_size': Decimal('1'), 'unit': 'oz'}],
                [{'total_size': Decimal('1'), 'unit': 'oz'}],
        ),
        (
                [{'total_size': Decimal('16'), 'unit': 'oz'}],
                [{'total_size': Decimal('1'), 'unit': 'pound'}],
        ),
        (
                [{'total_size': Decimal('16'), 'unit': 'oz'}, {'total_size': Decimal('5000'), 'unit': 'lb'}],
                [{'total_size': Decimal('1'), 'unit': 'pound'}, {'total_size': Decimal('2.5'), 'unit': 'ton'}],
        ),
    ]
)
def test_human_units(items, expected):
    assert human_units(items, 'total_size') == expected
