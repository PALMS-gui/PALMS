"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
from enum import Enum, unique
from PyQt5.QtCore import qInfo


@unique
class Modes(Enum):
    # keep keys and values the same!
    browse = 'browse'
    annotation = 'annotation'
    partition = 'partition'
    epoch = 'epoch'


class Mode:
    mode = None

    @staticmethod
    def switch_mode(new_mode: Modes):
        """it is a callback to Modes checkboxes. defines which mode should be switched on and emits a setOperationMode signal"""
        from gui.viewer import Viewer
        old_mode = Mode.mode

        # if old_mode == new_mode:  # switching off current mode --> browsing mode
        #     if new_mode in [Modes.annotation, Modes.partition, Modes.epoch]:
        #         new_mode = Modes.browse
        # elif not old_mode == new_mode:
        #     pass

        Mode.mode = new_mode
        Viewer.get().setOperationMode.emit(new_mode)
        qInfo('Mode: ' + Mode.mode.value)

    @staticmethod
    def is_annotation_mode():
        return Mode.mode == Modes.annotation

    @staticmethod
    def is_partition_mode():
        return Mode.mode == Modes.partition

    @staticmethod
    def is_epoch_mode():
        return Mode.mode == Modes.epoch

    @staticmethod
    def current_mode_name():
        return Mode.mode.value

    @staticmethod
    def all_modes():
        return [s.value for s in Modes]
