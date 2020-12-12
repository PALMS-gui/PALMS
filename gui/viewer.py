"""
Copyright (c) 2005-2017 TimeView Developers
MIT license (see in gui\LICENSE.txt)
"""
from functools import partial
import json
import time
import logging
import re
import sys
import weakref
import pathlib
from collections import defaultdict
from pathlib import Path
from timeit import default_timer as timer
from typing import Tuple, List, Optional, DefaultDict, Dict
from config import config, tooltips
from gui.dialogs.SelectFileDialog import SelectFileDialog
from utils.QTimerWithPause import QTimerWithPause
import numpy as np
import pyqtgraph as pg
from config.config import ICON_PATH, ALL_DATABASES, DATABASE_MODULE_NAME
from pandas import read_csv
from qtpy import QtWidgets, QtGui, QtCore
from qtpy.QtCore import Slot, Signal
from gui.dialogs.AnnotationConfigDialog import AnnotationConfigDialog
from gui.dialogs.help_popup import help_popup
from gui.dialogs.FilterConfigDialog import FilterConfigDialog
from gui import tracking
from logic.databases.DatabaseHandler import Database
from PyQt5.QtCore import qInfo, qDebug
from .display_panel import DisplayPanel, Frame
from .model import Model, View, Panel
from .view_table import ViewTable
from utils.utils_general import get_project_root, resource_path
from utils.utils_gui import Dialog
from logic.operation_mode.operation_mode import Modes, Mode
from logic.operation_mode.partitioning import Partitions
from logic.operation_mode.epoch_mode import EpochWindow, EpochModeConfig
from gui.plot_area import PlotArea

logger = logging.getLogger()
if __debug__:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.WARN)


class Group(QtCore.QObject):
    relay = Signal(name='relay')

    def __init__(self) -> None:
        super().__init__()
        self.views: List[View] = []

    def viewsExcludingSource(self, view_to_exclude):
        return [view for view in set(self.views) if view is not view_to_exclude]

    def join(self, view):
        self.views.append(view)
        self.relay.connect(view.renderer.reload)


class ScrollArea(QtWidgets.QScrollArea):
    dragEnterSignal = Signal(name='dragEnterSignal')
    dragLeaveSignal = Signal(name='dragLeaveSignal')
    dropSignal = Signal(name='dropSignal')

    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setParent(parent)
        self.dropSignal.connect(self.parent().moveToEnd)
        self.setWidgetResizable(True)
        self.setAcceptDrops(True)
        self.setContentsMargins(0, 0, 0, 0)

    def dropEvent(self, event: QtGui.QDropEvent):
        self.dropSignal.emit()
        event.accept()

    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent):
        self.dragLeaveSignal.emit()
        event.accept()

    def sizeHint(self):
        return QtCore.QSize(1000, 810)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.type() == QtCore.QEvent.KeyPress:
            event.ignore()


class ScrollAreaWidgetContents(QtWidgets.QWidget):

    def __init__(self, parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setParent(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignTop)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        self.dragStartPos = QtCore.QPoint(0, 0)

    def swapWidgets(self, positions: Tuple[int, int]):
        assert len(positions) == 2
        if positions[0] == positions[1]:
            return
        frame_one = self.layout.takeAt(min(positions)).widget()
        frame_two = self.layout.takeAt(max(positions) - 1).widget()
        self.layout.insertWidget(min(positions), frame_two)
        self.layout.insertWidget(max(positions), frame_one)


class Viewer(QtWidgets.QMainWindow):
    queryAxesWidths = Signal(name='queryAxisWidths')
    queryColWidths = Signal(name='queryColWidths')
    setAxesWidth = Signal(float, name='setAxesWidth')
    setSplitter = Signal(list, name='setSplitter')
    moveSplitterPosition = Signal(name='moveSplitterPosition')
    setColWidths = Signal(list, name='setColWidths')
    refresh = Signal(name='refresh')
    cursorReadoutStatus = Signal(bool, name='cursor_readout_status')
    autoscaleYstatus = Signal(bool, name='autoscaleY_status')
    rewriteH5Status = Signal(bool, name='rewriteH5_status')
    setOperationMode = Signal(Modes, name='setOperationMode')

    _instance = None
    REBOOT_APP = False

    def __init__(self, application):
        super().__init__()
        self.application = application
        # self.annotationManager = ManagerWindow('Annotation Manager',self)
        self.annotationConfig = AnnotationConfigDialog(self.application)
        self.processorConfig = FilterConfigDialog(self.application)
        self.help_popup = help_popup(self.application)
        # self.partitionConfig = PartiotionConfigDialog(self.application) #TODO??
        if ICON_PATH.exists():
            # pix_map_icon = QtGui.QPixmap(str(ICON_PATH), format="PNG")
            # self.setWindowIcon(QtGui.QIcon(pix_map_icon))
            #  this fixes a warning on OSX, but doesn't work at all on windows
            self.setWindowIcon(QtGui.QIcon(str(ICON_PATH)))
        else:
            logging.warning(f'cannot find icon at {ICON_PATH}')
        self.resize(QtWidgets.QDesktopWidget().availableGeometry(self).size() * 0.5)  # change this for video capture
        self.resize(*PALMS.config['viewer_window_size'])
        self.model: Model = Model()
        self.track_menu = None
        self.groups: DefaultDict[int, Group] = defaultdict(Group)
        self.setWindowTitle('PALMS')

        self.scrollArea = ScrollArea(self)
        self.scrollAreaWidgetContents = ScrollAreaWidgetContents(self.scrollArea)
        self.setCentralWidget(self.scrollArea)
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.synchronized = True
        self.cursor_readout = False
        self.autoscale_y = PALMS.config['autoscale_y']
        self.rewriteH5 = PALMS.config['save_overwrite']

        self.frames: List[Frame] = []
        self.selected_frame: Optional[Frame] = None
        self.moving_frame: Optional[Frame] = None
        self.from_index: Optional[int] = None
        self.to_index: Optional[int] = None

        self.axis_width = 10
        # for storing
        self.column_width_hint: List[int] = []
        self.all_column_widths: List[Dict[ViewTable, int]] = []

        self.reference_plot: Optional[pg.ViewBox] = None
        self.min_plot_width = self.width()

        self.createMenus()

        self.statusBar()
        self.status('Ready')
        self.guiAddPanel()
        self.evalTrackMenu()

        self.timer = QTimerWithPause(interval=PALMS.config['autoplay_timer_interval'])
        self.timer.timeout.connect(self.shiftRight)
        Viewer._instance = weakref.ref(self)()

    @staticmethod
    def get():
        return Viewer._instance if Viewer._instance is not None else None

    @Slot(float, float)
    def plot_point(self, x, y):
        line = pg.InfiniteLine(pos=x, angle=90, movable=False)
        # self.temporary_items.append(line)
        self.addItem(line)

    @Slot(name='guiAddPanel')
    def guiAddPanel(self, pos: Optional[int] = None):
        """
        when adding a panel through the gui, this method determines
        where the panel should go, and handles the associated frame selection
        """
        if pos is None:
            if not self.frames:
                pos = 0
            elif self.selected_frame:
                pos = self.frames.index(self.selected_frame) + 1
            else:
                pos = len(self.frames)
        self.createNewPanel(pos=pos)
        self.applySync()
        self.selectFrame(self.frames[pos])

    def createMenus(self):
        menu = self.menuBar()
        # to work around OSX bug that requires switching focus away from this
        # application, and the coming back to it, to make menu accessible this
        # is not necessary when started from the TimeView.app application icon
        if __debug__:  # I am beginning to think that I always want this
            menu.setNativeMenuBar(False)

        # File menu
        self.file_menu = menu.addMenu('&File')
        self.file_menu.setToolTipsVisible(True)

        self.file_menu.restart_action = QtWidgets.QAction('&Restart', self, enabled=True)
        self.file_menu.restart_action.setToolTip(tooltips.restart)
        self.file_menu.restart_action.triggered.connect(self.restart_app)
        self.file_menu.restart_action.setShortcut(PALMS.shortcuts['restart'])
        self.file_menu.addAction(self.file_menu.restart_action)

        self.file_menu.load_next_action = QtWidgets.QAction('&Load Next', self, enabled=True)
        self.file_menu.load_next_action.setToolTip(tooltips.restart_and_load_next)
        self.file_menu.load_next_action.triggered.connect(partial(self.restart_and_load, 'next'))
        self.file_menu.load_next_action.setShortcuts(PALMS.shortcuts['restart_and_load_next'])
        self.file_menu.addAction(self.file_menu.load_next_action)

        self.file_menu.load_prev_action = QtWidgets.QAction('&Load Prev', self, enabled=True)
        self.file_menu.load_prev_action.setToolTip(tooltips.restart_and_load_prev)
        self.file_menu.load_prev_action.triggered.connect(partial(self.restart_and_load, 'prev'))
        self.file_menu.load_prev_action.setShortcuts(PALMS.shortcuts['restart_and_load_prev'])
        self.file_menu.addAction(self.file_menu.load_prev_action)

        self.file_menu.exit_action = QtWidgets.QAction('&Exit', self)
        self.file_menu.exit_action.triggered.connect(QtWidgets.qApp.quit)
        self.file_menu.exit_action.setShortcut(QtGui.QKeySequence.Quit)
        self.file_menu.exit_action.setMenuRole(QtWidgets.QAction.QuitRole)
        self.file_menu.exit_action.setStatusTip('Exit application')
        self.file_menu.addAction(self.file_menu.exit_action)

        # Track Menu
        self.track_menu = menu.addMenu('&Track')
        self.track_menu.setToolTipsVisible(True)

        remove_action = QtWidgets.QAction("&Delete", self)
        remove_action.setToolTip(tooltips.remove_track)
        remove_action.triggered.connect(self.guiDelView)
        remove_action.setShortcut(QtGui.QKeySequence(PALMS.shortcuts['remove_track']))
        self.track_menu.addAction(remove_action)

        self.track_menu.addSeparator()

        # Panel Menu
        panel_menu = menu.addMenu('&Panel')
        panel_menu.setToolTipsVisible(True)

        add_action = QtWidgets.QAction('&New Panel', self, enabled=False)
        add_action.setToolTip(tooltips.add_panel)
        add_action.triggered.connect(self.guiAddPanel)
        add_action.setShortcut(PALMS.shortcuts['new_panel'])
        add_action.setStatusTip('Add Panel')
        panel_menu.addAction(add_action)

        remove_action = QtWidgets.QAction("&Close Panel", self, enabled=True)
        remove_action.setToolTip(tooltips.remove_panel)
        remove_action.triggered.connect(self.delItem)
        remove_action.setShortcut(PALMS.shortcuts['close_panel'])
        remove_action.setStatusTip('Remove panel')
        panel_menu.addAction(remove_action)

        panel_menu.addSeparator()
        move_panel_up = QtWidgets.QAction("Move Up", self)
        move_panel_up.setShortcut(PALMS.shortcuts['move_up'])
        move_panel_up.triggered.connect(self.moveUp)
        panel_menu.addAction(move_panel_up)

        move_panel_down = QtWidgets.QAction("Move Down", self)
        move_panel_down.setShortcut(PALMS.shortcuts['move_down'])
        move_panel_down.triggered.connect(self.moveDown)
        panel_menu.addAction(move_panel_down)

        panel_menu.addSeparator()
        increase_size_action = QtWidgets.QAction('&Increase Height', self)
        increase_size_action.triggered.connect(self.increaseSize)
        increase_size_action.setShortcut(PALMS.shortcuts['increase_height'])
        increase_size_action.setToolTip(tooltips.increasePanelSize)
        panel_menu.addAction(increase_size_action)

        decrease_size_action = QtWidgets.QAction('&Decrease Height', self)
        decrease_size_action.triggered.connect(self.decreaseSize)
        decrease_size_action.setShortcut(PALMS.shortcuts['decrease_height'])
        decrease_size_action.setToolTip(tooltips.decresePanelSize)
        panel_menu.addAction(decrease_size_action)
        panel_menu.addSeparator()

        synchronize_action = QtWidgets.QAction('Synchronize', self, checkable=True, checked=self.synchronized, enabled=False)
        synchronize_action.setToolTip(tooltips.syncronize)
        synchronize_action.triggered.connect(self.changeSync)
        panel_menu.addAction(synchronize_action)
        panel_menu.addSeparator()
        toggleAll_action = QtWidgets.QAction('Hide all', self, checkable=False, enabled=True)
        toggleAll_action.setToolTip(tooltips.toggleAll)
        toggleAll_action.setShortcut(PALMS.shortcuts['toggle_all_views'])
        toggleAll_action.triggered.connect(self.toggleAll_action)
        panel_menu.addAction(toggleAll_action)

        # Navigation Menu
        navigation = menu.addMenu('&Navigation')
        # these changes applies to current panel
        # (and thus globally if synchronization is on)
        play_pause_action = QtWidgets.QAction('Play/Pause', self)
        play_pause_action.triggered.connect(self.play_pause)
        play_pause_action.setShortcut(PALMS.shortcuts['play_pause'])
        navigation.addAction(play_pause_action)

        shift_left_action = QtWidgets.QAction("Move &Left", self)
        shift_left_action.triggered.connect(self.shiftLeft)
        shift_left_action.setShortcut(PALMS.shortcuts['move_left'])
        navigation.addAction(shift_left_action)

        move_right_action = QtWidgets.QAction("Move &Right", self)
        move_right_action.triggered.connect(self.shiftRight)
        move_right_action.setShortcut(PALMS.shortcuts['move_right'])
        move_right_action.setStatusTip("Shift plot half a window to the right")
        navigation.addAction(move_right_action)

        goto_start_action = QtWidgets.QAction("Go to &Beginning", self)
        goto_start_action.triggered.connect(self.goToBeginning)
        goto_start_action.setShortcut(PALMS.shortcuts['goto_start'])
        navigation.addAction(goto_start_action)

        goto_end_action = QtWidgets.QAction("Go to &End", self)
        goto_end_action.triggered.connect(self.goToEnd)
        goto_end_action.setShortcut(PALMS.shortcuts['goto_end'])
        navigation.addAction(goto_end_action)

        navigation.addSeparator()

        zoom_in_action = QtWidgets.QAction("Zoom &In", self)
        zoom_in_action.triggered.connect(self.zoomIn)
        zoom_in_action.setShortcut(PALMS.shortcuts['zoom_in'])
        navigation.addAction(zoom_in_action)

        zoom_out_action = QtWidgets.QAction("Zoom &Out", self)
        zoom_out_action.triggered.connect(self.zoomOut)  # no overlap
        zoom_out_action.setShortcut(PALMS.shortcuts['zoom_out'])
        navigation.addAction(zoom_out_action)

        # NB: this works only for single panel, and is quite useless, so switch it off
        # zoom_to_match_action = QtWidgets.QAction("Zoom to &1:1", self)
        # zoom_to_match_action.setShortcut(PALMS.shortcuts['zoom_to_match'])
        # zoom_to_match_action.triggered.connect(self.zoomToMatch)
        # navigation.addAction(zoom_to_match_action)

        zoom_fit_action = QtWidgets.QAction("Zoom to &Fit", self)
        zoom_fit_action.setShortcut(PALMS.shortcuts['zoom_to_fit'])
        zoom_fit_action.triggered.connect(self.zoomFit)  # show all
        navigation.addAction(zoom_fit_action)

        # annotation menu
        self.annotation_menu = menu.addMenu('&Annotation')
        self.annotation_menu.setToolTipsVisible(True)

        self.annotation_menu.addSection('Modes')
        self.annotation_menu.annotationMode_action = QtWidgets.QAction('Annotation Mode', self, checkable=True, checked=False, enabled=True)
        self.annotation_menu.annotationMode_action.setToolTip(tooltips.annotationMode)
        self.annotation_menu.annotationMode_action.setShortcut(PALMS.shortcuts['annotation_mode'])
        self.annotation_menu.annotationMode_action.triggered.connect(partial(Mode.switch_mode, Modes.annotation))
        self.annotation_menu.addAction(self.annotation_menu.annotationMode_action)

        self.annotation_menu.partitionMode_action = QtWidgets.QAction('Partition Mode', self, checkable=True, checked=False, enabled=True)
        self.annotation_menu.partitionMode_action.setToolTip(tooltips.partitionMode)
        self.annotation_menu.partitionMode_action.setShortcut(PALMS.shortcuts['partition_mode'])
        self.annotation_menu.partitionMode_action.triggered.connect(partial(Mode.switch_mode, Modes.partition))
        self.annotation_menu.addAction(self.annotation_menu.partitionMode_action)

        self.annotation_menu.epochMode_action = QtWidgets.QAction('Epoch Mode', self, checkable=True, checked=False, enabled=True)
        self.annotation_menu.epochMode_action.setToolTip(tooltips.epochMode)
        self.annotation_menu.epochMode_action.setShortcut(PALMS.shortcuts['epoch_mode'])
        self.annotation_menu.epochMode_action.triggered.connect(partial(Mode.switch_mode, Modes.epoch))
        self.annotation_menu.addAction(self.annotation_menu.epochMode_action)

        self.annotation_menu.browseMode_action = QtWidgets.QAction('Browse Mode', self, checkable=True, checked=False, enabled=True)
        self.annotation_menu.browseMode_action.setShortcut(PALMS.shortcuts['browse_mode'])
        self.annotation_menu.browseMode_action.setToolTip(tooltips.browseMode)
        self.annotation_menu.browseMode_action.triggered.connect(partial(Mode.switch_mode, Modes.browse))
        self.annotation_menu.addAction(self.annotation_menu.browseMode_action)

        self.annotation_menu.addSeparator()
        self.annotation_menu.addSection('Annotation')
        self.annotation_menu.annotationConfig_action = QtWidgets.QAction('Config', self)
        self.annotation_menu.annotationConfig_action.setToolTip(tooltips.annotation_config)
        self.annotation_menu.annotationConfig_action.setShortcut(PALMS.shortcuts['annotation_config'])
        self.annotation_menu.annotationConfig_action.triggered.connect(self.annotationConfig.show)
        self.annotation_menu.addAction(self.annotation_menu.annotationConfig_action)

        self.annotation_menu.sticky_fiducial_menu = QtWidgets.QMenu('"Sticky" Fiducial')
        self.annotation_menu.sticky_fiducial_menu.setToolTipsVisible(True)

        from logic.operation_mode.annotation import AnnotationConfig
        sticky_fiducial_menu_actions = []
        for f in AnnotationConfig.all_fiducials():
            action = QtWidgets.QAction(f, self, checkable=True, checked=False, enabled=True)
            action.setToolTip(tooltips.stickyFiducialMenu)
            action.triggered.connect(self.toggle_sticky_fiducial_checkboxes)
            sticky_fiducial_menu_actions.append(action)
            self.annotation_menu.sticky_fiducial_menu.addAction(action)
        self.annotation_menu.addMenu(self.annotation_menu.sticky_fiducial_menu)
        self.annotation_menu.sticky_fiducial_menu.setStatusTip('Avoid pressing keyboard button to annotate non-default fiducial')
        self.sticky_fiducial_popup_shortcut = QtWidgets.QShortcut(PALMS.shortcuts['sticky_fiducials_popup'], self)
        self.sticky_fiducial_popup_shortcut.activated.connect(self.raise_sticky_fiducial_popup)

        self.annotation_menu.addSection('Partitions')
        self.annotation_menu.partitionConfig_action = QtWidgets.QAction('Config', self, checkable=False, enabled=False)
        self.annotation_menu.partitionConfig_action.setToolTip(tooltips.partition_config)
        self.annotation_menu.partitionConfig_action.setShortcut(PALMS.shortcuts['partition_config'])
        self.annotation_menu.partitionConfig_action.triggered.connect(lambda: Dialog().warningMessage('NotImplemented'))
        self.annotation_menu.addAction(self.annotation_menu.partitionConfig_action)

        self.annotation_menu.addSeparator()
        self.annotation_menu.annotationSave_action = QtWidgets.QAction('Save', self)
        self.annotation_menu.annotationSave_action.setToolTip(tooltips.annotationSave)
        self.annotation_menu.annotationSave_action.triggered.connect(Database.get().save)
        self.annotation_menu.annotationSave_action.setShortcut(PALMS.shortcuts['save'])
        self.annotation_menu.addAction(self.annotation_menu.annotationSave_action)

        self.annotation_menu.annotationLoad_action = QtWidgets.QAction('&Load hdf5', self, enabled=True)
        self.annotation_menu.annotationLoad_action.setToolTip(tooltips.annotationLoad)
        self.annotation_menu.annotationLoad_action.triggered.connect(self.load_from_hdf5)
        self.annotation_menu.annotationLoad_action.setShortcut(PALMS.shortcuts['load'])
        self.annotation_menu.addAction(self.annotation_menu.annotationLoad_action)

        # other options
        self.settings_menu = menu.addMenu('&Settings')
        self.settings_menu.show_cursor_action = QtWidgets.QAction('Show Cursor', self, checkable=True, enabled=True)
        self.settings_menu.show_cursor_action.setChecked(PALMS.config['show_cursor'])
        self.settings_menu.show_cursor_action.triggered.connect(self.toggleCursorReadout)
        self.settings_menu.show_cursor_action.setToolTip(tooltips.showCursor)
        self.settings_menu.addAction(self.settings_menu.show_cursor_action)

        self.settings_menu.autoscale_y_action = QtWidgets.QAction('Autoscale Y-axis', self, checkable=True, enabled=True)
        self.settings_menu.autoscale_y_action.setChecked(PALMS.config['autoscale_y'])
        self.settings_menu.autoscale_y_action.triggered.connect(self.toggleAutoscaleY)
        self.settings_menu.autoscale_y_action.setToolTip(tooltips.autoscaleY)
        self.settings_menu.addAction(self.settings_menu.autoscale_y_action)

        self.settings_menu.toggle_xaxis_label_action = QtWidgets.QAction("Show X-Axis Label", self, checkable=True)
        self.settings_menu.toggle_xaxis_label_action.triggered.connect(self.toggleXAxis)
        self.settings_menu.toggle_xaxis_label_action.setChecked(PALMS.config['show_xaxis_label'])
        self.settings_menu.addAction(self.settings_menu.toggle_xaxis_label_action)

        self.settings_menu.save_tracks_action = QtWidgets.QAction('Save tracks with data', self, checkable=True, enabled=True)
        self.settings_menu.save_tracks_action.setToolTip(tooltips.save_tracks)
        self.settings_menu.save_tracks_action.setChecked(PALMS.config['save_tracks'])
        self.settings_menu.addAction(self.settings_menu.save_tracks_action)

        self.settings_menu.save_overwrite_action = QtWidgets.QAction('Overwrite .h5 files if any', self, checkable=True, checked=True,
                                                                     enabled=True)
        self.settings_menu.save_overwrite_action.setChecked(PALMS.config['save_overwrite'])
        self.settings_menu.save_overwrite_action.triggered.connect(self.toggleRewriteH5)
        self.settings_menu.save_overwrite_action.setToolTip(tooltips.save_overwrite)
        self.settings_menu.addAction(self.settings_menu.save_overwrite_action)

        self.setOperationMode.connect(self.toggle_mode)

        # help menu
        self.help_menu = menu.addMenu('Help')
        self.help_menu.open_doc_action = QtWidgets.QAction('User manual', self, enabled=True)
        self.help_menu.open_doc_action.setToolTip(tooltips.open_doc)
        self.help_menu.open_doc_action.triggered.connect(self.open_doc)
        self.help_menu.addAction(self.help_menu.open_doc_action)

        self.help_menu.shortcut_action = QtWidgets.QAction('Shortcuts', self, enabled=True)
        self.help_menu.shortcut_action.setShortcut(QtGui.QKeySequence('F1'))
        self.help_menu.shortcut_action.triggered.connect(self.help_popup.show)
        self.help_menu.addAction(self.help_menu.shortcut_action)

    def toggleAll_action(self):
        # TODO: it is here because when menus are created, there is no panel and selectedPanel yet
        # otherwise, can set callback directly to ...plot_area.hideAllViewsExceptMain()
        if self.selectedDisplayPanel is not None:
            self.selectedDisplayPanel.plot_area.toggleAllViewsExceptMain()

    def open_doc(self):
        try:
            from PyQt5.QtCore import QUrl
            ql = QtWidgets.QLabel('Help')
            path = resource_path(pathlib.Path('docs', 'user_manual.pdf'))
            url = bytearray(QUrl.fromLocalFile(path.as_posix()).toEncoded()).decode()
            text = "<a href={}>Reference Link> </a>".format(url)
            ql.setText(text)
            ql.setVisible(False)
            ql.setOpenExternalLinks(True)
            ql.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
            ql.linkActivated.emit('str')
            ql.move(0, 0)
            ql.show()
            mouseevent = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, QtCore.QPoint(0, 0), QtCore.Qt.LeftButton,
                                           QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
            ql.mousePressEvent(mouseevent)
            ql.hide()
            del ql
        except Exception as e:
            Dialog().warningMessage('Something went wrong while opening the document.\r\n'
                                    'You can continue your work.\r\n'
                                    'The error was: '+ str(e))

    def restart_app(self):
        result = QtWidgets.QMessageBox.question(self,
                                                "Confirm Restart...",
                                                "Do you want to save\overwrite and restart ?",
                                                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Abort)
        if result == QtWidgets.QMessageBox.Save or result==QtWidgets.QMessageBox.Discard:
            db = Database.get()

            if result == QtWidgets.QMessageBox.Save:
                db.save()
                qInfo('{} saved'.format(db.fullpath.stem))

            PALMS.NEXT_FILE = None
            # PALMS.PREV_FILE = PALMS.CURRENT_FILE  # after reboot there is no previous file
            from logic.operation_mode.annotation import AnnotationConfig
            AnnotationConfig.get().clear()
            Partitions.delete_all()
            self.REBOOT_APP = True
            QtGui.QGuiApplication.exit(PALMS.EXIT_CODE_REBOOT)

    def restart_and_load(self, next_or_prev):
        db = Database.get()
        PALMS.NEXT_FILE = db.get_next_database_file()
        PALMS.PREV_FILE = db.get_prev_database_file()

        db.save()
        qInfo('{} saved'.format(db.fullpath.stem))
        #TODO: add QmessageBox about Save/Discard here and a tickbox option "Dont ask again"

        if next_or_prev in ['N', 'n', 'next', 'NEXT', 'Next']:
            if PALMS.NEXT_FILE is None:
                qInfo('Thi is the last file in the database.\r\n Try File->Restart or File->Load Prev')
                return
        elif next_or_prev in ['P', 'p', 'prev', 'PREV', 'Prev']:
            if PALMS.PREV_FILE is None:
                qInfo('Thi is the first file in the database.\r\n Try File->Restart or File->Load Next')
                return

        # don't clear data before certain that restart will happen
        from logic.operation_mode.annotation import AnnotationConfig
        AnnotationConfig.get().clear()
        Partitions.delete_all()
        self.REBOOT_APP = True
        if next_or_prev in ['N', 'n', 'next', 'NEXT', 'Next']:
            QtGui.QGuiApplication.exit(PALMS.EXIT_CODE_LOAD_NEXT)
        elif next_or_prev in ['P', 'p', 'prev', 'PREV', 'Prev']:
            QtGui.QGuiApplication.exit(PALMS.EXIT_CODE_LOAD_PREV)

    def raise_sticky_fiducial_popup(self):
        pos = self.selectedDisplayPanel.plot_area.event_cursor_global_position
        if pos is not None:
            sticky_fiducial = self.annotation_menu.sticky_fiducial_menu.exec_(pos)
        else:
            sticky_fiducial = self.annotation_menu.sticky_fiducial_menu.exec_()

    def toggle_sticky_fiducial_checkboxes(self):
        sender = self.sender()
        for ch in self.annotation_menu.sticky_fiducial_menu.actions():
            if ch.isChecked() and ch != sender:
                ch.setChecked(False)

    def toggle_mode(self, mode: Modes):  # annotation and partition modes can not be both ON, but can be both OFF
        self.selectedDisplayPanel.plot_area.redraw_fiducials()
        for item in self.annotation_menu.sticky_fiducial_menu.actions():
            item.setChecked(False)
        EpochModeConfig.get().redraw_epochs()
        if mode == Modes.annotation:
            self.annotation_menu.annotationMode_action.setChecked(True)
            self.annotation_menu.partitionMode_action.setChecked(False)
            self.annotation_menu.epochMode_action.setChecked(False)
            self.annotation_menu.browseMode_action.setChecked(False)
            Partitions.unhide_all_partitions()
            # Partitions.hide_all_partitions()
            self.annotation_menu.annotationConfig_action.setEnabled(True)
            self.annotation_menu.sticky_fiducial_menu.setEnabled(True)
            self.annotation_menu.partitionConfig_action.setEnabled(False)
            EpochWindow.hide()
        elif mode == Modes.partition:
            self.annotation_menu.annotationMode_action.setChecked(False)
            self.annotation_menu.partitionMode_action.setChecked(True)
            self.annotation_menu.epochMode_action.setChecked(False)
            self.annotation_menu.browseMode_action.setChecked(False)
            Partitions.unhide_all_partitions()
            self.annotation_menu.annotationConfig_action.setEnabled(False)
            self.annotation_menu.sticky_fiducial_menu.setEnabled(False)
            self.annotation_menu.partitionConfig_action.setEnabled(True)
            EpochWindow.hide()
        elif mode == Modes.browse:
            self.annotation_menu.annotationMode_action.setChecked(False)
            self.annotation_menu.partitionMode_action.setChecked(False)
            self.annotation_menu.epochMode_action.setChecked(False)
            self.annotation_menu.browseMode_action.setChecked(True)
            Partitions.unhide_all_partitions()
            self.annotation_menu.annotationConfig_action.setEnabled(False)
            self.annotation_menu.sticky_fiducial_menu.setEnabled(False)
            self.annotation_menu.partitionConfig_action.setEnabled(False)
            EpochWindow.hide()
        elif mode == Modes.epoch:
            self.annotation_menu.annotationMode_action.setChecked(False)
            self.annotation_menu.partitionMode_action.setChecked(False)
            self.annotation_menu.epochMode_action.setChecked(True)
            self.annotation_menu.browseMode_action.setChecked(False)
            Partitions.hide_all_partitions()
            self.annotation_menu.annotationConfig_action.setEnabled(False)
            self.annotation_menu.sticky_fiducial_menu.setEnabled(False)
            self.annotation_menu.partitionConfig_action.setEnabled(False)
            x_min, x_max = PlotArea.get_main_view().renderer.vb.viewRange()[0]
            EpochWindow.move_current_window_to_x(x_min)
            PlotArea.get_main_view().renderer.plot_area.setFocus()
            # TODO: reset plot to window + overlap

    def load_from_hdf5(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load hdf5 with annotations", get_project_root().as_posix(), " (*.h5);",
                                                      options=QtWidgets.QFileDialog.Options())
        if fn:
            Database.get().load(fn)
        else:
            qInfo('Load canceled')

    def toggleAutoscaleY(self):
        self.autoscale_y = not self.autoscale_y
        self.autoscaleYstatus.emit(self.autoscale_y)

    def toggleRewriteH5(self):
        self.rewriteH5 = not self.rewriteH5
        self.rewriteH5Status.emit(self.rewriteH5)

    def toggleCursorReadout(self):
        self.cursor_readout = not self.cursor_readout
        self.cursorReadoutStatus.emit(self.cursor_readout)

    def getSelectedDisplayPanel(self) -> DisplayPanel:
        selected_index = self.model.panels.index(self.model.selected_panel)
        return self.frames[selected_index].displayPanel

    selectedDisplayPanel = property(getSelectedDisplayPanel)

    def getSelectedTrack(self) -> tracking.Track:
        panel = self.selectedPanel
        track = panel.selected_track()
        return track

    selectedTrack = property(getSelectedTrack)

    def getSelectedView(self) -> View:
        return self.selectedPanel.selected_view

    selectedView = property(getSelectedView)

    def viewRange(self, display_panel=None) -> Tuple[float, float]:
        if display_panel is None:
            display_panel = self.selectedDisplayPanel
            if display_panel is None:
                return 0., 1.
        view = display_panel.panel.selected_view
        if view is None:
            vb = display_panel.plot_area.main_vb
        else:
            vb = view.renderer.vb
        return vb.viewRange()[0]

    # TODO: when shifting by menu / keys, implement a *target* system,
    # where we are smoothly and exponentially scrolling to the desired target
    @Slot(name='pageRight')
    def pageRight(self):
        span = np.diff(self.viewRange())[0]
        self.translateBy(span)

    def translateBy(self, delta_x):
        # using multiple panels can cause unexpected behaviour, to avoid, we always switch to the panel with the main track
        for frame in self.frames:
            if frame.displayPanel.plot_area.is_main_view_in_current_panel():
                break
        self.selectFrame(frame)

        view = self.selectedView
        if view is None:
            return
        x_min, x_max = view.renderer.vb.viewRange()[0]
        if x_min < 0 and delta_x < 0:
            return
        self.applySync()
        view.renderer.vb.translateBy(x=delta_x)
        self.selectedDisplayPanel.plot_area.alignViews()
        if self.synchronized:
            reference_view_range = self.reference_plot.viewRange()[0]
            for frame in self.frames:
                frame_view_range = frame.displayPanel.plot_area.main_vb.viewRange()[0]  # assert reference_view_range == frame_view_range

    def scaleBy(self, mag_x):
        view = self.selectedView
        if view is None:
            return
        self.applySync()
        center = view.renderer.vb.targetRect().center()
        padding = view.renderer.vb.suggestPadding(pg.ViewBox.XAxis)
        proposed_ranges = [dim * mag_x for dim in view.renderer.vb.viewRange()[0]]
        if proposed_ranges[0] < -padding:
            shift_right = abs(proposed_ranges[0]) - padding
            center.setX(center.x() + shift_right)
        view.renderer.vb.scaleBy(x=mag_x, center=center)
        self.selectedDisplayPanel.plot_area.alignViews()
        # if self.synchronized:
        #     reference_view_range = self.reference_plot.viewRange()[0]
        #     try:
        #         assert all([reference_view_range == frame.displayPanel.plot_area.main_vb.viewRange()[0] for frame in self.frames])
        #     except Exception as e:
        #         if len(self.frames) > 1:
        #             Dialog().warningMessage('Exception occured\r\n'
        #                                     'Using more than one frame may have caused this!\r\n'
        #                                     'The error was: '+ str(e))
        #         else:
        #             Dialog().warningMessage('Exception occured\r\n' + str(e))

    def getSelectedPanel(self) -> Panel:
        return self.model.selected_panel

    def setSelectedPanel(self, panel: Panel):
        self.model.set_selected_panel(panel)

    selectedPanel = property(getSelectedPanel, setSelectedPanel)

    @Slot(name='pageLeft')
    def pageLeft(self):
        span = np.diff(self.viewRange())[0]
        self.translateBy(-span)

    @Slot(name='shiftRight')
    def shiftRight(self):
        if Mode.is_epoch_mode() and not EpochWindow.get().is_out_of_scope():
            EpochWindow.move_right()
        else:
            if self.selectedView is None:
                return
            x_min, x_max = self.viewRange()
            span = np.diff(self.viewRange())[0]
            if x_max > self.selectedView.panel.get_max_duration():
                return
            shift = span / 10
            self.translateBy(shift)

    @Slot(name='play_pause')
    def play_pause(self):
        if self.timer.isActive():
            self.timer.pause()
        else:
            self.timer.resume()

    @Slot(name='shiftLeft')
    def shiftLeft(self):
        if Mode.is_epoch_mode() and not EpochWindow.get().is_out_of_scope():
            EpochWindow.move_left()
        else:
            if self.selectedView is None:
                return
            vb = self.selectedPanel.selected_view.renderer.vb
            x_min, x_max = vb.viewRange()[0]
            padding = vb.suggestPadding(pg.ViewBox.XAxis)
            span = x_max - x_min
            shift = span / 10
            if x_min < 0:
                return
            elif x_min - shift < -padding:
                shift = max(x_min, padding)
            self.translateBy(-shift)

    @Slot(name='goToBeginning')
    def goToBeginning(self):
        x_min, x_max = self.viewRange()
        padding = self.selectedPanel.selected_view.renderer.vb.suggestPadding(1)
        self.translateBy(-x_min - padding)

    @Slot(name='goToEnd')
    def goToEnd(self):
        x_min, x_max = self.viewRange()
        view = self.selectedView
        if view is None:
            return
        track = view.track
        end_time = view.track.duration / view.track.fs
        self.translateBy(end_time - x_max)

    @Slot(name='zoomFit')
    def zoomFit(self):
        view = self.selectedView
        if view is None:
            return
        track = view.track
        max_t = track.duration / track.fs
        span = np.diff(view.renderer.vb.viewRange()[0])[0]
        self.scaleBy(max_t / span)
        self.goToBeginning()

    @Slot(name='zoomToMatch')
    def zoomToMatch(self):
        """
        where each pixel represents exactly one sample at the
        highest-available sampling-frequency
        :return:
        """
        view = self.selectedPanel.selected_view
        if view is None:
            return
        vb = view.renderer.vb
        pixels = vb.screenGeometry().width()
        mag_span = pixels / self.selectedTrack.fs
        span = np.diff(self.viewRange())[0]
        mag = mag_span / span
        self.scaleBy(mag)

    @Slot(name='zoomIn')
    def zoomIn(self):
        """
        In AnnotationMode and PartitionMode: Up and Down execute regular zoom operation
        In EpochMode: Up and Down make label change to next\prev, zoom can be done only by MouseWheel
        :return:
        """
        if Mode.is_epoch_mode() and not EpochWindow.get().is_out_of_scope():
            EpochModeConfig.get().current_window_upgrade_value()
        else:
            view = self.selectedPanel.selected_view
            if view is None:
                return
            vb = view.renderer.vb
            x_range = np.diff(vb.viewRange()[0])[0]
            minXRange = vb.getState()['limits']['xRange'][0]
            zoom = 0.9

            if x_range <= minXRange:
                return
            elif x_range * zoom < minXRange:
                zoom = minXRange / x_range
            self.scaleBy(zoom)

    @Slot(name='zoomOut')
    def zoomOut(self):
        if Mode.is_epoch_mode() and not EpochWindow.get().is_out_of_scope():
            EpochModeConfig.get().current_window_downgrade_value()
        else:
            view = self.selectedPanel.selected_view
            if view is None:
                return
            vb = view.renderer.vb
            x_range = np.diff(vb.viewRange()[0])
            maxXRange = vb.getState()['limits']['xLimits'][1] - vb.getState()['limits']['xLimits'][0]
            zoom = 1.1

            if x_range >= maxXRange:
                return
            elif x_range * zoom > maxXRange:
                zoom = maxXRange / x_range
            self.scaleBy(zoom)

    @Slot(name='increaseSize')
    def increaseSize(self):
        self.selected_frame.increaseSize()

    @Slot(name='decreaseSize')
    def decreaseSize(self):
        self.selected_frame.decreaseSize()

    def status(self, msg: str, timeout: int = 5000):
        self.statusBar().showMessage(msg, timeout)

    def joinGroup(self, view):
        group = self.groups[id(view.track)]
        group.join(view)

    def changeSync(self):
        self.synchronized = not self.synchronized
        self.reference_plot = self.selectedDisplayPanel.plot_area.main_vb
        self.applySync()

    def applySync(self):
        if self.synchronized:
            self.synchronize()
        else:
            self.desynchronize()

    def synchronize(self):
        self.reference_plot = self.selectedDisplayPanel.plot_area.main_vb
        assert isinstance(self.reference_plot, pg.ViewBox)
        x_min, x_max = self.reference_plot.viewRange()[0]
        for frame in self.frames:
            if frame.displayPanel.plot_area.main_vb is self.reference_plot:
                continue
            frame.displayPanel.plot_area.main_vb.setXLink(self.reference_plot)
            if frame.displayPanel.panel.selected_view:
                frame.displayPanel.panel.selected_view.renderer.vb.setXRange(x_min, x_max, padding=0)

    def desynchronize(self):
        self.reference_plot = None
        for frame in self.frames:
            frame.displayPanel.plot_area.main_vb.setXLink(frame.displayPanel.plot_area.main_vb)

    def toggleXAxis(self):
        PALMS.config['show_xaxis_label'] = not PALMS.config['show_xaxis_label']
        for frame in self.frames:
            frame.displayPanel.plot_area.axis_bottom.showLabel(PALMS.config['show_xaxis_label'])

    def createNewPanel(self, pos=None):
        frame = Frame(main_window=self)
        w = DisplayPanel(frame=frame)
        w.plot_area.setAxesWidths(self.axis_width)
        self.queryAxesWidths.connect(w.plot_area.updateWidestAxis)
        self.setAxesWidth.connect(w.plot_area.setAxesWidths)
        self.moveSplitterPosition.connect(w.setSplitterPosition)
        self.setSplitter.connect(w.table_splitter.setSizes_)
        self.setColWidths.connect(w.view_table.setColumnWidths)
        self.queryColWidths.connect(w.view_table.calcColumnWidths)

        w.table_splitter.setSizes([1, w.view_table.viewportSizeHint().width()])
        frame.layout.addWidget(w)
        frame.displayPanel = w
        if pos is not None:
            insert_index = pos
        elif self.selected_frame:
            insert_index = self.frames.index(self.selected_frame) + 1
        else:
            insert_index = None
        panel = self.model.new_panel(pos=insert_index)
        w.loadPanel(panel)
        self.addFrame(frame, insert_index)
        self.applySync()

    def delItem(self):
        if self.selected_frame is None:
            logging.debug('no frame is selected for debug')
            return
        remove_index = self.frames.index(self.selected_frame)
        self.model.remove_panel(remove_index)
        self.removeFrame(self.selected_frame)
        if not self.frames:
            self.selected_frame = None
            self.reference_plot = None
            self.guiAddPanel()
            self.selectFrame(self.frames[-1])
        elif remove_index == len(self.frames):
            self.selectFrame(self.frames[-1])
        else:
            self.selectFrame(self.frames[remove_index])
        self.applySync()

    @Slot(int, name='viewMoved')
    def viewMoved(self, panel_index):
        view_to_add = self.model.panels[panel_index].views[-1]
        self.frames[panel_index].displayPanel.view_table.addView(view_to_add, setColor=False)

    def addFrame(self, frame: Frame, index=None):
        if not index:
            index = len(self.frames)
        self.frames.insert(index, frame)
        self.scrollAreaWidgetContents.layout.insertWidget(index, frame)
        self.updateFrames()

    def removeFrame(self, frame_to_remove: Frame):
        if frame_to_remove.displayPanel.plot_area.main_vb is self.reference_plot:
            self.reference_plot = None
        self.frames.remove(frame_to_remove)
        self.scrollAreaWidgetContents.layout.removeWidget(frame_to_remove)
        frame_to_remove.deleteLater()
        self.updateFrames()

    def updateFrames(self):
        self.scrollArea.updateGeometry()
        for panel, frame in zip(self.model.panels, self.frames):
            frame.displayPanel.handle.updateLabel()
            assert frame.displayPanel.panel == panel

    def swapFrames(self, positions: Tuple[int, int]):
        self.scrollAreaWidgetContents.swapWidgets(positions)
        self.frames[positions[0]], self.frames[positions[1]] = self.frames[positions[1]], self.frames[positions[0]]
        self.model.panels[positions[0]], self.model.panels[positions[1]] = self.model.panels[positions[1]], self.model.panels[positions[0]]
        self.updateFrames()

    @Slot(list, name='determineColumnWidths')
    def determineColumnWidths(self, widths: List[int]):
        if not self.all_column_widths:
            self.all_column_widths = [{self.sender(): width} for width in widths]
        else:
            for index, width in enumerate(widths):
                self.all_column_widths[index][self.sender()] = width

        self.column_width_hint = [max(column.values()) for column in self.all_column_widths]
        self.setColWidths.emit(self.column_width_hint)
        self.moveSplitterPosition.emit()

    @Slot(name='moveUp')
    def moveUp(self):
        index = self.frames.index(self.selected_frame)
        if index == 0:
            return
        self.swapFrames((index, index - 1))

    @Slot(name='moveDown')
    def moveDown(self):
        index = self.frames.index(self.selected_frame)
        if index == len(self.frames) - 1:
            return
        self.swapFrames((index, index + 1))

    @Slot(name='selectNext')
    def selectNext(self):
        index = self.frames.index(self.selected_frame)
        if index == len(self.frames) - 1:
            return
        else:
            self.selectFrame(self.frames[index + 1])

    @Slot(name='selectPrevious')
    def selectPrevious(self):
        index = self.frames.index(self.selected_frame)
        if index == 0:
            return
        else:
            self.selectFrame(self.frames[index - 1])

    @Slot(QtWidgets.QFrame, name='selectFrame')
    def selectFrame(self, frame_to_select: Frame):
        assert isinstance(frame_to_select, Frame)
        assert frame_to_select in self.frames
        if self.selected_frame is not None:
            self.selected_frame.resetStyle()
        self.selected_frame = frame_to_select
        self.selected_frame.setFocus(QtCore.Qt.ShortcutFocusReason)
        self.selected_frame.setStyleSheet("""
        Frame {
            border: 3px solid red;
        }
        """)
        index = self.frames.index(self.selected_frame)
        self.model.set_selected_panel(self.model.panels[index])
        if self.synchronized and self.reference_plot is None:
            self.reference_plot = self.selectedDisplayPanel.plot_area.main_vb
        self.evalTrackMenu()
        selected_frame_index = self.frames.index(frame_to_select)
        selected_panel_index = self.model.panels.index(self.selectedPanel)
        assert selected_frame_index == selected_panel_index

    @Slot(QtWidgets.QFrame, name='frameToMove')
    def frameToMove(self, frame_to_move: Frame):
        self.from_index = self.frames.index(frame_to_move)

    @Slot(QtWidgets.QFrame, name='whereToInsert')
    def whereToInsert(self, insert_here: Frame):
        self.to_index = self.frames.index(insert_here)
        if self.to_index == self.from_index:
            self.from_index = self.to_index = None
            return
        self.moveFrame()

    def moveFrame(self):
        if self.to_index is None or self.from_index is None:
            logging.debug('To and/or From index not set properly')
            return
        frame = self.frames[self.from_index]
        self.scrollAreaWidgetContents.layout.removeWidget(frame)
        self.frames.insert(self.to_index, self.frames.pop(self.from_index))
        self.model.move_panel(self.to_index, self.from_index)
        self.scrollAreaWidgetContents.layout.insertWidget(self.to_index, frame)
        self.selectFrame(self.frames[self.to_index])
        self.updateFrames()
        # Resetting moving parameters
        self.from_index = self.to_index = None

    @Slot(name='moveToEnd')
    def moveToEnd(self):
        self.frameToMove(self.selected_frame)
        self.to_index = len(self.frames) - 1
        self.moveFrame()

    @Slot(name='checkAxesWidths')
    def checkAxesWidths(self):
        widths = [axis.preferredWidth() for frame in self.frames for axis in frame.displayPanel.plot_area.axes.values()]
        if not widths:
            return
        axis_width = max(widths)
        if axis_width != self.axis_width:
            self.axis_width = axis_width
            self.setAxesWidth.emit(self.axis_width)

    @Slot(name='invertView')
    def invertViewView(self):
        #NB: not implemented
        """ invert the track, the view, annotations' Y-data, limits, etc."""
        if self.selectedView is None:
            return
        try:
            return
            self.selectedView.track.invert()
        except Exception as e:
            Dialog().warningMessage('Inverting signal failed\r\n' + str(e))


    @Slot(name='guiDelView')
    def guiDelView(self):
        """identifies the selected view and removes it"""
        if self.selectedView is None:
            return
        if self.selectedView.track.label is Database.get().main_track_label:
            Dialog().warningMessage('It is not possible to delete the main ({}) track'.format(Database.get().main_track_label))
            return
        view_to_remove = self.selectedView
        self.selectedDisplayPanel.removeViewFromChildren(view_to_remove)
        self.selectedDisplayPanel.delViewFromModel(view_to_remove)
        self.evalTrackMenu()
        AnnotationConfigDialog.get().reset_pinned_to_options_to_existing_views()

    def setTrackMenuStatus(self, enabled):
        ignore_actions = ["New Partition", "Open"]  # TODO: hate this...
        for action in self.track_menu.actions():
            if any([ignore_str in action.text() for ignore_str in ignore_actions]):
                continue
            else:
                action.setEnabled(enabled)

    def evalTrackMenu(self):
        self.setTrackMenuStatus(bool(self.selectedPanel.views))

    def closeEvent(self, event):
        if not self.REBOOT_APP:  # the app is restarting, thus a dialog already appeared
            result = QtWidgets.QMessageBox.question(self,
                                                    "Confirm Exit...",
                                                    "Are you sure you want to exit ?",
                                                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        else:
            result = QtWidgets.QMessageBox.Yes

        event.ignore()

        if result == QtWidgets.QMessageBox.Yes:
            self.annotationConfig.close()
            self.help_popup.close()
            self.processorConfig.close()
            event.accept()


class PALMS(object):  # Application - here's still the best place for it methinks
    EXIT_CODE_REBOOT = -123
    EXIT_CODE_LOAD_NEXT = 1
    EXIT_CODE_LOAD_PREV = -1
    PREV_FILE = None
    CURRENT_FILE = None
    NEXT_FILE = None
    _instance = None
    config = config.default_config
    shortcuts = None

    def __init__(self, file_to_load: Path = None, **kwargs):
        start = timer()
        # sys.argv[0] = 'PALMS'  # to override Application menu on OSX
        QtCore.qInstallMessageHandler(self._log_handler)
        QtWidgets.QApplication.setDesktopSettingsAware(False)
        self.qtapp = qtapp = QtWidgets.QApplication(sys.argv)
        qtapp.setStyle("fusion")
        qtapp.setApplicationName("PALMS")
        qtapp.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
        if hasattr(QtWidgets.QStyleFactory, 'AA_UseHighDpiPixmaps'):
            qtapp.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

        try:
            with open(config.CONFIG_PATH) as file:
                PALMS.config.update(json.load(file))
            with open(config.SHORTCUTS_PATH) as file:
                PALMS.shortcuts = json.load(file)
        except IOError:
            logging.debug('cannot find saved configuration, using default configuration')

        db_name = self.config.get('prev_database', None)
        mode = self.config.get('default_mode', Modes.annotation.value)

        if (file_to_load is not None) and (db_name is not None) and (db_name in ALL_DATABASES):
            try:
                db = getattr(sys.modules[DATABASE_MODULE_NAME], db_name).__call__()
                self.initialize_new_file(file_to_load)
            except Exception as e:
                Dialog().warningMessage(
                    'Loading requested file {} failed with \r\n {} \r\nPlease select a file manually'.format(file_to_load, str(e)))
                self.request_user_input_database_and_file()
                self.initialize_new_file(PALMS.CURRENT_FILE)

        else:
            self.request_user_input_database_and_file()
            self.initialize_new_file(PALMS.CURRENT_FILE)


        if mode not in Mode.all_modes():
            mode = Modes.annotation.value
        Mode.switch_mode(Modes[mode])
        # self.viewer.getSelectedDisplayPanel().plot_area.sigScaleChanged.emit(self.viewer.getSelectedDisplayPanel().plot_area)

        x_min, x_max = self.viewer.getSelectedView().track.get_time()[[0,-1]]
        self.viewer.getSelectedView().renderer.vb.setXRange(x_min, x_max,padding=0)
        finish = timer()
        PALMS._instance = weakref.ref(self)()
        qDebug(f'complete startup time is {finish - start:{0}.{3}} seconds')

    def request_user_input_database_and_file(self):
        selectFile = SelectFileDialog(self.config.get('prev_database', None))
        accepted = selectFile.exec()
        if accepted and selectFile.selected_files[0]:
            db = selectFile.db
            PALMS.CURRENT_FILE = selectFile.selected_files[0]
        else:
            Dialog().warningMessage('No file selected. Closing the app.')
            sys.exit(accepted)

    def initialize_new_file(self, filepath: Path):
        PALMS.CURRENT_FILE = filepath
        db = Database.get()
        try:
            db.get_data(filepath.as_posix())
        except Exception as e:
            Dialog().warningMessage(
                'get_data() method failed on {} with \r\n'.format(filepath.name) +
                str(e) +
                '\r\nCheck your data or get_data() method implementation.')
            sys.exit(1)
        db.set_annotation_config()
        db.set_epochMode_config()
        db.set_annotation_data()

        self.viewer = Viewer(self)
        for i, s in enumerate(db.tracks_to_plot_initially):
            self.add_view_from_track(db.tracks[s], 0)

        try:
            file_idx = Database.get().get_all_files_in_database().index(filepath) + 1
            n_files = len(Database.get().get_all_files_in_database())
            progress_str = str(file_idx) + '/' + str(n_files)
        except:
            progress_str = ''
        self.viewer.setWindowTitle(filepath.as_posix() + ' ' + progress_str)
        self.viewer.selectedDisplayPanel.plot_area.redraw_fiducials()

        from logic.operation_mode.annotation import AnnotationConfig
        self.viewer.get().annotationConfig.aConf_to_table(AnnotationConfig.get())

    @staticmethod
    def update_config():
        PALMS.config.update({'viewer_window_size': [PALMS.get().viewer.width(), PALMS.get().viewer.height()]})
        PALMS.config.update({'prev_database': Database.get().name})
        PALMS.config.update({'autoscale_y': PALMS.get().viewer.settings_menu.autoscale_y_action.isChecked()})
        PALMS.config.update({'save_tracks': PALMS.get().viewer.settings_menu.save_tracks_action.isChecked()})
        PALMS.config.update({'save_overwrite': PALMS.get().viewer.settings_menu.save_overwrite_action.isChecked()})
        PALMS.config.update({'default_mode': Mode.current_mode_name()})

    @staticmethod
    def get():
        return PALMS._instance

    @staticmethod
    def _log_handler(msg_type, msg_log_context, msg_string):
        if msg_type == 1:
            if re.match("QGridLayoutEngine::addItem: Cell \\(\\d+, \\d+\\) already taken", msg_string):
                return
            logger.warning(msg_string)
        elif msg_type == 2:
            logger.critical(msg_string)
        elif msg_type == 3:
            logger.error(msg_string)
        elif msg_type == 4:
            logger.info(msg_string)
        elif msg_type == 0:
            logger.debug(msg_string)
        else:
            logger.warning(f'received unknown message type from qt system with contents {msg_string}')
        try:
            Viewer.get().status(msg_string)
        except:
            pass

    def start(self):
        self.viewer.show()
        self.viewer.selectedDisplayPanel.plot_area.toggleAllViewsExceptMain()
        exit_code = self.qtapp.exec_()
        file_to_load = None
        if exit_code == PALMS.EXIT_CODE_LOAD_NEXT:
            file_to_load = PALMS.NEXT_FILE
        elif exit_code == PALMS.EXIT_CODE_LOAD_PREV:
            file_to_load = PALMS.PREV_FILE

        self.update_config()
        with open(config.CONFIG_PATH, 'w') as file:
            json.dump(PALMS.config, file, indent=4)

        return (exit_code, file_to_load)

    def _exit(self, status):
        self.update_config()
        with open(config.CONFIG_PATH, 'w') as file:
            json.dump(PALMS.config, file, indent=4)
        self.qtapp.closeAllWindows()
        del self.viewer
        del self.qtapp

    def add_view(self, track_obj: tracking.Track, panel_index: int = None, renderer_name: Optional[str] = None, *args, **kwargs):
        if isinstance(panel_index, int) and panel_index >= len(self.viewer.frames):
            for pos in range(len(self.viewer.frames), panel_index + 1):
                self.viewer.guiAddPanel()
                self.viewer.selectFrame(self.viewer.frames[pos])
        self.viewer.selectedDisplayPanel.createViewWithTrack(track_obj, renderer_name, **kwargs)

    def add_view_from_track(self, track, panel_index: int = None):
        parent_view = self.viewer.selectedView
        self.add_view(track, panel_index=panel_index, y_min=track.minY, y_max=track.maxY, x_min=track.minX,
                      x_max=Database.get().get_longest_track_duration())
        if parent_view is not None:
            self.viewer.selectedDisplayPanel.selectView(parent_view)
