"""Default field schemas and category lists for the inventory module.

An inventory's ``type`` only seeds its initial ``fields`` — afterwards the user owns the schema and may
add/remove/reorder/retype fields freely.  Quantity-field default units use mathjs-compatible names (e.g. ``lb``,
not ``pound``); all unit math happens in the frontend via mathjs.
"""
import re

# Supported field types.  The backend treats every value as an opaque string/number; only the frontend interprets
# `quantity` (magnitude + `<key>_unit`), `date`, `select` (enum `options`), `location`, and `calories` (a number of
# kcal-per-unit that the Summary's ration estimate detects by type).
FIELD_TYPES = ('text', 'number', 'quantity', 'date', 'select', 'location', 'calories')


def _field(key, label, type_, order, **kwargs):
    d = dict(key=key, label=label, type=type_, order=order)
    d.update({k: v for k, v in kwargs.items() if v is not None})
    return d


# Food storage categories (subcategory, category).  Used to seed the `category` select field's options and for
# category suggestions in the UI.
DEFAULT_FOOD_CATEGORIES = [
    ('salt', 'cooking ingredients'),
    ('dry milk', 'dairy'),
    ('evaporated milk', 'dairy'),
    ('freeze dried', 'dairy'),
    ('shortening', 'fats'),
    ('vegetable oil', 'fats'),
    ('canned', 'fruits'),
    ('dehydrated', 'fruits'),
    ('freeze-dried', 'fruits'),
    ('corn meal', 'grains'),
    ('flour', 'grains'),
    ('oats', 'grains'),
    ('pasta', 'grains'),
    ('rice', 'grains'),
    ('wheat', 'grains'),
    ('dry beans', 'legumes'),
    ('lentils', 'legumes'),
    ('canned', 'meats'),
    ('dried', 'meats'),
    ('freeze dried', 'meals'),
    ('brown sugar', 'sugars'),
    ('corn syrup', 'sugars'),
    ('honey', 'sugars'),
    ('juice mix', 'sugars'),
    ('white sugar', 'sugars'),
    ('canned', 'vegetables'),
    ('dehydrated', 'vegetables'),
    ('freeze dried', 'vegetables'),
    ('water', 'water'),
    ('bottled', 'water'),
    ('barrel', 'water'),
]

_FOOD_CATEGORY_OPTIONS = sorted({category for _, category in DEFAULT_FOOD_CATEGORIES})

DEFAULT_FIELD_SETS = {
    # `mobile=True` marks the columns shown in the condensed, read-only portrait-mobile view; the user can change
    # which fields are mobile in the field-schema editor.
    'food': [
        _field('brand', 'Brand', 'text', 0),
        _field('name', 'Name', 'text', 1, required=True, mobile=True),
        _field('category', 'Category', 'select', 2, options=_FOOD_CATEGORY_OPTIONS),
        _field('subcategory', 'Subcategory', 'text', 3, mobile=True),
        _field('item_size', 'Size', 'quantity', 4, unit='lb', mobile=True),
        _field('count', 'Count', 'number', 5, mobile=True),
        _field('calories', 'kcal per unit', 'calories', 6),
        _field('expiration_date', 'Expires', 'date', 7),
    ],
    'fuel': [
        _field('name', 'Name', 'text', 0, required=True, mobile=True),
        _field('fuel_type', 'Fuel Type', 'select', 1,
               options=['gasoline', 'diesel', 'propane', 'kerosene', 'oil'], mobile=True),
        _field('container', 'Container', 'text', 2),
        _field('item_size', 'Size', 'quantity', 3, unit='gallon', mobile=True),
        _field('count', 'Count', 'number', 4, mobile=True),
        _field('purchase_date', 'Purchased', 'date', 5),
        _field('location', 'Location', 'location', 6),
    ],
    'tool': [
        _field('name', 'Name', 'text', 0, required=True, mobile=True),
        _field('brand', 'Brand', 'text', 1),
        _field('category', 'Category', 'select', 2,
               options=['hand', 'power', 'garden', 'automotive', 'measuring', 'safety'], mobile=True),
        _field('count', 'Count', 'number', 3, mobile=True),
        _field('condition', 'Condition', 'select', 4, options=['new', 'good', 'worn', 'broken']),
        _field('location', 'Location', 'location', 5, mobile=True),
        _field('notes', 'Notes', 'text', 6),
    ],
}

# The first/default type used when a type is not specified (e.g. legacy migration).
DEFAULT_TYPE = 'food'

INVENTORY_TYPES = tuple(DEFAULT_FIELD_SETS.keys())

# A brand-new install seeds one example inventory of each kind so the feature is discoverable.
DEFAULT_INVENTORIES = [
    dict(name='Food Storage', type='food'),
]


def default_fields(inventory_type: str) -> list:
    """Return a fresh copy of the default field set for the given type (falls back to food)."""
    from copy import deepcopy
    return deepcopy(DEFAULT_FIELD_SETS.get(inventory_type, DEFAULT_FIELD_SETS[DEFAULT_TYPE]))


def slugify(name: str) -> str:
    """Convert an inventory name to a filesystem-safe slug used as its config file stem."""
    slug = re.sub(r'[^a-z0-9]+', '-', (name or '').strip().lower()).strip('-')
    return slug or 'inventory'
