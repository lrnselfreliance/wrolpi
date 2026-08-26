"""The ai.yaml config — the source of truth for the AI assistant's state.

AI is opt-in: nothing is downloaded and llama-server does not run until the user enables it on
the Manage tab.  YAML-only (no database)."""
import contextlib
from dataclasses import dataclass
from typing import Optional

from wrolpi.common import ConfigFile


@dataclass
class AIConfigValidator:
    version: int = None
    enabled: bool = None
    active_model: str = None
    idle_unload_minutes: int = None
    context_size: Optional[int] = None
    max_tool_calls: int = None


class AIConfig(ConfigFile):
    file_name = 'ai.yaml'
    default_config = dict(
        version=0,
        enabled=False,
        active_model='',  # a GGUF file name in <media>/ai/models/
        idle_unload_minutes=15,
        context_size=None,  # None uses the active model's default from the catalog.
        max_tool_calls=6,
    )
    validator = AIConfigValidator

    def import_config(self, file=None, send_events=False):
        super().import_config(file, send_events)
        # YAML-only config (no database); a successful read is a successful import.
        self.successful_import = True

    @property
    def enabled(self) -> bool:
        return self._config['enabled']

    @enabled.setter
    def enabled(self, value: bool):
        self.update({'enabled': bool(value)})

    @property
    def active_model(self) -> str:
        return self._config['active_model']

    @active_model.setter
    def active_model(self, value: str):
        self.update({'active_model': value or ''})

    @property
    def idle_unload_minutes(self) -> int:
        return self._config['idle_unload_minutes']

    @idle_unload_minutes.setter
    def idle_unload_minutes(self, value: int):
        self.update({'idle_unload_minutes': int(value)})

    @property
    def context_size(self) -> Optional[int]:
        return self._config['context_size']

    @context_size.setter
    def context_size(self, value: Optional[int]):
        self.update({'context_size': int(value) if value else None})

    @property
    def max_tool_calls(self) -> int:
        return self._config['max_tool_calls']

    @max_tool_calls.setter
    def max_tool_calls(self, value: int):
        self.update({'max_tool_calls': int(value)})


AI_CONFIG: AIConfig = AIConfig()

# Test override (see get_ai_config).
TEST_AI_CONFIG: Optional[AIConfig] = None


def get_ai_config() -> AIConfig:
    global TEST_AI_CONFIG
    if isinstance(TEST_AI_CONFIG, ConfigFile):
        return TEST_AI_CONFIG
    return AI_CONFIG


@contextlib.contextmanager
def ai_config_context():
    """Used to create a test config."""
    global TEST_AI_CONFIG
    TEST_AI_CONFIG = AIConfig()
    try:
        yield TEST_AI_CONFIG
    finally:
        TEST_AI_CONFIG = None
