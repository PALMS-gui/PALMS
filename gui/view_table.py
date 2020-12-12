"""
Copyright (c) 2005-2017 TimeView Developers
MIT license (see in gui\LICENSE.txt)
"""
import logging
import weakref
from itertools import cycle
from typing import Tuple, List, Optional
from functools import partial
from math import ceil

# 3rd party
from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Slot, Signal

from logic.databases.DatabaseHandler import Database
from utils.utils_gui import Dialog
from .model import Panel, View

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# pastel colors, will change to color-blind with an alternate option of bright
colors = [(146, 198, 255), (151, 240, 170), (255, 159, 154), (208, 187, 255), (255, 254, 163), (176, 224, 230)]
plot_colors = cycle(colors)


class ShowCheckBox(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        self.checkbox = QtWidgets.QCheckBox()
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.checkbox)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        self.setLayout(layout)
        self.checkbox.setChecked(True)


class ViewTable(QtWidgets.QTableWidget):
    colorChanged = Signal(View, name='colorChanged')
    plotViewObj = Signal(View, name='plotViewObj')
    tableWidth = Signal(int, name='tableWidth')
    colWidths = Signal(list, name='colWidths')
    showPlot = Signal(View, int, name='showPlot')
    hidePlot = Signal(View, name='hidePlot')
    newSelected = Signal(View, name='newSelected')
    _instance = None

    def __init__(self, display_panel, col_widths: Optional[List[int]] = None):
        super().__init__()
        self.display_panel = display_panel
        self.main_window = self.display_panel.main_window
        self.panel: Optional[Panel] = None
        self.columns = ('Track', 'Type', 'Show', 'Color')
        self.setColumnCount(len(self.columns))
        self.setHorizontalHeaderLabels(self.columns)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.verticalHeader().hide()
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setSectionsClickable(False)
        self.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.colWidths.connect(self.main_window.determineColumnWidths)
        self.hidePlot.connect(display_panel.hideView)
        self.showPlot.connect(display_panel.showView)
        self.newSelected.connect(display_panel.selectionChanged)
        self.itemSelectionChanged.connect(self.evalSelection)
        self.colorChanged.connect(display_panel.changeColor)
        self.plotViewObj.connect(display_panel.plotViewObj)

        if col_widths:
            self.setColumnWidths(col_widths)
        self.setFixedWidth(self.viewportSizeHint().width() + 2)
        self.setContentsMargins(0, 0, 0, 0)

        ViewTable._instance = weakref.ref(self)()

    @staticmethod
    def get():
        return ViewTable._instance

    def colNameToIndex(self, name: str) -> int:
        return self.columns.index(name)

    def loadPanel(self, panel_obj: Panel):
        self.setRowCount(0)
        assert isinstance(panel_obj, Panel)
        self.panel = panel_obj
        for view in panel_obj.views:
            self.addView(view)

    def delView(self, view_to_remove):
        """Remove the selected views from the panel"""
        row_to_remove = self.selectedRow()
        assert row_to_remove == self.panel.views.index(view_to_remove)
        if row_to_remove is None:
            return
        self.removeRow(row_to_remove)
        self.calcColumnWidths()

    def allViewsTrackLabels(self):
        return [v.track.label for v in self.panel.views]

    def selectedView(self) -> Optional[View]:
        """Returns the currently selected view"""
        if not self.selectedIndexes():
            logger.warning('Selected Indexes returned nothing')
            self.selectRow(0)
        return self.panel.selected_view

    def selectedRow(self) -> int:
        if self.selectedIndexes():
            row = self.selectedIndexes()[0].row()
            return row
        elif self.rowCount() > 0:
            logger.error('Rows exist but no row selected, selecting last row as guess')
            row = self.panel.views.index(self.panel.selected_view - 1)
            self.selectRow(row)
            return row
        else:
            return -1

    @Slot(name='evalSelection')
    def evalSelection(self):
        if self.rowCount() > 1:
            if 0 <= self.selectedRow() < self.rowCount():
                self.selectRow(self.selectedRow(), bypass=True)
            else:
                if self.panel.selected_view:
                    logger.error('No selected row, querying model')
                    row = self.panel.views.index(self.panel.selected_view)
                    self.selectRow(row, bypass=False)
                else:
                    logger.error('No selected row, no model.Panel.selected_view either')
                    self.panel.set_selected_view(self.panel.views[self.rowCount() - 1])
                    row = self.panel.views.index(self.panel.selected_view)
                    self.selectRow(row, bypass=False)

    # overloading select row operator so I can emit a signal to plot to change
    # and change the selected view property in the model.Model()
    def selectRow(self, row: int, bypass=False):
        if not bypass:
            super().selectRow(row)
        previous_selected_view = self.panel.selected_view
        new_selected_view = self.panel.views[row]
        self.panel.set_selected_view(new_selected_view)
        if new_selected_view is not previous_selected_view:
            self.newSelected.emit(new_selected_view)

    def indexFromWidget(self, widget: QtCore.QObject) -> Tuple[int, int]:
        for _ in range(5):  # only go 5 layers recursively
            if isinstance(widget.parent().parent(), QtWidgets.QTableWidget):
                index = self.indexAt(widget.pos())
                return index.row(), index.column()
            widget = widget.parent()
        else:
            logging.error('Could not find appropriate widget to map')
            self.main_window.application.viewer.status('Could not find appropriate widget to map')
            raise IndexError

    def rowFromWidget(self, widget) -> int:
        return self.indexFromWidget(widget)[0]

    def select_main_view(self):
        try:
            all_views = [v.track.label for v in self.main_window.selectedPanel.views]
            self.selectRow(all_views.index(Database.get().main_track_label))  # select the main signal again
        except:
            pass

    @Slot(int, name='toggleView')
    def toggleView(self, state: int):
        self.selectRow(self.rowFromWidget(self.sender()))
        if state == 2:
            self.selectedView().show = True
            self.showPlot.emit(self.selectedView(), self.selectedRow())
        else:
            self.selectedView().show = False
            self.hidePlot.emit(self.selectedView())
        self.select_main_view()

    def update_showCheckbox_state(self):
        for ir in range(self.rowCount()):
            self.selectRow(ir)
            self.cellWidget(ir, self.colNameToIndex('Show')).checkbox.setChecked(self.selectedView().show)
        self.select_main_view()

    def _configureFileLabel(self, view_object: View):
        font = QtGui.QFont("Monospace")
        font.setStyleHint(font.TypeWriter, strategy=font.PreferDefault)
        font.setFixedPitch(True)
        text = str(view_object.track.label)
        desired_length = 32
        if len(text) > desired_length:
            beginning = text[: ceil(desired_length / 2)]
            end = text[(len(text) - ceil(desired_length / 2)) + 1:]
            text = beginning + "⋯" + end
        assert len(text) <= 32
        fileLabel = QtWidgets.QLabel(text)
        fileLabel.setMargin(5)
        fileLabel.setFont(font)
        fileLabel.setAlignment(QtCore.Qt.AlignCenter)
        fileLabel.setToolTip(str(view_object.track.label))
        fileLabel.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        fileLabel.customContextMenuRequested.connect(self.viewPopup)
        self.setCellWidget(self.panel.views.index(view_object), self.colNameToIndex("Track"), fileLabel)

    def _configureTrackItem(self, view_object: View):
        text = type(view_object.track).__name__
        trackLabel = QtWidgets.QLabel(text)
        trackLabel.setMargin(5)
        trackLabel.setAlignment(QtCore.Qt.AlignCenter)
        trackLabel.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        trackLabel.customContextMenuRequested.connect(self.viewPopup)
        self.setCellWidget(self.panel.views.index(view_object), self.colNameToIndex("Type"), trackLabel)

    def _configureShowBox(self, view_object: View):
        show_check_box = ShowCheckBox()
        show_check_box.checkbox.setChecked(view_object.show)
        show_check_box.checkbox.stateChanged.connect(self.toggleView)
        self.setCellWidget(self.panel.views.index(view_object), self.colNameToIndex('Show'), show_check_box)

    def _configureColor(self, view_object: View):
        color_button = QtWidgets.QPushButton()
        row = self.panel.views.index(view_object)
        col = self.colNameToIndex('Color')
        r = view_object.color[0]
        g = view_object.color[1]
        b = view_object.color[2]
        color_button.setStyleSheet(f"background-color: rgb({r}, {g}, {b})")
        color_button.clicked.connect(self.changeColor)
        self.setCellWidget(row, col, color_button)

    @Slot(name='changeColor')
    def changeColor(self):
        self.selectRow(self.rowFromWidget(self.sender()))
        existing_color = createQColor(self.selectedView().color)
        dialog = QtWidgets.QColorDialog()
        for index, color in enumerate(colors):
            dialog.setCustomColor(index, createQColor(color))
        color = dialog.getColor(existing_color)
        if not color.isValid():
            logging.warning(f'Non valid color {color.getRgb()[0:3]}')
            self.main_window.application.viewer.status(f'Non valid color {color.getRgb()[0:3]}')
            return
        r, g, b = color.getRgb()[0:3]
        self.selectedView().set_color((r, g, b))
        self.sender().setStyleSheet(f"background-color: rgb({r}, {g}, {b})")
        self.colorChanged.emit(self.selectedView())

    def addView(self, view_object: View, setColor=True):
        """
        Add the view_object to the existing panel
        and display information in the table
        """
        if setColor:
            view_object.set_color(next(plot_colors))
        pos = self.panel.views.index(view_object)
        self.insertRow(pos)
        self._configureFileLabel(view_object)
        # self._configureComboBox(view_object)
        self._configureShowBox(view_object)
        self._configureTrackItem(view_object)
        self._configureColor(view_object)
        self.calcColumnWidths()
        self.plotViewObj.emit(view_object)
        self.selectRow(pos)

    @Slot(name='calcColumnWidths')
    def calcColumnWidths(self):
        self.resizeColumnsToContents()
        self.colWidths.emit([self.columnWidth(col) for col in range(self.columnCount())])

    @Slot(list, name='setColumnWidths')
    def setColumnWidths(self, widths: List[int]):
        for col, width in enumerate(widths):
            self.setColumnWidth(col, width)
        new_width = self.viewportSizeHint().width() + 2
        self.setFixedWidth(new_width)  # self.updateMaxWidth.emit()

    @Slot(QtCore.QPoint, name='viewPopup')
    def viewPopup(self, point):
        if isinstance(self.sender(), QtWidgets.QHeaderView):
            row = self.sender().logicalIndexAt(point)
        elif isinstance(self.sender(), QtWidgets.QLabel):
            row = self.rowFromWidget(self.sender())
        else:
            logging.error(f'do not know how to handle getting index of ', f'{self.sender()} object')
            self.main_window.application.viewer.status(f'do not know how to handle getting index of ', f'{self.sender()} object')
            raise TypeError
        view = self.panel.views[row]
        menu = QtWidgets.QMenu(self.verticalHeader())
        menu.clear()
        move_menu = menu.addMenu('&Move View')
        link_menu = menu.addMenu("&Link Track")
        copy_menu = menu.addMenu("Copy View")

        derive_menu = menu.addMenu("Add derived tracks")

        linkAction = QtWidgets.QAction('Create Link in this Panel', self)
        linkAction.triggered.connect(partial(self.display_panel.linkTrack, view, self.main_window.model.panels.index(self.panel)))
        link_menu.addAction(linkAction)
        link_menu.addSeparator()
        link_menu.setEnabled(False)

        copyAction = QtWidgets.QAction("Duplicate View in this Panel", self)
        copyAction.triggered.connect(partial(self.display_panel.copyView, view, self.main_window.model.panels.index(self.panel)))
        copy_menu.addAction(copyAction)
        copy_menu.addSeparator()
        copy_menu.setEnabled(False)

        addDerivativeAction = QtWidgets.QAction('1st derivative', self)
        addDerivativeAction.triggered.connect(
            partial(self.display_panel.addDerivative, view, self.main_window.model.panels.index(self.panel), 1))
        # TODO: derivative filters GUI
        derive_menu.addAction(addDerivativeAction)

        addDerivativeAction = QtWidgets.QAction('2nd derivative', self)
        addDerivativeAction.triggered.connect(
            partial(self.display_panel.addDerivative, view, self.main_window.model.panels.index(self.panel), 2))
        derive_menu.addAction(addDerivativeAction)

        menu.addSeparator()

        try:
            addRRintervalMenu = menu.addMenu('RR-intevals')
            from logic.operation_mode.annotation import AnnotationConfig
            RRintervalMenu_actions = []
            for f in AnnotationConfig.all_fiducials():
                f_idx = AnnotationConfig.get().find_idx_by_name(f)
                if AnnotationConfig.get().fiducials[f_idx].annotation.x.size > 2:
                    action = QtWidgets.QAction(f, self, checkable=False, enabled=True)
                    action.triggered.connect(partial(self.main_window.application.add_view_from_track,
                                                     AnnotationConfig.get().fiducials[f_idx].annotation.create_RRinterval_track(),
                                                     self.main_window.model.panels.index(self.panel)))
                    RRintervalMenu_actions.append(action)
                    addRRintervalMenu.addAction(action)
        except Exception as e:
            Dialog().warningMessage('Creating RR interval plot failed\r\n'
                                    'The error was:\r\n' +
                                    str(e))

        # TODO: load another track
        # TODO: move existing view

        db = Database.get()
        add_menu = menu.addMenu("Add tracks from DB")
        add_menu.setEnabled(False)
        if db is not None and db.ntracks() > 0:
            add_menu.setEnabled(True)
            for label, track in db.tracks.items():
                plot_signal_action = QtWidgets.QAction(label, self)
                plot_signal_action.triggered.connect(
                    partial(self.main_window.application.add_view_from_track, track, self.main_window.model.panels.index(self.panel)))
                add_menu.addAction(plot_signal_action)
                if label not in self.allViewsTrackLabels():
                    plot_signal_action.setEnabled(True)
                else:
                    plot_signal_action.setEnabled(False)

        menu.addSeparator()
        process_action = QtWidgets.QAction('Processor Config', self)
        process_action.triggered.connect(partial(self.main_window.application.viewer.processorConfig.show, self.selectedView()))
        menu.addAction(process_action)
        process_action.setEnabled(False)

        menu.addSeparator()
        invertAction = QtWidgets.QAction('&Invert Track', self)
        invertAction.triggered.connect(self.main_window.invertView)
        invertAction.setEnabled(False)
        menu.addAction(invertAction)

        menu.addSeparator()
        deleteAction = QtWidgets.QAction('&Delete Track', self)
        deleteAction.triggered.connect(self.main_window.guiDelView)
        menu.addAction(deleteAction)

        for index, panel in enumerate(self.main_window.model.panels):
            if panel is self.panel:
                continue
            linkAction = QtWidgets.QAction(f'Link to Panel {index + 1}', self)
            linkAction.triggered.connect(partial(self.display_panel.linkTrack, view, index))
            link_menu.addAction(linkAction)

            moveAction = QtWidgets.QAction(f'Move To Panel {index + 1}', self)
            moveAction.triggered.connect(partial(self.display_panel.moveView, view, index))
            move_menu.addAction(moveAction)

            copyAction = QtWidgets.QAction(f'Copy to Panel {index + 1}', self)
            copyAction.triggered.connect(partial(self.display_panel.copyView, view, index))
            copy_menu.addAction(copyAction)

        moveAction = QtWidgets.QAction(f'Move to New Panel', self)
        moveAction.triggered.connect(partial(self.display_panel.moveView, view, -1))

        linkAction = QtWidgets.QAction(f'Link to New Panel', self)
        linkAction.triggered.connect(partial(self.display_panel.linkTrack, view, -1))

        copyAction = QtWidgets.QAction(f'Copy to New Panel', self)
        copyAction.triggered.connect(partial(self.display_panel.copyView, view, -1))

        move_menu.addSeparator()
        link_menu.addSeparator()
        copy_menu.addSeparator()
        move_menu.addAction(moveAction)
        link_menu.addAction(linkAction)
        copy_menu.addAction(copyAction)
        menu.popup(QtGui.QCursor.pos())


def createQColor(rgb: Tuple[int, int, int]) -> QtGui.QColor:
    return QtGui.QColor.fromRgb(rgb[0], rgb[1], rgb[2])
