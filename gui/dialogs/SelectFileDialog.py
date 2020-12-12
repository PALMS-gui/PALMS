"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
import importlib
import os
import pathlib
import sys
from pathlib import Path

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout

from config.config import ALL_DATABASES, DATABASE_MODULE_NAME, ICON_PATH
from utils.utils_gui import Dialog

importlib.import_module(DATABASE_MODULE_NAME)

window_title = 'Database selector'


class SelectFileDialog(QDialog):
    """
    Dialog pop-up to select a file to work with.
    Databases list is formed by all subclasses of the Database class in DatabaseHandler.py
    Then file list is generated using the selected database path and file template.
    Currently only one file can be selected. In order to annotate another file, the tool must be restarted.
    #TODO: make self.listWidget_files size to fit all found files, but not more than N
    #FIXME: databases with many files (>1000) are not fully shown. May be there is line limit in self.listWidget_files
    #TODO: choosing a custom file (self.onclick_find). Doubt if this is needed
    #TODO: allow multiple file selection
    """

    def __init__(self, prev_database: str = None, parent=None):
        super().__init__(parent)
        self.setGeometry(50, 50, 200, 200)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setWindowTitle(window_title)
        self.setWindowIcon(QtGui.QIcon(str(ICON_PATH)))
        screen_center = lambda widget: QtWidgets.QApplication.desktop().screen().rect().center() - widget.rect().center()
        self.move(screen_center(self))

        self.combobox_database = QtWidgets.QComboBox()
        self.combobox_database.clearFocus()
        self.combobox_database.setFocusPolicy(QtCore.Qt.TabFocus)
        # self.combobox_database.setFocusPolicy(QtCore.Qt.NoFocus)
        self.combobox_database.addItems(ALL_DATABASES)
        if prev_database is not None and prev_database in ALL_DATABASES:
            self.combobox_database.setCurrentText(prev_database)
        db_name = self.combobox_database.currentText()
        self.db = getattr(sys.modules[DATABASE_MODULE_NAME], db_name).__call__()
        self.combobox_database.currentIndexChanged.connect(self.selectionchange)

        self.listWidget_files = QtWidgets.QListWidget()
        self.listWidget_files.setGeometry(QtCore.QRect(10, 60, 221, 241))
        self.listWidget_files.setObjectName('{} files found in {}'.format(self.db.file_template, self.db.DATAPATH))
        self.listWidget_files.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)  # single file selection
        # self.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # multiple files selection: NotImplemented
        self.find_files()
        self.update_list_geometry()
        self.listWidget_files.setCurrentRow(0)
        self.z = self.listWidget_files.selectionModel()
        self.z.currentChanged.connect(self.on_row_changed)

        self.button_select = QtWidgets.QPushButton('Select')
        self.button_select.clicked.connect(self.onclick_select)
        self.button_find = QtWidgets.QPushButton('Find a file')
        self.button_find.clicked.connect(self.onclick_find)

        hbox = QHBoxLayout()
        hbox.addWidget(self.button_select)
        hbox.addStretch()
        hbox.addWidget(self.button_find)

        vbox = QVBoxLayout()
        vbox.addWidget(self.combobox_database)
        vbox.addWidget(self.listWidget_files)
        vbox.addLayout(hbox)
        self.setLayout(vbox)
        self.adjustSize()
        # self.show()

    def onclick_find(self):
        Dialog().warningMessage('Custom file choice not implemented')

    def on_row_changed(self, current, previous):
        try:
            # fn = [pathlib.Path(self.db.DATAPATH, item.text()) for item in self.listWidget_files.selectedItems()]
            file_idx = current.row() + 1
            n_files = len(self.db.get_all_files_in_database())
            progress_str = str(file_idx) + '/' + str(n_files)
            self.setWindowTitle(window_title + ' ' + progress_str)
        except:
            pass

    def onclick_select(self):
        try:
            fn = [pathlib.Path(self.db.DATAPATH, item.text()) for item in self.listWidget_files.selectedItems()]
            if len(fn) > 1:
                Dialog().warningMessage('Multiple file selection not implemented')
            self.selected_files = fn
            global selected_files
            selected_files = fn
            self.accept()
        except Exception as e:
            Dialog().warningMessage(str(e))

    def find_files(self):
        if not os.path.isdir(self.db.DATAPATH):
            Dialog().warningMessage('database path is incorrect. No files can be found.')
        tmp = '**/*.' + self.db.filetype if self.db.file_template is None else self.db.file_template
        for filename in Path(self.db.DATAPATH).glob(tmp):
            item = QtWidgets.QListWidgetItem()
            item.setFont(QtGui.QFont('Arial', 16))
            item.setText(filename.as_posix().replace(self.db.DATAPATH.as_posix() + '/', ''))
            if self.db.annotation_exists(pathlib.Path(item.text()).stem):
                item.setForeground(QtGui.QColor(QtCore.Qt.darkBlue))
                item.setBackground(QtGui.QColor(QtCore.Qt.lightGray))
            else:
                item.setForeground(QtGui.QColor(QtCore.Qt.blue))
            self.listWidget_files.addItem(item)
        self.listWidget_files.setMinimumWidth(self.listWidget_files.sizeHintForColumn(0))
        if self.listWidget_files.count() > 0:
            self.listWidget_files.setCurrentRow(0)
        self.listWidget_files.setFocus()

    def selectionchange(self):
        db_name = self.combobox_database.currentText()
        self.db = getattr(sys.modules[DATABASE_MODULE_NAME], db_name).__call__()
        self.listWidget_files.clear()
        self.find_files()
        self.update_list_geometry()

    def update_list_geometry(self):
        width = self.listWidget_files.sizeHintForColumn(0) + 2 * self.listWidget_files.frameWidth()
        width = min([width, 1000])
        self.listWidget_files.setMinimumWidth(width)
        height = self.listWidget_files.sizeHintForRow(0) * self.listWidget_files.count() + 2 * self.listWidget_files.frameWidth()
        height = min([height, 600])
        self.listWidget_files.setMinimumHeight(height)

    def exec(self):
        self.listWidget_files.setFocus()
        accepted = super(SelectFileDialog, self).exec()
        return accepted
