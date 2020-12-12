"""
Copyright (c) 2020 Stichting imec Nederland (https://www.imec-int.com/en/imec-the-netherlands)
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
from pathlib import Path
from logic.databases.DatabaseHandler import Database
from utils.utils_general import resource_path

DATABASE_MODULE_NAME = 'logic.databases'
ALL_DATABASES = [c.__name__ for c in Database.__subclasses__()]
ICON_PATH = resource_path(Path('config', 'icons', 'PALMS.png'))
SHORTCUTS_PATH = resource_path(Path('config', 'shortcuts.json'))
CONFIG_PATH = Path('config.json').absolute()

# @formatter:off
default_config = {'panel_height'              : 300,
                  'yrange_margin'             : 0.1,
                  'partition_labels_font_size': 15,
                  'epoch_labels_font_size'    : 30,
                  'min_xzoom_factor'          : 4,
                  'autoscale_y'               : True,
                  'save_tracks'               : True,
                  'save_overwrite'            : True,
                  "show_cursor"               : False,
                  "show_xaxis_label"          : False,
                  "autoplay_timer_interval"   : 800,
                  "default_mode"              : "annotation"}


# @formatter:on
