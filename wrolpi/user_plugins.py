"""
This module contains all plugins that will be loaded and linked to in the navbar.  Add to the
plugins object below when adding a new plugin.

You can uncomment the "example_plugin" lines below to explore building your own plugin!
"""
from collections import OrderedDict

from wrolpi.plugins import videos

# from wrolpi.plugins import example_plugin

PLUGINS = OrderedDict(
    videos=videos,
    # example_plugin=example_plugin,
)

# Share this list of plugins with every plugin
for plugin in PLUGINS.values():
    plugin.set_plugins(PLUGINS)
