"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""

from PyQt5.QtCore import qWarning, qInfo
from PyQt5.QtWidgets import QMessageBox, QDialog


class Dialog(QDialog):
    def __init__(self, parent=None):
        super(Dialog, self).__init__(parent)

    def warningMessage(self, msg, header='Assert warning'):
        msgBox = QMessageBox(QMessageBox.Warning, header, msg, QMessageBox.NoButton, self)
        qWarning(msg)
        msgBox.addButton("Ok", QMessageBox.AcceptRole)
        if msgBox.exec_() == QMessageBox.AcceptRole:
            pass
        self.show()

    def informationMessage(self, msg):
        reply = QMessageBox.information(self, "QMessageBox.information()", msg)
        qInfo(msg)
        if reply == QMessageBox.Ok:
            self.informationLabel.setText("OK")
        else:
            self.informationLabel.setText("Escape")
        self.show()
