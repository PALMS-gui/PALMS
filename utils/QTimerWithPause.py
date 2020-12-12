"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
from PyQt5 import QtCore


class QTimerWithPause(QtCore.QTimer):
    def __init__(self, parent=None, interval=200):
        QtCore.QTimer.__init__(self, parent)
        self.interval = interval

    def set_interval(self, interval):
        self.interval = interval

    def pause(self):
        if self.isActive():
            self.stop()

    def resume(self):
        if not self.isActive():
            self.start(self.interval)
