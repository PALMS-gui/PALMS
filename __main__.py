"""
Copyright (c) 2020 Stichting imec Nederland (https://www.imec-int.com/en/imec-the-netherlands)
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
import importlib
import sys
# NB: do not remove. PanTompkinsQRSDetector is used in one of the configuration files,
#  but when an executable is created via pyinstaller this dependency is not fetched as
#  database config files are not part of the distribution. If something is explicitly imported here,
#  it can be used later inside any database config files by 'from __main__ import ...'
from utils.QRSDetectorOffline import QRSDetectorOffline as PanTompkinsQRSDetector
tmp = PanTompkinsQRSDetector

try:  # NB: import here external algorithms to be used later in database configuration files (see ECG_Physionet2011.py)
    pass
except Exception as e:
    str(e)

from gui import PALMS


def reimport_all():
    """
    when restarting the app, all modules need to be reset, otherwise some settings might have non-default values
    TODO: "model" can't be reloaded because of the circular imports
    """
    from gui import viewer, view_table, plot_area, rendering, tracking, display_panel
    from logic import operation_mode
    # importlib.reload(model)
    importlib.reload(viewer)
    importlib.reload(view_table)
    importlib.reload(plot_area)
    importlib.reload(display_panel)
    importlib.reload(rendering)
    importlib.reload(tracking)
    importlib.reload(operation_mode)


def main():
    """
    if the app was closed with EXIT_CODE_REBOOT, then it was restarted
    """

    file_to_load = None
    exit_code = PALMS.EXIT_CODE_REBOOT
    while exit_code in [PALMS.EXIT_CODE_REBOOT, PALMS.EXIT_CODE_LOAD_NEXT, PALMS.EXIT_CODE_LOAD_PREV]:
        reimport_all()
        app = PALMS(file_to_load)
        exit_code, file_to_load = app.start()
        app._exit(exit_code)
    sys.exit(exit_code)


main()
