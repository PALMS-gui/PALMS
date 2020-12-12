"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
import weakref
import pandas as pd
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSlot, qInfo, qWarning
from PyQt5.QtWidgets import QSizePolicy, QFileDialog
from qtpy.QtCore import Slot
from config.config import ICON_PATH
from config import tooltips
from logic.operation_mode.annotation import AnnotationConfig, SingleFiducialConfig
from utils.utils_general import get_project_root
from utils.utils_gui import Dialog


class AnnotationConfigDialog(QtWidgets.QDialog):
    _instance = None

    def __init__(self, app, fileName=None, parent=None):
        super().__init__(parent)
        self.application = app
        self.fileName = fileName
        self.setWindowTitle('Annotation Configuration')
        self.setMinimumSize(540, 30)  # TODO: resize automatically to fit everything
        self.resize(540, 30)
        self.setWindowIcon(QtGui.QIcon(str(ICON_PATH)))
        self.setWindowFlags(QtCore.Qt.WindowSystemMenuHint | QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowCloseButtonHint)

        self.table = QtWidgets.QTableWidget(self)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setToolTip('Visualization of annotationConfig file')

        self.pushButtonLoad = QtWidgets.QPushButton(self)
        self.pushButtonLoad.setText("Load Csv File!")
        self.pushButtonLoad.clicked.connect(self.on_clicked_save)

        self.pushButtonWrite = QtWidgets.QPushButton(self)
        self.pushButtonWrite.setText("Write Csv File!")
        self.pushButtonWrite.clicked.connect(self.on_clicked_load)
        self.pushButtonWrite.setEnabled(True)

        self.layoutVertical = QtWidgets.QVBoxLayout(self)
        self.layoutVertical.addWidget(self.table)
        # spacerItem = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        # self.layoutVertical.addItem(spacerItem)
        self.layoutVertical.addWidget(self.pushButtonLoad, alignment=QtCore.Qt.AlignCenter)
        self.layoutVertical.addWidget(self.pushButtonWrite, alignment=QtCore.Qt.AlignCenter)
        self.layoutVertical.setAlignment(QtCore.Qt.AlignCenter)
        self.layoutVertical.setContentsMargins(0, 0, 0, 0)

        self.adjustSize()
        AnnotationConfigDialog._instance = weakref.ref(self)()

    def generate_pinned_to_choices_from_current_views(self):
        from gui import PALMS
        items, plotted_tracks = [], []
        # self.main_window.model.panels
        # TODO: also check other panels, but doing this will drag other bugs, as currently using multipanels is not bug-free
        for p in self.application.viewer.model.panels:
            plotted_tracks.extend([v.track.label for v in p.views])
        # plotted_tracks = [v.track.label for v in self.application.viewer.selectedPanel.views]
        for t in plotted_tracks:
            for p in PALMS.config['pinned_to_options']:
                # if not t == Database.get().main_track_label:
                items.append(p + ' ' + t)
        return items

    # not used
    def reset_pinned_to_options_to_existing_views(self):
        items = self.generate_pinned_to_choices_from_current_views()
        for row in range(self.table.rowCount()):
            if self.combo_pinned_to[row].currentText() not in items:
                self.combo_pinned_to[row].setCurrentText(items[0])

    def table_to_fiducials(self):
        fiducials = []
        from gui import PALMS
        for row in range(self.table.rowCount()):
            row_data = {}
            for col in range(self.table.columnCount()):
                col_name = self.table.horizontalHeaderItem(col).text()
                self.table.toolTipDuration()
                w = self.table.cellWidget(row, col)
                if col_name in ['name', 'key', 'symbol', 'symbol_colour']:
                    row_data[col_name] = w.text()
                elif col_name in ['is_pinned']:
                    row_data[col_name] = bool(w.checkState())
                elif col_name in ['pinned_to']:
                    # assert w.currentText() in pinned_to_options
                    row_data[col_name] = w.currentText()
                elif col_name in ['pinned_window', 'min_distance']:
                    row_data[col_name] = w.value()
                elif col_name in ['symbol_size']:
                    row_data[col_name] = int(w.text())

            assert all([k in row_data.keys() for k in PALMS.config['annotationConfig_columns']])
            fiducials.append(SingleFiducialConfig(row_data))
        return fiducials

    @Slot()
    def update_aConf(self, **kwargs):
        aConf = AnnotationConfig.get()
        fiducials = self.table_to_fiducials()
        aConf.reset_fiducials_config(fiducials)
        self.table.clear()
        self.aConf_to_table(aConf)

        # NB: recover aConf.pinned_to changes from json
        #  it is not needed as one can rewrite annotation config from AnnotationConfigDialog Save button
        # see also AnnotationConfig where saved data is applied
        # from gui.viewer import PALMS
        # pinned_to_state = {}
        # for f in aConf.fiducials:
        #     pinned_to_state.update({f.name: f.pinned_to})
        # PALMS.config.update({'pinned_to_last_state': pinned_to_state})

    def aConf_to_table(self, aConf):
        from gui import PALMS
        aConfColumns = PALMS.config['annotationConfig_columns']
        if aConf:
            self.table.clearContents()
            rowCount = len(aConf.fiducials)
            columnCount = len(aConfColumns)
            self.table.setRowCount(rowCount)
            self.table.setColumnCount(columnCount)

            self.qlabel_name = [{} for _ in range(rowCount)]
            self.qlabel_key = [{} for _ in range(rowCount)]
            self.checkbox_is_pinned = [{} for _ in range(rowCount)]
            self.combo_pinned_to = [{} for _ in range(rowCount)]
            self.spin_window = [{} for _ in range(rowCount)]
            self.spin_min_distance = [{} for _ in range(rowCount)]
            self.table.setHorizontalHeaderLabels(aConfColumns)
            # self.table.setVerticalHeaderLabels([aConf.fiducials[row].name for row in range(rowCount)])
            for row in range(rowCount):
                for col in range(columnCount):
                    fid = aConf.fiducials[row]
                    colName = aConfColumns[col]
                    colValue = fid.__getattribute__(colName)
                    if colName in ['name']:
                        self.qlabel_name[row] = QtWidgets.QLabel()
                        self.qlabel_name[row].row = row
                        self.qlabel_name[row].setText(colValue)
                        # self.qlabel_name[row].setFixedWidth(40)
                        self.qlabel_name[row].setEnabled(False)
                        self.qlabel_name[row].setFont(QtGui.QFont("Times", 12, QtGui.QFont.Bold))
                        self.qlabel_name[row].setAlignment(QtCore.Qt.AlignHCenter)
                        self.qlabel_name[row].setAlignment(QtCore.Qt.AlignVCenter)
                        self.table.setCellWidget(row, col, self.qlabel_name[row])
                        self.table.horizontalHeaderItem(col).setToolTip(tooltips.name)
                    elif colName in ['key']:
                        self.qlabel_key[row] = QtWidgets.QLabel()
                        self.qlabel_key[row].row = row
                        self.qlabel_key[row].setText(colValue)
                        # self.qlabel_key[row].setFixedWidth(15)
                        self.qlabel_key[row].setEnabled(False)
                        self.qlabel_key[row].setFont(QtGui.QFont("Times", 12, QtGui.QFont.Bold))
                        self.qlabel_key[row].setAlignment(QtCore.Qt.AlignHCenter)
                        self.qlabel_key[row].setAlignment(QtCore.Qt.AlignVCenter)
                        self.table.setCellWidget(row, col, self.qlabel_key[row])
                        self.table.horizontalHeaderItem(col).setToolTip(tooltips.key)
                    elif colName in ['is_pinned']:
                        self.checkbox_is_pinned[row] = QtWidgets.QCheckBox()
                        self.checkbox_is_pinned[row].row = row
                        self.checkbox_is_pinned[row].setChecked(colValue)
                        self.checkbox_is_pinned[row].stateChanged.connect(self.update_aConf)
                        self.table.setCellWidget(row, col, self.checkbox_is_pinned[row])
                        self.table.horizontalHeaderItem(col).setToolTip(tooltips.is_pinned)
                    elif colName in ['pinned_to']:
                        self.combo_pinned_to[row] = QtWidgets.QComboBox()
                        self.combo_pinned_to[row].row = row
                        # self.combo_pinned_to[row].addItems(pinned_to_options)
                        self.combo_pinned_to[row].addItems(self.generate_pinned_to_choices_from_current_views())
                        if colValue not in self.generate_pinned_to_choices_from_current_views():
                            qInfo('{} pinned_to options do not contain {} '.format(colName,colValue))
                        self.combo_pinned_to[row].setCurrentText(colValue)
                        self.combo_pinned_to[row].setFocusPolicy(QtCore.Qt.NoFocus)
                        self.combo_pinned_to[row].currentIndexChanged.connect(self.update_aConf)
                        self.combo_pinned_to[row].setEnabled(self.checkbox_is_pinned[row].isChecked())
                        self.table.setCellWidget(row, col, self.combo_pinned_to[row])
                        self.table.horizontalHeaderItem(col).setToolTip(tooltips.pinned_to)
                    elif colName in ['pinned_window']:
                        self.spin_window[row] = QtWidgets.QDoubleSpinBox()
                        self.spin_window[row].row = row
                        self.spin_window[row].setValue(colValue)
                        self.spin_window[row].setMinimum(0)
                        self.spin_window[row].setMaximum(10)
                        self.spin_window[row].setSingleStep(0.05)
                        self.spin_window[row].setSuffix(' s')
                        self.spin_window[row].setAlignment(QtCore.Qt.AlignHCenter)
                        self.spin_window[row].setAlignment(QtCore.Qt.AlignVCenter)
                        self.spin_window[row].valueChanged.connect(self.update_aConf)
                        self.table.setCellWidget(row, col, self.spin_window[row])
                        self.table.horizontalHeaderItem(col).setToolTip(tooltips.pinned_window)
                    elif colName in ['min_distance']:
                        self.spin_min_distance[row] = QtWidgets.QDoubleSpinBox()
                        self.spin_min_distance[row].row = row
                        self.spin_min_distance[row].setValue(colValue)
                        self.spin_min_distance[row].setMinimum(0)
                        self.spin_min_distance[row].setMaximum(50)
                        self.spin_min_distance[row].setSingleStep(0.1)
                        self.spin_min_distance[row].setSuffix(' s')
                        self.spin_min_distance[row].setAlignment(QtCore.Qt.AlignHCenter)
                        self.spin_min_distance[row].setAlignment(QtCore.Qt.AlignVCenter)
                        self.spin_min_distance[row].valueChanged.connect(self.update_aConf)
                        self.table.setCellWidget(row, col, self.spin_min_distance[row])
                        self.table.horizontalHeaderItem(col).setToolTip(tooltips.spin_min_distance)
                    elif colName in ['symbol', 'symbol_size', 'symbol_colour']:
                        item = QtWidgets.QLabel()
                        item.setText(str(colValue))
                        item.setFont(QtGui.QFont("Times", 12, QtGui.QFont.Bold))
                        # item.setFixedWidth(10)
                        item.setEnabled(False)
                        item.setAlignment(QtCore.Qt.AlignHCenter)
                        item.setAlignment(QtCore.Qt.AlignVCenter)
                        self.table.setCellWidget(row, col, item)
                        if colName == 'symbol':
                            self.table.horizontalHeaderItem(col).setToolTip(tooltips.symbol)
                        elif colName == 'symbol_colour':
                            self.table.horizontalHeaderItem(col).setToolTip(tooltips.symbol_colour)
                    else:
                        raise ValueError  # TODO: align checkboxes https://stackoverflow.com/questions/32458111/pyqt-allign-checkbox-and-put-it-in-every-row

            for col in range(columnCount):
                header = self.table.horizontalHeader()
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
                header.setDefaultAlignment(QtCore.Qt.AlignHCenter)  # QApplication.processEvents()  # self.adjustSize()

            # can't just run self.update_aConf() as it will go into infinite loop (update_aConf <-> update_table)
            fiducials = self.table_to_fiducials()
            aConf.reset_fiducials_config(fiducials)
        else:
            qInfo("aConf is None")

    def show(self):
        self.aConf_to_table(AnnotationConfig.get())
        super().show()

    @classmethod
    def get(cls):
        return cls._instance

    def load_annotation_config_from_csv(self, fileName=None):
        fn = fileName or self.fileName
        if not fn:
            fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load AnnotationConfig", get_project_root().as_posix(),
                                                          " (*.csv);; All Files (*)", options=QtWidgets.QFileDialog.Options())

        if fn:
            from gui import PALMS
            with open(fn, "r") as csv:
                settings_init = pd.read_csv(csv)
                fiducials = []
                for _, row_data in settings_init.iterrows():
                    try:
                        assert all([k in row_data for k in PALMS.config['annotationConfig_columns']])
                    except:
                        Dialog().warningMessage('Columns in chosen {file} file do not match aConfColumns from config.py. Try again! '
                                                ''.format(file=fn))
                        return
                    fiducials.append(SingleFiducialConfig(row_data))

            aConf = AnnotationConfig.get()
            aConf.reset_fiducials_config(fiducials)
            self.show()

    def write_annotation_config_to_csv(self, fileName=None):
        try:
            import csv
            options = QFileDialog.Options()
            options |= QFileDialog.DontUseNativeDialog
            fileName, _ = QFileDialog.getSaveFileName(self, 'Save File', get_project_root().as_posix(), "CSV Files(*.csv)", options=options)
            if fileName:
                with open(fileName, 'w', newline='') as stream:
                    writer = csv.writer(stream, delimiter=',')
                    header_items = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                    writer.writerow(header_items)
                    for row in range(self.table.rowCount()):
                        row_data = {}
                        for col in range(self.table.columnCount()):
                            col_name = self.table.horizontalHeaderItem(col).text()
                            self.table.toolTipDuration()
                            w = self.table.cellWidget(row, col)
                            if col_name in ['name', 'key', 'symbol', 'symbol_colour']:
                                row_data[col_name] = w.text()
                            elif col_name in ['is_pinned']:
                                row_data[col_name] = bool(w.checkState())
                            elif col_name in ['pinned_to']:
                                # assert w.currentText() in pinned_to_options
                                row_data[col_name] = w.currentText()
                            elif col_name in ['pinned_window', 'min_distance']:
                                row_data[col_name] = w.value()
                            elif col_name in ['symbol_size']:
                                row_data[col_name] = int(w.text())
                        row_text = [str(int(i))if isinstance(i, bool) else str(i) for i in row_data.values()]
                        writer.writerow(row_text)
            qInfo('Annotation config saved to ' + fileName)
        except Exception as e:
            qWarning('Failed to save Annotation Config\r\n' + str(e))


    @pyqtSlot(name='on_clicked_load')
    def on_clicked_load(self):
        self.write_annotation_config_to_csv(self.fileName)

    @pyqtSlot(name='on_clicked_save')
    def on_clicked_save(self):
        self.load_annotation_config_from_csv(self.fileName)

