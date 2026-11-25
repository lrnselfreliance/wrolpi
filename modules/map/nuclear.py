"""The map's nuclear targets: likely detonation sites, simulated in the map's nuclear mode.  Kept apart
from the pins, in their own config."""
from dataclasses import dataclass, field
from typing import List

from wrolpi.common import ConfigFile, logger
from wrolpi.dates import now
from wrolpi.switches import register_switch_handler, ActivateSwitchMethod

logger = logger.getChild(__name__)


class TargetsChanged(ValueError):
    """The saved targets are not the ones the user started from."""


def check_weapon(weapon: str = None, yield_kt: float = None, fission_fraction: float = None) -> dict:
    """A target's weapon, as it is kept: the key of a weapon the simulator offers (or "custom"), its
    yield (kt) when it is a yield of the user's own, and the share of the yield from fission."""
    fields = dict()
    if weapon is not None:
        if not isinstance(weapon, str) or not weapon.strip():
            raise ValueError('A weapon is named by its key')
        fields['weapon'] = weapon.strip()
    if yield_kt is not None:
        if not isinstance(yield_kt, (int, float)) or not 0 < yield_kt <= 1e5:
            raise ValueError('A yield is more than 0 and at most 100,000 kt')
        fields['yield_kt'] = yield_kt
    if fission_fraction is not None:
        if not isinstance(fission_fraction, (int, float)) or not 0 < fission_fraction <= 1:
            raise ValueError('A fission share is more than 0 and at most 1')
        fields['fission_fraction'] = fission_fraction
    return fields


@dataclass
class MapNuclearConfigValidator:
    version: int = None
    targets: list = field(default_factory=list)


class MapNuclearConfig(ConfigFile):
    file_name = 'map_nuclear.yaml'
    default_config = dict(
        version=0,
        targets=[],
    )
    validator = MapNuclearConfigValidator

    @property
    def targets(self) -> List[dict]:
        return list(self._config.get('targets', []))

    @targets.setter
    def targets(self, value: List[dict]):
        self.update({'targets': value})

    def replace_targets(self, targets: List[dict], loaded_ids: List[int]) -> List[dict]:
        """Make `targets` the saved targets, in one change of the config.

        Each target is {lat, lon, label, weapon?, yield_kt?, fission_fraction?, id?}: a target with
        the id of a saved target keeps that target's id and date, the others are new.  `loaded_ids`
        are the ids of the saved targets the user started from: if the saved targets are not those
        (they were not loaded, or have changed since), nothing is saved, so none are lost unseen.
        Returns the saved targets."""
        saved = {t['id']: t for t in self.targets}
        if set(saved) != set(loaded_ids):
            raise TargetsChanged('The saved targets are not the ones loaded: load them again, then save')
        next_id = max(saved, default=0) + 1
        kept = []
        for target in targets:
            label = str(target.get('label') or '').strip()
            if not label:
                raise ValueError('Every target has a name')
            lat, lon = target.get('lat'), target.get('lon')
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) \
                    or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError(f'{label} is not at a latitude and longitude')
            weapon_fields = check_weapon(target.get('weapon'), target.get('yield_kt'), target.get('fission_fraction'))
            old = saved.get(target.get('id'))
            if old:
                target_id, created = old['id'], old.get('created')
            else:
                target_id, created = next_id, str(now().date())
                next_id += 1
            kept.append(dict(id=target_id, lat=round(lat, 6), lon=round(lon, 6), label=label, created=created,
                             **weapon_fields))
        if len({t['id'] for t in kept}) != len(kept):
            raise ValueError('A saved target is given more than once')
        self.targets = kept
        save_map_nuclear_config.activate_switch()
        return kept

    def delete_target(self, target_id: int) -> bool:
        targets = self.targets
        kept = [t for t in targets if t.get('id') != target_id]
        if len(kept) == len(targets):
            return False
        self.targets = kept
        save_map_nuclear_config.activate_switch()
        return True


MAP_NUCLEAR_CONFIG: MapNuclearConfig = MapNuclearConfig()

# Test override.
TEST_MAP_NUCLEAR_CONFIG = None


def get_map_nuclear_config() -> MapNuclearConfig:
    global TEST_MAP_NUCLEAR_CONFIG
    if isinstance(TEST_MAP_NUCLEAR_CONFIG, ConfigFile):
        return TEST_MAP_NUCLEAR_CONFIG
    return MAP_NUCLEAR_CONFIG


@register_switch_handler('save_map_nuclear_config')
def save_map_nuclear_config():
    get_map_nuclear_config().save()


save_map_nuclear_config: ActivateSwitchMethod
