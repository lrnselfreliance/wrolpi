from dataclasses import dataclass, field
from typing import List

from wrolpi.common import ConfigFile, logger
from wrolpi.dates import now
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod

logger = logger.getChild(__name__)


@dataclass
class MapPinsConfigValidator:
    version: int = None
    pins: list = field(default_factory=list)


class MapPinsConfig(ConfigFile):
    file_name = 'map_pins.yaml'
    default_config = dict(
        version=0,
        pins=[],
    )
    validator = MapPinsConfigValidator

    def import_config(self, file=None, send_events=False):
        super().import_config(file, send_events)
        self.successful_import = True

    @property
    def pins(self) -> List[dict]:
        return list(self._config.get('pins', []))

    @pins.setter
    def pins(self, value: List[dict]):
        self.update({'pins': value})

    def _next_pin_id(self) -> int:
        """Return the next available pin ID (max existing ID + 1)."""
        pins = self.pins
        if not pins:
            return 1
        return max(p.get('id', 0) for p in pins) + 1

    def add_pin(self, lat: float, lon: float, label: str, color: str = 'red') -> dict:
        pin = dict(
            id=self._next_pin_id(),
            lat=round(lat, 6),
            lon=round(lon, 6),
            label=label,
            color=color,
            created=str(now().date()),
        )
        pins = self.pins
        pins.append(pin)
        self.pins = pins
        save_map_pins_config.activate_switch()
        return pin

    def delete_pin(self, pin_id: int) -> bool:
        pins = self.pins
        new_pins = [p for p in pins if p.get('id') != pin_id]
        if len(new_pins) == len(pins):
            return False
        self.pins = new_pins
        save_map_pins_config.activate_switch()
        return True

    def update_pin(self, pin_id: int, label: str = None, color: str = None) -> bool:
        pins = self.pins
        for pin in pins:
            if pin.get('id') == pin_id:
                if label is not None:
                    pin['label'] = label
                if color is not None:
                    pin['color'] = color
                self.pins = pins
                save_map_pins_config.activate_switch()
                return True
        return False


MAP_PINS_CONFIG: MapPinsConfig = MapPinsConfig()

# Test override.
TEST_MAP_PINS_CONFIG = None


def get_map_pins_config() -> MapPinsConfig:
    global TEST_MAP_PINS_CONFIG
    if isinstance(TEST_MAP_PINS_CONFIG, ConfigFile):
        return TEST_MAP_PINS_CONFIG
    return MAP_PINS_CONFIG


@register_switch_handler('save_map_pins_config')
def save_map_pins_config():
    get_map_pins_config().save()


save_map_pins_config: ActivateSwitchMethod
