from collections import OrderedDict

from . import inventory
from . import map
from . import videos

MODULES = OrderedDict([
    (videos.main.PRETTY_NAME, videos),
    (map.PRETTY_NAME, map),
    (inventory.PRETTY_NAME, inventory)
])
