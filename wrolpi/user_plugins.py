"""
This document contains all plugins that will be loaded and linked to in the navbar.  Add to the
plugins object below when adding a new plugin.
"""
from collections import OrderedDict

from wrolpi.plugins import videos

PLUGINS = OrderedDict(
    videos=videos,
)

# Share this list of plugins with every plugin
for plugin in PLUGINS.values():
    plugin.set_plugins(PLUGINS)
