"""
Copyright (c) 2005-2017 TimeView Developers
MIT license (see in gui\LICENSE.txt)
"""

import logging
import sys
from functools import partial
from math import ceil
from typing import Dict, Optional

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import qInfo, qDebug, qWarning
from PyQt5.QtWidgets import QInputDialog
from qtpy import QtGui, QtWidgets, QtCore
from qtpy.QtCore import Slot, Signal
from setuptools.package_index import unique_everseen

from logic.databases.DatabaseHandler import Database
from logic.operation_mode.annotation import AnnotationConfig
from logic.operation_mode.epoch_mode import EpochModeConfig
from logic.operation_mode.operation_mode import Modes, Mode
from logic.operation_mode.partitioning import SinglePartition, Partitions
from utils.QTimerWithPause import QTimerWithPause
from utils.utils_general import find_closest
from utils.utils_gui import Dialog
from .model import View

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

icon_color = QtGui.QColor('#00897B')


class PlotArea(pg.GraphicsView):
    maxWidthChanged = Signal(name='maxWidthChanged')
    signal_annotation_added = Signal(float, float, str, name='signal_annotation_added')
    signal_annotation_deleted = Signal(float, float, str, name='signal_annotation_deleted')
    last_keypress_event_key = None

    wheelEventsCounter = 0

    @classmethod
    def reset_wheelEvents(cls):
        cls.wheelEventsCounter = 0

    # mouseWheelTimer.timeout.connect(PlotArea.reset_wheelEvents)

    def __init__(self, display_panel):
        from gui import PALMS
        super().__init__()
        self.display_panel = display_panel
        self.main_window = self.display_panel.main_window
        # Layout
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.layout = pg.GraphicsLayout()
        self.layout.layout.setColumnFixedWidth(0, self.main_window.axis_width)
        # self.setBackground('w')
        # Variables
        self.axes: Optional[Dict[View, pg.AxisItem]] = {}
        self.vbs: Optional[Dict[View, pg.ViewBox]] = {}

        self.main_plot = pg.PlotItem(enableMenu=False)
        self.main_plot.hideButtons()
        self.main_plot.hideAxis('left')
        self.main_plot.hideAxis('bottom')
        self.main_plot.temporary_items = []

        self.main_vb: pg.ViewBox = self.main_plot.getViewBox()
        self.main_vb.sigXRangeChanged.connect(self.zoomChanged)
        # self.main_vb.sigYRangeChanged.connect(self.setYRange)
        self.main_vb.setXRange(0, 1)
        self.main_vb.setYRange(0, 1)
        self.main_vb.setMouseEnabled(False, False)
        self.main_plot.setZValue(-sys.maxsize - 1)
        self.main_vb.enableAutoRange(axis=pg.ViewBox.XYAxes)
        self.axis_bottom = pg.AxisItem('bottom', parent=self.main_vb,
                                       showValues=False)  # ticks are disabled, because each view has separately created GridItem()
        # self.axis_bottom.setPen(pg.mkPen(color='k', width=1))
        self.axis_bottom.setLabel('time', units='s')
        self.axis_bottom.showLabel(PALMS.config['show_xaxis_label'])
        # self.axis_bottom.setFixedHeight(self.axis_bottom.height())
        self.label_cursor_position = pg.LabelItem(justify='left', color=[255, 255, 255, 0])
        self.event_cursor_global_position = None
        # Connections
        self.maxWidthChanged.connect(self.main_window.checkAxesWidths)
        self.main_vb.sigResized.connect(self.updateViews)
        self.main_window.cursorReadoutStatus.connect(self.setCursorReadout)

        # self.proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self.mouseMoved)
        self.buildLayout()
        self.setCursorReadout(self.main_window.cursor_readout)

        self.signal_annotation_added.connect(self.plot_vline)
        self.signal_annotation_deleted.connect(self.plot_vline)

        self.mouseWheelTimer = QTimerWithPause(interval=500)
        self.mouseWheelTimer.timeout.connect(self.reset_wheelEvents)
        self.mouseWheelTimer.resume()
        self.ALL_VIEWS_HIDDEN = False

    def buildLayout(self):
        self.setCentralWidget(self.layout)
        self.layout.addItem(self.main_plot, row=0, col=1)
        self.layout.addItem(self.label_cursor_position, row=0, col=1)
        self.layout.addItem(self.axis_bottom, row=1, col=1)
        self.axis_bottom.linkToView(self.main_vb)
        self.layout.layout.setRowStretchFactor(0, 1)
        self.layout.layout.setColumnStretchFactor(1, 1)
        self.layout.update()
        self.axis_bottom.hide()

    def setYRange(self):
        from gui.viewer import Viewer
        if self.selected_view() is None:
            return
        x_range_start, x_range_end = self.selected_view().renderer.vb.viewRange()[0]  # x_range
        # x_range_start, x_range_end = self.sender().viewRange()[0]  # x_range
        for view in self.vbs.keys():
            if view.show:
                if Viewer.get().autoscale_y:
                    ymin, ymax = view.track.get_yrange_between(x_range_start, x_range_end)
                else:
                    ymin, ymax = view.renderer.track.minY, view.renderer.track.maxY
                from gui import PALMS
                if PALMS.get() is not None:
                    view.renderer.vb.setYRange(min=ymin, max=ymax, padding=PALMS.get().config['yrange_margin'])  # padding==0: scale to [min;max]
                else:
                    view.renderer.vb.setYRange(min=ymin, max=ymax, padding=0.1)

    def wheelEvent(self, event: QtGui.QWheelEvent):
        # limit wheelevents to max N events in T seconds to avoid hanging GUI because of zooming in and out non-stop
        PlotArea.wheelEventsCounter = PlotArea.wheelEventsCounter + 1
        # print(PlotArea.wheelEventsCounter)
        if PlotArea.wheelEventsCounter > 3:
            qInfo('Zooming speed limited to optimize performance.')
            return

        super().wheelEvent(event)
        newRange = self.main_vb.viewRange()[0]
        if self.main_window.selectedView is not None:
            maxX = self.main_window.selectedView.panel.get_max_duration()
        else:
            return
        if newRange[-1] > maxX:
            newRange[-1] = maxX
        if newRange[0] < 0:
            newRange[0] = 0
        if newRange[0] == 0:
            self.main_vb.setXRange(newRange[0], newRange[1], padding=0)
        else:
            self.main_vb.setXRange(newRange[0], newRange[1])
        event.accept()

    def keyPressEvent(self, event):
        """
        #TODO: what else can be parametrized with keypresses?
        """
        if Mode.is_epoch_mode():
            # print((event.key(), event.text()))
            from logic.operation_mode.epoch_mode import EpochModeConfig
            EpochModeConfig.get().process_keypress(event.text())
        else:
            # save last pressed button to later decide which fiducial is to be marked
            self.last_keypress_event_key = (event.key(), event.text())
            qInfo('Key pressed: {}'.format(event.text()))
            event.accept()

    @Slot(float, float, str)
    def plot_vline(self, x, y, added_or_deleted):
        """
        add vline where an annotation is added or deleted, it will be deleted once the plot is updated
        # TODO: run a new singleShotTimer every time to autoremove vline even without moving the plot
        """
        if added_or_deleted not in ['added', 'deleted']:
            qWarning('Incorrect parameter to plot_vline')
            return
        self.redraw_fiducials()
        if added_or_deleted == 'added':
            line = pg.InfiniteLine(pos=x, angle=90, movable=False)
        elif added_or_deleted == 'deleted':
            line = pg.InfiniteLine(pos=x, angle=90, movable=False, pen=pg.mkPen('r', style=QtCore.Qt.DashLine, cosmetic=True))

        self.selected_view().renderer.vb.addItem(line)
        self.selected_view().renderer.vb.temporary_items.append(line)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """
        The following only has effect if the main track is selected in the track table view on the right
        Annotation mode:
            **LeftMouseButton** places a new fiducial. By default it is the first fiducial as set in the annotationConfig,
            unless before that a keyboard button was pressed corresponding to another fiducial or "sticky fiducial" mode is on.
            **RightMouseButton** removes the nearest fiducial (default), unless "sticky fiducial" mode is on. Keyboard has no effect
        Partition mode:
            **CTRL + LeftMouseButton** creates a new partition which takes 2% of the whole track duration or less to avoid overlapping
            partiotions;
            **CTRL + RightMouseButton** removes partition under the click
            **SHIFT + LeftMouseButton** to drag partition borders or move the partition. Repositioning is possible within the limits of
            neighboring partition. Moving the partition fully inside another one or reducing its size to 1 sample deletes the partition.
            #NOTE: creating partition of desired size directly by click and drag might not be that convenient and harder to implement
        Epoch mode:

        # NB: when adding\removing mouse click operations also adapt self.mouseReleaseEvent() and self.mouseMoveEvent()
        """

        def which_fiducial_to_add(last_keypress_event_key):
            from gui.viewer import Viewer
            # first check if 'sticky' fiducial option is enabled for one of the fiducials
            sticky_fiducial = [item.isChecked() for item in Viewer.get().annotation_menu.sticky_fiducial_menu.actions()]
            if any(sticky_fiducial):
                idx = np.argwhere(sticky_fiducial)[0]
                return AnnotationConfig.get().find_idx_by_name(Viewer.get().annotation_menu.sticky_fiducial_menu.actions()[idx[0]].text())
            # if 'sticky' fiducial option is off, check what key was pressed the last
            default_fiducial_idx = 0  # default: first fiducial
            if last_keypress_event_key is not None:
                qInfo('Last pressed: ' + str(last_keypress_event_key[1]))
                for fiducial_idx, f in enumerate(AnnotationConfig.get().fiducials):
                    if f.key.lower() == last_keypress_event_key[1].lower():
                        return fiducial_idx
                return default_fiducial_idx
            else:
                return default_fiducial_idx

        def which_fiducial_to_delete(click_x):
            from gui.viewer import Viewer
            # first check if 'sticky' fiducial option is enabled for one of the fiducials
            sticky_fiducial = [item.isChecked() for item in Viewer.get().annotation_menu.sticky_fiducial_menu.actions()]
            if any(sticky_fiducial):
                idx = np.argwhere(sticky_fiducial)[0]
                return AnnotationConfig.get().find_idx_by_name(Viewer.get().annotation_menu.sticky_fiducial_menu.actions()[idx[0]].text())

            dist = np.inf
            fiducial_name, fiducial_idx = None, None
            for f_idx, f in enumerate(AnnotationConfig.get().fiducials):
                if f.annotation.x.size > 0:
                    closest_idx, _, _ = find_closest(f.annotation.x, np.array([click_x]))
                    dist_new = abs(click_x - f.annotation.x[closest_idx])
                    if dist_new < dist:
                        dist = dist_new
                        fiducial_name, fiducial_idx = f.name, f_idx
            if not dist == np.inf:
                return fiducial_idx

        try:
            from gui.viewer import Viewer
            Viewer.get().selectFrame(self.display_panel.parent())  # first select the frame where the click was made

            if Mode.is_epoch_mode():
                EpochModeConfig.get().process_mouseclick(event)
                return

            vb = self.vbs[self.selected_view()]
            click_x = vb.mapSceneToView(event.pos()).x()
            if self.selected_view().track.label is Database.get().main_track_label:  # TODO: do this check properly and uniformly everywhere
                if Mode.is_annotation_mode():
                    if AnnotationConfig.get().is_valid():
                        if event.button() == QtCore.Qt.LeftButton:  # Left click to mark
                            fiducial_idx = which_fiducial_to_add(self.last_keypress_event_key)
                            AnnotationConfig.get().fiducials[fiducial_idx].annotation.signal_annotate.emit(click_x)
                        elif event.button() == pg.QtCore.Qt.RightButton:  # right click to delete
                            fiducial_idx = which_fiducial_to_delete(click_x)
                            if fiducial_idx is not None:
                                AnnotationConfig.get().fiducials[fiducial_idx].annotation.signal_delete_annotation.emit(click_x)
                            else:
                                qInfo('No annotation found to be deleted')
                        self.last_keypress_event_key = None  # need to press extra key every time to annotate secondary fiducial

                elif Mode.is_partition_mode():
                    if event.button() == QtCore.Qt.LeftButton:
                        if event.modifiers() == QtCore.Qt.ControlModifier:
                            self.create_new_partition(event)
                        else:
                            super().mousePressEvent(event)
                            qInfo('CTRL+Left: create region; SHIFT+Left: move region')  # event.accept()
                    elif event.button() == QtCore.Qt.RightButton:
                        if event.modifiers() == QtCore.Qt.ControlModifier:
                            p = Partitions.find_partition_by_point(click_x)
                            if p is not None:
                                p.region_deleted()  # event.accept()
                        elif event.modifiers() == QtCore.Qt.ShiftModifier:
                            p = Partitions.find_partition_by_point(click_x)
                            if p is not None:
                                self.partition_context_menu(event)
                            else:
                                qInfo('No partition found...CTRL+Right: delete region; SHIFT+Right: region context menu')
                        else:
                            super().mousePressEvent(event)
                            qInfo('CTRL+Right: delete region; SHIFT+Right: region context menu')
                    else:
                        super().mousePressEvent(event)
                elif Mode.mode == Modes.browse:
                    super().mousePressEvent(event)


            else:
                if not self.is_main_view_in_current_panel():  # click on a panel, without the main track
                    Dialog().warningMessage(
                        'Selected display panel does not contain the main track ({}).\r\n'.format(Database.get().main_track_label) +
                        'Try clicking on another display panel')
                else:  # click on a correct panel, but the main track is not selected
                    Dialog().warningMessage('Selected signal is not the main one.\r\n'
                                            'Click on the ''{}'' track in the control area on the right.'.format(Database.get().main_track_label))
                return
        except Exception as e:
            Dialog().warningMessage('Mouse click processing failed\r\n'
                                    'What unusual did you do?\r\n' + str(e))
            return

    def partition_context_menu(self, event):
        vb = self.vbs[self.selected_view()]
        click_x = vb.mapSceneToView(event.pos()).x()
        p = Partitions.find_partition_by_point(click_x)
        menu = QtWidgets.QMenu()
        action = QtWidgets.QAction('Clear annotations', self, enabled=True)
        action.triggered.connect(partial(Partitions.clear_annotations_in_this_partition, p))
        menu.addAction(action)
        temp = menu.exec_(event.globalPos().__add__(QtCore.QPoint(10, 10)))

    def create_new_partition(self, event):
        from gui.viewer import PALMS
        vb = self.vbs[self.selected_view()]
        click_x = vb.mapSceneToView(event.pos()).x()
        menu = QtWidgets.QMenu()
        existing_partition_names = list(unique_everseen(PALMS.config['default_partition_labels'] + Partitions.unique_labels()))
        menu.addActions([menu.addAction(n) for n in existing_partition_names])
        menu.addSeparator()
        menu.addAction('New Partition')
        new_partition_name = menu.exec_(event.globalPos().__add__(QtCore.QPoint(10, 10)))
        if new_partition_name is not None:
            new_name = new_partition_name.text()
            if new_name == 'New Partition':
                new_name, accepted = QInputDialog.getText(self, 'Partition name input', 'Enter new partition name:')
                if not accepted:
                    qWarning('Incorrect name')
                    return

            if Partitions.find_partition_by_point(click_x) is not None:
                qWarning('Choose different place or delete existing region')
            else:
                p = SinglePartition.from_click(new_name, click_x=click_x)
                vb.addItem(p)
                vb.addItem(p.label)
        event.accept()

    @Slot(bool, name='Set Cursor Readout')
    def setCursorReadout(self, enabled):
        if enabled:
            self.label_cursor_position.show()
        else:
            self.label_cursor_position.hide()
        self.layout.update()

    def update_cursor_info(self, event):
        if self.selected_view() not in self.vbs.keys():
            return
        vb = self.vbs[self.selected_view()]
        pos = event.pos()
        if not self.main_plot.sceneBoundingRect().contains(pos):
            return
        mousePoint = vb.mapSceneToView(pos)
        time = f"{mousePoint.x():12.5}"
        sample = int(ceil(mousePoint.x() * self.selected_view().track.fs))
        y = f"{mousePoint.y():+12.5}"  # always show sign
        self.label_cursor_position.setText("<span style=color: white> " f"t = {time}<br /> " f"x = {sample}<br />" f"y = {y}" f"</span>")

    def mouseMoveEvent(self, event):
        self.event_cursor_global_position = event.globalPos()
        if self.main_window.cursor_readout:
            self.update_cursor_info(event)
        if Mode.mode == Modes.annotation:
            event.accept()  # in annotation mode mouse move is not used
        elif Mode.mode == Modes.partition:
            if event.buttons() & QtCore.Qt.LeftButton:
                if event.modifiers == QtCore.Qt.NoModifier:  # just click
                    super().mouseMoveEvent(event)
                elif event.modifiers() in [QtCore.Qt.ControlModifier]:  # left click + CTRL: remove partition
                    pass
                elif event.modifiers() in [QtCore.Qt.ShiftModifier]:
                    super().mouseMoveEvent(event)  # delegate linearRegionItem move\drag to parent class
            elif event.buttons() & QtCore.Qt.RightButton:
                if event.modifiers() == QtCore.Qt.NoModifier:  # just click
                    super().mouseMoveEvent(event)
                elif event.modifiers() in [QtCore.Qt.ControlModifier]:  # right click + CTRL: remove partition
                    pass
                elif event.modifiers() in [QtCore.Qt.ShiftModifier]:  # context menu
                    pass
            else:
                super().mouseMoveEvent(event)
        elif Mode.mode == Modes.browse:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if Mode.mode == Modes.annotation:
            event.accept()
        elif Mode.mode == Modes.partition:
            if event.button() == QtCore.Qt.LeftButton:
                if event.modifiers == QtCore.Qt.NoModifier:  # just click
                    super().mouseReleaseEvent(event)
                elif event.modifiers() in [QtCore.Qt.ControlModifier]:  # left click + CTRL: remove partition
                    pass
                elif event.modifiers() in [QtCore.Qt.ShiftModifier]:
                    super().mouseReleaseEvent(event)  # delegate linearRegionItem move\drag to parent class
            elif event.button() == QtCore.Qt.RightButton:
                if event.modifiers() == QtCore.Qt.NoModifier:  # just click
                    super().mouseReleaseEvent(event)
                elif event.modifiers() in [QtCore.Qt.ControlModifier]:  # right click + CTRL: remove partition
                    pass
                elif event.modifiers() in [QtCore.Qt.ShiftModifier]:  # context menu
                    pass
        elif Mode.mode == Modes.browse:
            super().mouseReleaseEvent(event)

    @Slot(View, name='addView')
    def addView(self, view: View, forceRangeReset=None):
        qDebug(f'Adding {view.renderer.name}')
        if forceRangeReset is not None:
            rangeReset = forceRangeReset
        else:
            if len(self.main_window.model.panels) == 1:
                rangeReset = not (bool(self.vbs))
            else:
                rangeReset = False
        ax, vb = view.renderer.render(self)
        self.main_window.joinGroup(view)
        self.axes[view] = ax
        self.vbs[view] = vb
        self.updateWidestAxis()
        self.updateViews()
        if view.show is False:
            self.hideView(view)
        self.axis_bottom.show()
        # this fixes the bottom axis mirroring on macOS
        old_size = self.size()
        self.resize(QtCore.QSize(old_size.width() + 1, old_size.height()))
        self.resize(old_size)

        self.layout.update()
        if rangeReset:
            self.main_window.zoomFit()

    # TODO: problem, this method is called after a view_to_remove.renderer has
    # already changed in view_table.changeRenderer
    # this should be refactored, so this method here can call
    # view_to_remove.renderer.prepareToDelete() if such a method exists
    def removeView(self, view_to_remove: View):
        axis_to_remove = self.axes.pop(view_to_remove)
        vb_to_remove = self.vbs.pop(view_to_remove)
        assert isinstance(vb_to_remove, pg.ViewBox)
        assert isinstance(axis_to_remove, pg.AxisItem)
        self.layout.removeItem(vb_to_remove)
        del vb_to_remove
        if axis_to_remove in self.layout.childItems():
            view_to_remove.is_selected()
            self.layout.removeItem(axis_to_remove)
        if not self.axes:
            self.layout.layout.setColumnFixedWidth(0, self.main_window.axis_width)
        self.updateViews()
        self.updateWidestAxis()
        if not self.vbs:
            self.axis_bottom.hide()
        self.layout.update()

    def hideView(self, view_to_hide: View):
        self.vbs[view_to_hide].setXLink(None)
        self.vbs[view_to_hide].hide()
        axis = self.axes[view_to_hide]
        width = axis.width()
        axis.showLabel(show=False)
        axis.setStyle(showValues=False)
        axis.setWidth(w=width)
        self.main_vb.setFixedWidth(self.vbs[view_to_hide].width())

    def toggleAllViewsExceptMain(self):
        # TODO: make a method to get all views over all panels
        from logic.databases.DatabaseHandler import Database
        all_views = [v for v in self.main_window.selectedPanel.views]
        if self.ALL_VIEWS_HIDDEN:
            for v in all_views:
                v.show = True
                self.showView(v)
            self.ALL_VIEWS_HIDDEN = False
        else:
            for v in all_views:
                if not v.track.label is Database.get().main_track_label:
                    v.show = False
                    self.hideView(v)
            self.ALL_VIEWS_HIDDEN = True
        self.display_panel.view_table.update_showCheckbox_state()

    def showView(self, view_to_show: View):
        self.axes[view_to_show].showLabel(show=True)
        self.axes[view_to_show].setStyle(showValues=True)
        self.vbs[view_to_show].setXLink(self.main_vb)
        self.vbs[view_to_show].show()
        self.updateViews()

    @Slot(View, name='changeColor')
    def changeColor(self, view_object: View):
        view_object.renderer.changePen()

    @Slot(name='Align Views')
    def alignViews(self):
        x_min, x_max = self.selected_view().renderer.vb.viewRange()[0]
        for view, vb in self.vbs.items():
            if view.is_selected():
                continue
            vb.setXRange(x_min, x_max, padding=0)
        self.axis_bottom.setRange(x_min, x_max)

    @Slot(name='updateViews')
    def updateViews(self):
        from gui import PALMS
        if self.selected_view() is None or not self.main_vb.width() or not self.main_vb.height():
            return
        track = self.selected_view().track
        # set how far it is possible to zoom in: minXRange in pixels/sec with an additional factor to enable closer view on the signal
        minXRange = self.main_vb.screenGeometry().width() / track.fs / PALMS.config['min_xzoom_factor']
        x_min, x_max = self.main_vb.viewRange()[0]
        for view, view_box in self.vbs.items():
            view_box.blockSignals(True)
            if view_box.geometry() != self.main_vb.sceneBoundingRect():
                view_box.setGeometry(self.main_vb.sceneBoundingRect())
            view_box.setLimits(minXRange=minXRange)  # applying max zoom
            view_box.setXRange(x_min, x_max, padding=0)
            view_box.blockSignals(False)
        self.axis_bottom.setRange(x_min, x_max)

    def is_main_view_in_current_panel(self):
        from logic.databases.DatabaseHandler import Database
        main_track_label = Database.get().main_track_label
        return main_track_label in [s.track.label for s in self.display_panel.panel.views]

    @staticmethod
    def get_main_view():
        from gui.viewer import Viewer
        from logic.databases.DatabaseHandler import Database
        main_track_label = Database.get().main_track_label

        if Viewer.get() is None:
            return None
        for frame in Viewer.get().frames:
            all_views = [v for v in frame.displayPanel.panel.views]
            all_views_labels = [v.track.label for v in all_views]
            main_track_idx = all_views_labels.index(main_track_label) if main_track_label in all_views_labels else None
            if main_track_idx is not None:
                break
        if main_track_idx is None:  # in case main view is not created yet
            return None
        main_view = all_views[main_track_idx]
        return main_view

    def redraw_fiducials(self):
        if self.selected_view() is None:
            return
        main_view = PlotArea.get_main_view()
        if main_view is None:
            return
        main_track = main_view.renderer.track
        vb = main_view.renderer.vb

        for item in vb.temporary_items:
            vb.removeItem(item)
        vb.temporary_items.clear()
        x_min, x_max = self.main_vb.viewRange()[0]
        if Mode.mode in [Modes.annotation, Modes.browse, Modes.partition, Modes.epoch]:  # NB: change to disable drawing annotations in other modes
            if Mode.mode == Modes.epoch and EpochModeConfig.get().toggle_fiducials == False:
                return  # if EpochMode and Fiducials are switched off
            if hasattr(main_track, 'aConf'):
                aConf = AnnotationConfig.get()
                for a in aConf:
                    points_x, points_y = a.annotation.find_annotation_between_two_ts(x_min, x_max)
                    if points_x.size > 0 and points_y.size > 0:
                        loadedFiducials = pg.PlotDataItem(points_x, points_y, symbol=a.symbol, symbolSize=a.symbol_size, pen=None,
                                                          symbolPen=a.symbol_pen, name=a.name)
                        vb.addItem(loadedFiducials)
                        vb.temporary_items.append(loadedFiducials)

    def zoomChanged(self):
        try:  # this is to avoid redrawing if it is already zoomed out to max
            newRange = self.main_window.selectedView.renderer.vb.targetRange()[0]
            viewRange = self.main_window.selectedView.renderer.vb.viewRange()[0]
            # newRange = self.main_vb.viewRange()[0]
            if newRange[-1] >= Database.get().get_longest_track_duration() and newRange[0] <= 0:  # TODO what if offset not 0
                if self.FLAG_full_zoom_out:
                    return
                else:
                    self.FLAG_full_zoom_out = True
            else:
                self.FLAG_full_zoom_out = False
        except:
            pass

        if self.main_vb.geometry():
            try:
                pixel_width = self.main_vb.viewPixelSize()[0]
                self.main_vb.setLimits(xMin=-pixel_width)
                for vb in self.vbs.values():
                    vb.setLimits(xMin=-pixel_width)
                self.redraw_fiducials()
                if self.display_panel is not None and len(self.display_panel.panel.views) > 0:
                    self.setYRange()
                EpochModeConfig.get().redraw_epochs()
            except Exception as e:
                Dialog().warningMessage('Exception occured\r\n'
                                        'Using more than one frame may have caused this!\r\n' +
                                        str(e))

    @Slot(View, name='selectionChanged')
    def selectionChanged(self, selected_view: View):
        assert selected_view is self.selected_view()
        self.blockViewBoxSignals()
        old_axis = self.layout.getItem(0, 0)
        if old_axis in self.axes.values():
            self.layout.removeItem(old_axis)
        self.layout.addItem(self.vbs[self.selected_view()], row=0, col=1)
        self.layout.addItem(self.axes[self.selected_view()], row=0, col=0)
        self.unblockViewBoxSignals()

    def updateWidestAxis(self):
        self.maxWidthChanged.emit()

    def selected_view(self) -> View:
        if not self.display_panel.panel is None:
            return self.display_panel.panel.selected_view
        else:
            return None

    @Slot(float, name='setAxesWidths')
    def setAxesWidths(self, width: float):
        if not self.axes or width == 0:
            return
        for axis in self.axes.values():
            if axis.width() != width:
                axis.blockSignals(True)
                axis.setWidth(w=width)
                axis.blockSignals(False)
        self.layout.update()

    def blockViewBoxSignals(self):
        self.main_vb.blockSignals(True)
        for vb in self.vbs.values():
            vb.blockSignals(True)

    def unblockViewBoxSignals(self):
        self.main_vb.blockSignals(False)
        for vb in self.vbs.values():
            vb.blockSignals(False)
