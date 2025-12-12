"""
Code-defined default configuration for the Controller.

Controller starts with these defaults and loads overrides from
/media/wrolpi/config/controller.yaml after the drive is mounted.
"""

DEFAULT_CONFIG = {
    "port": 8087,
    "media_directory": "/media/wrolpi",

    "drives": {
        "supported_filesystems": ["ext4", "btrfs", "vfat", "exfat", "zfs"],
        "auto_mount": True,
        "mounts": [],  # Populated from controller.yaml after drive mount
        "zfs_pools": [],
    },

    "managed_services": [
        # WROLPi services
        {
            "name": "wrolpi-api",
            "systemd_name": "wrolpi-api",
            "port": 8081,
            "viewable": True,
            "view_path": "/docs",
            "description": "Python API (Sanic)",
        },
        {
            "name": "wrolpi-app",
            "systemd_name": "wrolpi-app",
            "port": 3000,
            "viewable": False,
            "description": "React frontend",
        },
        {
            "name": "wrolpi-help",
            "systemd_name": "wrolpi-help",
            "port": 8086,
            "viewable": True,
            "description": "Help documentation",
        },
        {
            "name": "wrolpi-kiwix",
            "systemd_name": "wrolpi-kiwix",
            "port": 8085,
            "viewable": True,
            "description": "Kiwix/Zim server",
        },
        # Map services
        {
            "name": "renderd",
            "systemd_name": "renderd",
            "port": None,
            "viewable": False,
            "description": "Map tile rendering daemon",
        },
        {
            "name": "apache2",
            "systemd_name": "apache2",
            "port": 8084,
            "viewable": True,
            "description": "Map tile web server",
        },
        # System services
        {
            "name": "postgresql",
            "systemd_name": "postgresql",
            "port": 5432,
            "viewable": False,
            "description": "PostgreSQL database",
        },
        {
            "name": "nginx",
            "systemd_name": "nginx",
            "port": 80,
            "viewable": True,
            "description": "Web proxy",
        },
    ],

    "hotspot": {
        "device": "wlan0",
        "ssid": "WROLPi",
        "password": "wrolpi hotspot",
    },

    "throttle": {
        "default_governor": "ondemand",
    },
}
