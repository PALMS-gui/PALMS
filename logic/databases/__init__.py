# import all modules from this package to be able to correctly establish all subclasses inheriting from Database class
import pathlib
import sys

from logic.databases import DatabaseHandler

__all__ = []

import pkgutil
import inspect

import os
import glob
from utils.utils_general import get_project_root

print(get_project_root().as_posix())
# first check all .py files at project level if they inherit logic.databases.DatabaseHandler.Database
for file in glob.glob(get_project_root().as_posix() + "/*.py"):
    name = pathlib.Path(file).stem
    sys.path.append(str(pathlib.Path(file).parent))
    module = __import__(name)
    if hasattr(module, name) and issubclass(getattr(module, name), DatabaseHandler.Database):
        globals()[name] = getattr(module, name)
        __all__.append(name)

# then check logic.databases
for loader, name, is_pkg in pkgutil.walk_packages(__path__):
    module = loader.find_module(name).load_module(name)

    for name, value in inspect.getmembers(module):
        if name.startswith('__'):
            continue

        globals()[name] = value
        __all__.append(name)
