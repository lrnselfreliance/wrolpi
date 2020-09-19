from pathlib import Path

MY_DIR: Path = Path(__file__).parent

DEFAULT_CATEGORIES = [
    ('wheat', 'grains'),
    ('rice', 'grains'),
    ('flour', 'grains'),
    ('oats', 'grains'),
    ('pasta', 'grains'),
    ('corn meal', 'grains'),
    ('canned', 'meats'),
    ('dried', 'meats'),
    ('vegetable oil', 'fats'),
    ('shortening', 'fats'),
    ('dry beans', 'legumes'),
    ('lentils', 'legumes'),
    ('dry milk', 'dairy'),
    ('evaporated milk', 'dairy'),
    ('white sugar', 'sugars'),
    ('brown sugar', 'sugars'),
    ('honey', 'sugars'),
    ('corn syrup', 'sugars'),
    ('juice mix', 'sugars'),
    ('salt', 'cooking ingredients'),
    ('canned', 'fruits'),
    ('dehydrated', 'fruits'),
    ('freeze-dried', 'fruits'),
    ('canned', 'vegetables'),
    ('dehydrated', 'vegetables'),
    ('freeze-dried', 'vegetables'),
    ('water', 'water'),
]

DEFAULT_INVENTORIES = [
    'Food Storage',
]
