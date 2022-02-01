from dataclasses import dataclass, field
from typing import List


@dataclass
class FilesRequest:
    directories: List[str] = field(default_factory=list)


@dataclass
class DeleteRequest:
    file: str
