import pathlib
from typing import Union, List, Generator, Optional

# pathlib typing
PATH_OR_STR = Union[pathlib.Path, str]
LIST_OF_PATHS = List[pathlib.Path]
PATH_GENERATOR = Generator[pathlib.Path, None, None]
OPTIONAL_PATH_LIST = Optional[LIST_OF_PATHS]
