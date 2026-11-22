from dataclasses import dataclass, field
from typing import List

from wrolpi.common import ConfigFile, logger
from wrolpi.dates import now
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod

logger = logger.getChild(__name__)


# What a pin marks: a place, or a likely detonation site (a target, shown in the map's nuclear mode).
PIN_KINDS = ('pin', 'target')


def check_weapon(weapon: str = None, yield_kt: float = None, fission_fraction: float = None) -> dict:
    """A target's weapon, as it is kept: the key of a weapon the simulator offers (or "custom"), its
    yield (kt) when it is a yield of the user's own, and the share of the yield from fission."""
    fields = dict()
    if weapon is not None:
        if not isinstance(weapon, str) or not weapon.strip():
            raise ValueError('A weapon is named by its key')
        fields['weapon'] = weapon.strip()
    if yield_kt is not None:
        if not 0 < yield_kt <= 1e5:
            raise ValueError('A yield is more than 0 and at most 100,000 kt')
        fields['yield_kt'] = yield_kt
    if fission_fraction is not None:
        if not 0 < fission_fraction <= 1:
            raise ValueError('A fission share is more than 0 and at most 1')
        fields['fission_fraction'] = fission_fraction
    return fields


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

    def add_pin(self, lat: float, lon: float, label: str, color: str = 'red', kind: str = 'pin',
                weapon: str = None, yield_kt: float = None, fission_fraction: float = None) -> dict:
        if kind not in PIN_KINDS:
            raise ValueError(f'A pin is one of {", ".join(PIN_KINDS)}, not {kind!r}')
        weapon_fields = check_weapon(weapon, yield_kt, fission_fraction)
        if weapon_fields and kind != 'target':
            raise ValueError('Only a target has a weapon')
        pin = dict(
            id=self._next_pin_id(),
            lat=round(lat, 6),
            lon=round(lon, 6),
            label=label,
            color=color,
            created=str(now().date()),
        )
        # A pin without a kind is a plain pin, as every pin was before targets.
        if kind != 'pin':
            pin['kind'] = kind
        pin.update(weapon_fields)
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

    def update_pin(self, pin_id: int, label: str = None, color: str = None, weapon: str = None,
                   yield_kt: float = None, fission_fraction: float = None) -> bool:
        weapon_fields = check_weapon(weapon, yield_kt, fission_fraction)
        pins = self.pins
        for pin in pins:
            if pin.get('id') == pin_id:
                if weapon_fields and pin.get('kind') != 'target':
                    raise ValueError('Only a target has a weapon')
                if label is not None:
                    pin['label'] = label
                if color is not None:
                    pin['color'] = color
                if weapon is not None:
                    # A new weapon replaces the old one's yield and fission share.
                    for key in ('weapon', 'yield_kt', 'fission_fraction'):
                        pin.pop(key, None)
                pin.update(weapon_fields)
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
