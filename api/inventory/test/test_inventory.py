import tempfile
from decimal import Decimal
from itertools import zip_longest
from typing import List, Iterable

import pytest
import sqlalchemy
from pint import Quantity

from api.db import get_db_context, Base
from api.test.common import wrap_test_db, ExtendedTestCase
from .. import init
from ..common import sum_by_key, get_inventory_by_category, get_inventory_by_subcategory, get_inventory_by_name, \
    compact_unit, cleanup_quantity, save_inventories_file, import_inventories_file
from ..inventory import unit_registry, \
    get_inventories, save_inventory, update_inventory, \
    delete_inventory, get_categories
from ..models import Item, Inventory

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
    (1, 'Wheaters', 'Red Wheat', 500, 'oz', 1, 'grains', 'wheat'),
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


def extract_items(lst: List[Base], keys: Iterable[str]) -> List[Base]:
    extracted = []
    for i in lst:
        extracted.append({j: getattr(i, j) for j in keys})

    return extracted


class TestInventory(ExtendedTestCase):

    @staticmethod
    def prepare() -> None:
        init(force=True)

        with get_db_context(commit=True) as (engine, session):
            for item in TEST_ITEMS:
                item = Item(**item)
                session.add(item)

    @wrap_test_db
    def test_get_categories(self):
        self.prepare()

        categories = get_categories()
        self.assertGreater(len(categories), 0)

    @wrap_test_db
    def test_get_inventories(self):
        self.prepare()

        inventories = get_inventories()
        dates = extract_items(inventories, {'created_at', 'deleted_at', 'viewed_at'})
        self.assertItemsTruthyOrFalsey(dates, [{'created_at': True, 'deleted_at': False, 'viewed_at': False}])
        self.assertEqual(inventories[0].id, 1)
        self.assertEqual(inventories[0].name, 'Food Storage')

    @wrap_test_db
    def test_inventory1(self):
        self.prepare()

        # Insert a new Inventory.
        inventory = {
            'name': 'New Inventory',
            'viewed_at': 'asdf',  # This should be ignored.
        }
        save_inventory(inventory)

        with get_db_context() as (engine, session):
            i1, i2 = session.query(Inventory).order_by(Inventory.name).all()
            self.assertDictContains(i2, {'name': 'New Inventory', 'viewed_at': None})

        # Inventories cannot share a name.
        self.assertRaises(sqlalchemy.exc.IntegrityError, save_inventory, inventory)

        # Insert a second inventory.
        inventory['name'] = 'Super Inventory'
        save_inventory(inventory)

        # Cannot update the name to a name that is already used.
        with get_db_context() as (engine, session):
            i = Inventory.get_one(name='Super Inventory')
            inventory['name'] = 'New Inventory'
            self.assertRaises(sqlalchemy.exc.IntegrityError, update_inventory, i['id'], inventory)

        # Add some items to "New Inventory"
        with get_db_context(commit=True) as (engine, session):
            before_item_count = Item.count()
            Item(inventory_id=2, brand='a', name='b', item_size=45, unit='pounds', count=1).flush()
            Item(inventory_id=2, brand='a', name='b', item_size=45, unit='pounds', count=1).flush()
            Item(inventory_id=2, brand='a', name='b', item_size=45, unit='pounds', count=1).flush()
            Item(inventory_id=2, brand='a', name='b', item_size=45, unit='pounds', count=1).flush()

        # You can rename a inventory to a conflicting name, if the other inventory is marked as deleted.
        with get_db_context(commit=True) as (engine, session):
            delete_inventory(2)
            # Check that the items from the deleted Inventory were not deleted, YET.
            self.assertEqual(before_item_count + 4, Item.count())

            i = Inventory.get_one(name='Super Inventory')
            inventory['name'] = 'New Inventory'
            update_inventory(i['id'], inventory)

            # Check that the items from the deleted Inventory were really deleted.
            self.assertEqual(before_item_count, Item.count())

    @wrap_test_db
    def test_get_inventory_by_category(self):
        self.prepare()

        expected = [
            dict(category='fruits', total_size=Decimal('4.375'), unit='pound'),
            dict(category='grains', total_size=Decimal('149.25'), unit='pound'),
            dict(category='meats', total_size=Decimal('20'), unit='pound'),
        ]

        inventory = get_inventory_by_category(1)

        for idx, (i, j) in enumerate(zip_longest(inventory, expected)):
            self.assertEqual(i, j, f'category inventory {idx} is not equal')

    @wrap_test_db
    def test_get_inventory_by_subcategory(self):
        self.prepare()

        expected = [
            dict(category='fruits', subcategory='canned', total_size=Decimal('4.375'), unit='pound'),
            dict(category='grains', subcategory='rice', total_size=Decimal('8'), unit='pound'),
            dict(category='grains', subcategory='wheat', total_size=Decimal('141.25'), unit='pound'),
            dict(category='meats', subcategory='canned', total_size=Decimal('20'), unit='pound'),
        ]

        inventory = get_inventory_by_subcategory(1)

        for idx, (i, j) in enumerate(zip_longest(inventory, expected)):
            self.assertEqual(i, j, f'subcategory inventory {idx} is not equal')

    @wrap_test_db
    def test_get_inventory_by_name(self):
        self.prepare()

        expected = [
            dict(brand='Chewy', name='Beef', total_size=Decimal('12'), unit='pound'),
            dict(brand='Chewy', name='Chicken Breast', total_size=Decimal('8'), unit='pound'),
            dict(brand='Ricey', name='White Rice', total_size=Decimal('8'), unit='pound'),
            dict(brand='Vibrant', name='Peaches', total_size=Decimal('3'), unit='pound'),
            dict(brand='Vibrant', name='Pineapple', total_size=Decimal('1.375'), unit='pound'),
            dict(brand='Wheaters', name='Red Wheat', total_size=Decimal('141.25'), unit='pound'),
        ]

        inventory = get_inventory_by_name(1)

        for idx, (i, j) in enumerate(zip_longest(inventory, expected)):
            self.assertEqual(i, j, f'named inventory {idx} is not equal')

    @wrap_test_db
    def test_inventories_file(self):
        self.prepare()

        with tempfile.NamedTemporaryFile() as tf:
            # Can't import an empty file.
            self.assertRaises(ValueError, import_inventories_file, tf.name)

            save_inventories_file(tf.name)

            # Clear out the DB so the import will be tested
            with get_db_context(commit=True) as (engine, session):
                curs = db_conn.cursor()
                curs.execute('DELETE FROM item')
                curs.execute('DELETE FROM inventory')

            import_inventories_file(tf.name)

        inventories = get_inventories()
        self.assertEqual(len(inventories), 1)
        # ID has increased because we did not reset the sequence when deleting from the table.
        self.assertDictContains(inventories[0], {'id': 2, 'name': 'Food Storage'})

        # All items in the DB match those in the test list, except for the "deleted" item.
        self.assertEqual(len(inventories[0]['items']), len(TEST_ITEMS) - 1)
        test_items = {(i['name'], i['brand'], i['count']) for i in TEST_ITEMS}
        test_items.remove(('deleted', 'deleted', 1))
        db_items = {(i['name'], i['brand'], i['count']) for i in inventories[0]['items']}
        self.assertEqual(test_items, db_items)


def quantity_to_string(quantity: Quantity) -> str:
    quantity = cleanup_quantity(quantity)
    num, (units,) = quantity.to_tuple()
    (unit, _) = units
    return f'{num} {unit}'


@pytest.mark.parametrize(
    'quantity,expected',
    [
        (Decimal(5) * unit_registry.ounce, '5 ounce'),
        (Decimal(16) * unit_registry.ounce, '1 pound'),
        (Decimal(500) * unit_registry.pound, '500 pound'),
        (Decimal(2000) * unit_registry.pound, '1 ton'),
        (Decimal(128000) * unit_registry.ounce, '4 ton'),
    ]
)
def test_compact_unit(quantity, expected):
    # Round the result so we don't have to specify all those zeros for the test definition.
    assert quantity_to_string(compact_unit(quantity)) == expected


pound, oz, gram, gallon = unit_registry('pound'), unit_registry('oz'), unit_registry('gram'), unit_registry('gallon')
pound, oz, gram, gallon = pound.units, oz.units, gram.units, gallon.units
mass = pound.dimensionality
length = gallon.dimensionality


@pytest.mark.parametrize(
    'items,expected',
    [
        (
                # No conversion is necessary.
                [{'category': 'grains', 'count': Decimal('1'), 'item_size': Decimal('1'), 'unit': 'oz'}],
                {('grains',): Decimal('1') * oz},
        ),
        (
                # The larger of the units is what is returned.
                [
                    {'category': 'grains', 'count': Decimal('1'), 'item_size': Decimal('1'), 'unit': 'oz'},
                    {'category': 'grains', 'count': Decimal('1'), 'item_size': Decimal('1'), 'unit': 'lbs'},
                ],
                {('grains',): Decimal('1.0625') * pound},
        ),
        (
                # Items are summed by category.
                [
                    {'category': 'grains', 'count': Decimal('8'), 'item_size': Decimal('24'), 'unit': 'oz'},
                    {'category': 'grains', 'count': Decimal('2'), 'item_size': Decimal('45'), 'unit': 'lbs'},
                    {'category': 'fruits', 'count': Decimal('4'), 'item_size': Decimal('1'), 'unit': 'gram'},
                ],
                {
                    ('grains',): Decimal('102') * pound,
                    ('fruits',): Decimal('4') * gram,
                },
        ),
        (
                [
                    {'category': 'cooking ingredients', 'count': Decimal('1'), 'item_size': Decimal('1'),
                     'unit': 'gallon'},
                    {'category': 'cooking ingredients', 'count': Decimal('1'), 'item_size': Decimal('1'),
                     'unit': 'quart'},
                    {'category': 'cooking ingredients', 'count': Decimal('1'), 'item_size': Decimal('1'), 'unit': 'oz'},
                ],
                {
                    ('cooking ingredients',): Decimal('1.25') * gallon,
                    ('cooking ingredients',): Decimal('1') * oz,
                },
        ),
    ]
)
def test_sum_by_key(items, expected):
    assert sum_by_key(items, lambda i: (i['category'],)) == expected
