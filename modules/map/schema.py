from dataclasses import dataclass
from typing import List


@dataclass
class ImportPost:
    files: List[str]
