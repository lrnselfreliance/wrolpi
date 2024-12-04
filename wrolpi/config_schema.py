from dataclasses import dataclass


@dataclass
class ConfigGetRequest:
    file_name: str = None


@dataclass
class ConfigPostRequest:
    file_name: str


@dataclass
class ConfigsRequest:
    file_name: str
    overwrite: bool = False


@dataclass
class ConfigUpdateRequest:
    config: dict
