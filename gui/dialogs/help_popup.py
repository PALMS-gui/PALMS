"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
import importlib
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout
from PyQt5.QtCore import qWarning
from config.config import DATABASE_MODULE_NAME, ICON_PATH

importlib.import_module(DATABASE_MODULE_NAME)


class help_popup(QDialog):
    def __init__(self, prev_database: str = None, parent=None):
        super().__init__(parent)
        self.setGeometry(50, 50, 200, 200)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowTitle('Help')
        self.setWindowIcon(QtGui.QIcon(str(ICON_PATH)))
        screen_center = lambda widget: QtWidgets.QApplication.desktop().screen().rect().center() - widget.rect().center()
        self.move(screen_center(self))

        self.list_shortcuts = QtWidgets.QListWidget()
        self.list_shortcuts.setGeometry(QtCore.QRect(10, 60, 221, 241))
        self.list_shortcuts.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.list_shortcuts.setFocus()
        self.populate_list()
        self.update_list_geometry()
        self.list_shortcuts.setEnabled(False)

        self.button_ok = QtWidgets.QPushButton('Ok')
        self.button_ok.clicked.connect(self.onclick_ok)

        hbox = QHBoxLayout()
        hbox.addWidget(self.button_ok)

        vbox = QVBoxLayout()
        vbox.addWidget(self.list_shortcuts)
        vbox.addLayout(hbox)
        self.setLayout(vbox)
        self.adjustSize()
        # self.show()

    def onclick_ok(self):
        self.close()

    def populate_list(self):  # TODO: make it a nice QTableView with two columns
        try:
            from gui.viewer import PALMS
            d = PALMS.shortcuts
            for desc, key in d.items():
                item = QtWidgets.QListWidgetItem()
                item.setFont(QtGui.QFont('Arial', 16))
                item.setText('{:<40}  {:9}  {:>30}'.format(desc, '   ---   ', str(key)))
                item.setForeground(QtGui.QColor(QtCore.Qt.darkBlue))
                item.setBackground(QtGui.QColor(QtCore.Qt.lightGray))
                self.list_shortcuts.addItem(item)
        except Exception as e:
            qWarning('Could not load shortcuts info')

    def update_list_geometry(self):
        width = self.list_shortcuts.sizeHintForColumn(0) + 2 * self.list_shortcuts.frameWidth()
        width = min([width, 1000])
        self.list_shortcuts.setMinimumWidth(width)
        height = self.list_shortcuts.sizeHintForRow(0) * self.list_shortcuts.count() + 2 * self.list_shortcuts.frameWidth()
        height = min([height, 800])
        self.list_shortcuts.setMinimumHeight(height)
