import unittest
from decimal import Decimal
from itertools import zip_longest

from dictorm import Table

from api.db import get_db_context
from api.test.common import wrap_test_db
from ..inventory import init_categories, get_inventory_by_category, get_inventory_by_name

TEST_ITEMS_COLUMNS = (
    'brand',
    'name',
    'item_size',
    'unit',
    'count',
    'category',
    'subcategory',
    'serving',
    'expiration_date',
    'purchase_date',
)
TEST_ITEMS = [
    ('Wheaters', 'Red Wheat', 45, 'pounds', 1, 'grains', 'wheat'),
    ('Wheaters', 'Red Wheat', 55, 'pounds', 2, 'grains', 'wheat'),
    ('Ricey', 'White Rice', 8, 'pounds', 1, 'grains', 'rice'),
    ('Chewy', 'Chicken Breast', 16, 'oz', 8, 'meats', 'canned'),
    ('Chewy', 'Beef', 16, 'oz', 12, 'meats', 'canned'),
    ('Vibrant', 'Peaches', 24, 'oz', 2, 'fruits', 'canned'),
    ('Vibrant', 'Pineapple', Decimal('22.3'), 'oz', 1, 'fruits', 'canned'),
]


class TestInventory(unittest.TestCase):

    @staticmethod
    def prepare() -> None:
        init_categories(force=True)

        items = [dict(zip(TEST_ITEMS_COLUMNS, i)) for i in TEST_ITEMS]
        with get_db_context(commit=True) as (db_conn, db):
            Item: Table = db['item']
            for item in items:
                Item(**item).flush()

    @wrap_test_db
    def test_get_inventory_by_category(self):
        self.prepare()

        summary = get_inventory_by_category()

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

        inventory = get_inventory_by_name()

        for i, j in zip_longest(inventory, expected):
            self.assertEqual(i, j)
