"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""

import weakref
from itertools import cycle
from typing import List

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import qInfo
from PyQt5.QtGui import QFont

from logic.operation_mode.operation_mode import Mode, Modes
from utils.utils_gui import Dialog


class Index:
    idx: int = None

    def __init__(self, init_value: int):
        self.idx = init_value

    def increase(self):
        if self.idx < EpochModeConfig.get().window_data.shape[0] - 1:
            self.idx += 1
            return True
        else:
            return False

    def decrease(self):
        if self.idx > 0:
            self.idx -= 1
            return True
        else:
            return False

    def set(self, idx):
        if idx < 0:
            self.idx = 0
        elif idx > EpochModeConfig.get().window_data.shape[0] - 1:
            self.idx = EpochModeConfig.get().window_data.shape[0] - 1
        else:
            self.idx = int(idx)

    def get(self):
        return self.idx


class EpochModeConfig:
    _instance = None
    CURRENT_WINDOW_IDX = Index(0)
    NONE_LABEL = 'None'

    def __init__(self, *, winLen=10, labels: List[str] = None, keys: List[str] = None, default_label=None, description: List[str] = None):
        if labels is None:
            labels = ['low', 'good']
        if keys is None:
            keys = list(np.arange(len(labels)).astype(str))
        if description is None:
            description = labels
        if default_label is not None:
            if isinstance(default_label, str):
                if default_label not in labels:
                    default_label = labels[0]
                    qInfo('Given default_label is not in given labels. Changed to {} '.format(default_label))
            elif isinstance(default_label, int):
                if default_label <= len(labels):
                    default_label = labels[default_label]
                else:
                    default_label = labels[0]
                    qInfo('Given default_label is not in given labels. Changed to {} '.format(default_label))
        else:
            default_label = EpochModeConfig.NONE_LABEL

        from logic.databases.DatabaseHandler import Database
        track = Database.get().tracks[Database.get().main_track_label]
        self.window_data = pd.DataFrame(columns={'start', 'end', 'label'})
        self.visuals = []
        self.label_to_ypos = {}
        self.labels_to_keys = {}
        self.keys_to_labels = {}
        self.labels_to_color = {}
        self.toggle_fiducials = True

        self.window_overlap = 0  # sec

        self.window_length = winLen  # sec
        self.labels = labels
        self.default_label = default_label
        self.keys = keys
        self.description = description

        all_starts = np.arange(track.time[0], track.time[-1], self.window_length)
        all_ends = all_starts + self.window_length
        if all_ends[-1] > track.time[-1]:
            all_ends[-1] = track.time[-1]

        self.window_data['start'] = all_starts
        self.window_data['end'] = all_ends
        self.window_data['is_modified'] = 0
        self.window_data['label'] = self.default_label

        self.test_epoch_config()

        # colors to be assigned to different labels, colors do not mean anything and can be counterintuitive as Good=Red, Bad=Green
        colors = cycle(['r', 'g', 'b', 'c', 'm', 'y', 'w'])
        for l, k in zip(self.labels, self.keys):
            self.labels_to_keys[l] = k
            self.keys_to_labels[k] = l
            self.labels_to_color[l] = next(colors)

        st, en, label = self.get_window_data(EpochModeConfig.CURRENT_WINDOW_IDX.get())
        EpochWindow(label, start=st, end=en)

        self.redraw_epochs()
        EpochModeConfig._instance = weakref.ref(self)()

    @classmethod
    def get(cls):
        return EpochModeConfig._instance

    def change_toggle_fiducials(self):
        """Option to show annotated fiducials in EpochMode or hide them"""
        from gui.plot_area import PlotArea
        self.toggle_fiducials = not self.toggle_fiducials
        PlotArea.get_main_view().renderer.plot_area.redraw_fiducials()

    @staticmethod
    def to_csv(filename: str):
        data = EpochModeConfig.get()
        try:
            data.window_data.to_csv(filename + '.csv', index=False)
        except OSError as e:
            try:
                xl = win32com.client.Dispatch("Excel.Application")
                xl.Quit()  # quit excel, as if user hit the close button/clicked file->exit.
                # xl.ActiveWorkBook.Close()  # close the active workbook
                data.window_data.to_csv(filename + '.csv', index=False)
            except Exception as e:
                Dialog().warningMessage('Save of epoch mode annotations crashed with:\r\n' + str(e))

    @staticmethod
    def initialize_epoch_mode_settings_from_csv(csv):
        if csv is None:
            EpochModeConfig()
            qInfo('Epoch mode init settings not given. Starting with default values')

        try:
            csv_data = pd.read_csv(csv)
            winLen = int(csv_data.winLen.values[0])
            labels = list(csv_data.labels.values)
            description = list(csv_data.description.values)

            try:
                if not all(isinstance(elem, str) for elem in description):
                    description = labels
            except Exception as e:
                description = labels

            keys = list(csv_data['keys'].values)
            for i, k in enumerate(keys):
                if isinstance(k, (int, np.integer)):
                    keys[i] = str(k)
            default_label = csv_data.default_label.values[0]
            if not isinstance(default_label, str) and np.isnan(default_label):
                default_label = None
            EpochModeConfig(winLen=winLen, labels=labels, keys=keys, default_label=default_label, description=description)
        except Exception as e:
            Dialog().warningMessage('Epoch mode settings processing failed with\r\n' + str(e) + '\r\nInitializing with defaults')
            EpochModeConfig()

    @staticmethod
    def load_from_hdf5(data: pd.DataFrame, keys: List[str], labels, default_label: str, NONE_LABEL: str, description: List[str]):
        # TODO: check windows not overlap, cover whole signal, are of the same length
        assert all([s in data.columns for s in EpochModeConfig.get().window_data]), 'Loaded epoch data misses some columns'
        econfig = EpochModeConfig.get()
        econfig.window_data = data
        econfig.labels = labels
        econfig.keys = keys
        econfig.default_label = default_label
        EpochModeConfig.NONE_LABEL = NONE_LABEL
        econfig.description = description
        econfig.test_epoch_config()
        return

    def get_window_idx_from_x(self, x_pos):
        all_start = EpochModeConfig.get().window_data['start'].values
        all_ends = EpochModeConfig.get().window_data['end'].values
        if x_pos < 0:  # when starting the tool xrange has a margin
            x_pos = 0
        idx = np.where(np.bitwise_and(all_start <= x_pos, all_ends >= x_pos))[0][0]
        return idx

    def get_window_data(self, idx: int):
        if 0 <= idx < self.window_data.shape[0]:
            st = self.window_data['start'].values[idx]
            en = self.window_data['end'].values[idx]
            label = self.window_data['label'].values[idx]
            return st, en, label
        elif idx < 0:
            return self.get_window_data(0)
        elif idx >= self.window_data.shape[0]:
            return self.get_window_data(self.window_data.shape[0] - 1)

    def test_epoch_config(self):
        assert len(self.labels) == len(self.keys), 'Length of labels and keys should be the same'
        assert self.default_label in self.labels or self.default_label == EpochModeConfig.NONE_LABEL, 'Epoch default label is not among possible labels'
        assert self.window_overlap == 0, 'Windows with overlap is not supported'
        assert isinstance(self.default_label, str), 'Default label should be a string'

    @DeprecationWarning
    def redraw_epochs2(self):
        from gui.plot_area import PlotArea
        main_view = PlotArea.get_main_view()
        if main_view is None:
            return
        vb = main_view.renderer.vb
        for item in self.visuals:
            vb.removeItem(item)
        self.visuals.clear()
        if Mode.mode in [Modes.epoch]:
            x_min, x_max = vb.viewRange()[0]
            y_min, y_max = vb.viewRange()[1]
            y_max = y_max - 0.1 * (y_max - y_min)
            y_min = y_min + 0.1 * (y_max - y_min)
            y_range = y_max - y_min

            self.label_to_ypos = {}
            n_labels = len(self.labels)
            for i in np.arange(n_labels):
                self.label_to_ypos[self.labels[i]] = y_min + i * y_range / (n_labels - 1)

            for i in np.arange(self.window_data.shape[0]):
                label = self.window_data.loc[i, 'label']
                st = self.window_data.loc[i, 'start']
                en = self.window_data.loc[i, 'end']
                if not label == EpochModeConfig.NONE_LABEL:
                    y_pos = self.label_to_ypos[label]
                    if not (st >= x_max or en <= x_min):
                        line = pg.PlotDataItem(x=[st, en], y=[y_pos, y_pos], name=label,
                                               pen=pg.mkPen(self.labels_to_color[label], width=3, style=QtCore.Qt.SolidLine, cosmetic=True))
                        self.visuals.append(line)
                        vb.addItem(line)

    def redraw_epochs(self):
        from gui.plot_area import PlotArea
        main_view = PlotArea.get_main_view()
        if main_view is None:
            return
        vb = main_view.renderer.vb
        for item in self.visuals:
            vb.removeItem(item)
        self.visuals.clear()
        if Mode.mode in [Modes.epoch]:
            x_min, x_max = vb.viewRange()[0]
            y_min, y_max = vb.viewRange()[1]
            y_max = y_max - 0.1 * (y_max - y_min)
            y_min = y_min + 0.1 * (y_max - y_min)
            y_range = y_max - y_min

            self.label_to_ypos = {}
            n_labels = len(self.labels)
            for i in np.arange(n_labels):
                self.label_to_ypos[self.labels[i]] = y_min + i * y_range / (n_labels - 1)

            # only for epoch in current view span
            epoch_idxs = np.where(np.logical_and.reduce((self.window_data['start'].values < x_max, self.window_data['end'].values > x_min,
                                                         )))[0]
            # self.window_data['label'].values != EpochModeConfig.NONE_LABEL
            # draw corresponding labels, but combine them into long single lines for speed optimization if labels are non changing
            for i in epoch_idxs:
                label = self.window_data.loc[i, 'label']
                st = self.window_data.loc[i, 'start']
                en = self.window_data.loc[i, 'end']

                if i == epoch_idxs[0]:  # initialize
                    prev_label = label
                    line_start = st
                    line_end = en

                if label == EpochModeConfig.NONE_LABEL and prev_label != EpochModeConfig.NONE_LABEL:
                    y_pos = self.label_to_ypos[prev_label]
                    line = pg.PlotDataItem(x=[line_start, line_end], y=[y_pos, y_pos], name=prev_label,
                                           pen=pg.mkPen(self.labels_to_color[prev_label], width=3, style=QtCore.Qt.SolidLine, cosmetic=True))
                    self.visuals.append(line)
                    vb.addItem(line)
                    line_start = st
                    line_end = en
                    prev_label = label
                    continue

                if i == epoch_idxs[-1] and label == prev_label:  # last and label as prev --> draw the final line
                    if prev_label == EpochModeConfig.NONE_LABEL:
                        line_start = en
                        prev_label = label
                    else:
                        line_end = en
                        y_pos = self.label_to_ypos[prev_label]
                        line = pg.PlotDataItem(x=[line_start, line_end], y=[y_pos, y_pos], name=prev_label,
                                               pen=pg.mkPen(self.labels_to_color[prev_label], width=3, style=QtCore.Qt.SolidLine, cosmetic=True))
                        self.visuals.append(line)
                        vb.addItem(line)
                elif not (i == epoch_idxs[-1]) and label == prev_label:  # NOT last and label as prev --> continue line
                    line_end = en
                elif not (i == epoch_idxs[
                    -1]) and label != prev_label:  # NOT last and label NOT as prev --> draw the line up to this segment excluded and update for this segment
                    if prev_label != EpochModeConfig.NONE_LABEL:
                        y_pos = self.label_to_ypos[prev_label]
                        line = pg.PlotDataItem(x=[line_start, line_end], y=[y_pos, y_pos], name=prev_label,
                                               pen=pg.mkPen(self.labels_to_color[prev_label], width=3, style=QtCore.Qt.SolidLine, cosmetic=True))
                        self.visuals.append(line)
                        vb.addItem(line)
                    line_start = st
                    line_end = en
                    prev_label = label
                elif i == epoch_idxs[-1] and label != prev_label:  # last and label NOT as prev --> draw two lines
                    if prev_label != EpochModeConfig.NONE_LABEL:
                        y_pos = self.label_to_ypos[prev_label]
                        line = pg.PlotDataItem(x=[line_start, line_end], y=[y_pos, y_pos], name=prev_label,
                                               pen=pg.mkPen(self.labels_to_color[prev_label], width=3, style=QtCore.Qt.SolidLine, cosmetic=True))
                        self.visuals.append(line)
                        vb.addItem(line)

                    line_start = st
                    line_end = en
                    prev_label = label
                    y_pos = self.label_to_ypos[prev_label]
                    line = pg.PlotDataItem(x=[line_start, line_end], y=[y_pos, y_pos], name=prev_label,
                                           pen=pg.mkPen(self.labels_to_color[prev_label], width=3, style=QtCore.Qt.SolidLine, cosmetic=True))
                    self.visuals.append(line)
                    vb.addItem(line)

    def process_keypress(self, key: str):
        """
        When in EpochMode and keyPressed is one from the epochModeConfig: assign corresponding label to that epoch and move to the next one
        :param key:
        :return:
        """
        label = self.keys_to_labels.get(key, EpochModeConfig.NONE_LABEL)
        if label is not EpochModeConfig.NONE_LABEL:
            idx = EpochModeConfig.CURRENT_WINDOW_IDX.get()
            self.window_data.loc[idx, 'label'] = label
            self.window_data.loc[idx, 'is_modified'] = 1
            EpochWindow.update_label()
            self.redraw_epochs()

            EpochWindow.move_right()
            qInfo('Window labeled {} '.format(label))

    def process_mouseclick(self, event):
        """
        If in EpochMode and LeftMouseClick: move focus to the corresponding epoch
        If in EpochMode and RightMouseClick: show context menu options
        :param event:
        :return:
        """
        if event.button() == QtCore.Qt.LeftButton:
            from gui.plot_area import PlotArea
            vb = PlotArea.get_main_view().renderer.vb
            click_x = vb.mapSceneToView(event.pos()).x()
            EpochWindow.move_current_window_to_x(click_x)
        elif event.button() == QtCore.Qt.RightButton:
            from gui.plot_area import PlotArea
            vb = PlotArea.get_main_view().renderer.vb
            click_x = vb.mapSceneToView(event.pos()).x()
            context_menu = QtWidgets.QMenu()
            toggle_annotations_action = QtWidgets.QAction('Toggle Fiducials', PlotArea.get_main_view().renderer.plot_area, checkable=True,
                                                          checked=self.toggle_fiducials, enabled=True)

            toggle_annotations_action.triggered.connect(self.change_toggle_fiducials)
            context_menu.addAction(toggle_annotations_action)
            context_menu.setStatusTip('Toggle visibility for annotations in EpochMode')
            temp = context_menu.exec_(event.globalPos().__add__(QtCore.QPoint(10, 10)))
            return

    def current_window_upgrade_value(self):
        """
        For current epoch assign the next label from EpochConfig
        :return:
        """
        idx = EpochModeConfig.CURRENT_WINDOW_IDX.get()

        n_labels = len(self.labels)
        this_label = self.window_data.loc[idx, 'label']
        if this_label == EpochModeConfig.NONE_LABEL:
            this_label_idx = -1
        else:
            this_label_idx = self.labels.index(this_label)
        if this_label_idx < n_labels - 1:
            self.window_data.loc[idx, 'label'] = self.labels[this_label_idx + 1]
            self.window_data.loc[idx, 'is_modified'] = 1

            EpochWindow.update_label()
            self.redraw_epochs()
            # EpochWindow.move_right()
            qInfo('Window labeled {} '.format(self.labels[this_label_idx + 1]))
        else:
            qInfo('Window label can not be upgraded')

    def current_window_downgrade_value(self):
        """
        For current epoch assign the prev label from EpochConfig
        :return:
        """
        idx = EpochModeConfig.CURRENT_WINDOW_IDX.get()

        n_labels = len(self.labels)
        this_label = self.window_data.loc[idx, 'label']
        if this_label == EpochModeConfig.NONE_LABEL:
            this_label_idx = n_labels
        else:
            this_label_idx = self.labels.index(this_label)
        if this_label_idx > 0:
            self.window_data.loc[idx, 'label'] = self.labels[this_label_idx - 1]
            self.window_data.loc[idx, 'is_modified'] = 1

            EpochWindow.update_label()
            self.redraw_epochs()
            # EpochWindow.move_right()
            qInfo('Window labeled {} '.format(self.labels[this_label_idx - 1]))
        else:
            qInfo('Window label can not be downgraded')


class EpochWindow(pg.LinearRegionItem):
    _instance = None

    def __init__(self, name: str, *, start: float = None, end: float = None):
        from gui import PALMS
        from logic.databases.DatabaseHandler import Database
        track = Database.get().tracks[Database.get().main_track_label]

        super().__init__((start, end))
        self.setBounds([start, end])
        self.track = track
        self.start = start
        self.end = end
        self.mid = self.start + (self.end - self.start) / 2
        self.name = name
        self.label = pg.TextItem(name)

        self.label.setFont(QFont("", PALMS.config['epoch_labels_font_size'], QFont.Bold))
        self.label.setAnchor((0.5, 1))
        # self.label.setColor(QColor('k'))

        try:
            label_y = EpochModeConfig.get().label_to_ypos[name]
        except:
            label_y = self.track.get_yrange_between(self.start, self.end)[0]
        self.label.setPos(self.mid, label_y)

        # self.sigRegionChangeFinished.connect(self.region_moved)
        EpochWindow._instance = weakref.ref(self)()
        qInfo('Window at [{:0.2f}; {:0.2f}] '.format(self.start, self.end))

    @staticmethod
    def move_current_window_to_x(x_pos):
        idx = EpochModeConfig.get().get_window_idx_from_x(x_pos)
        EpochModeConfig.CURRENT_WINDOW_IDX.set(idx)
        st, en, label = EpochModeConfig.get().get_window_data(EpochModeConfig.CURRENT_WINDOW_IDX.get())
        EpochWindow.hide()
        EpochWindow(label, start=st, end=en)
        EpochWindow.show()

    @staticmethod
    def get():
        return EpochWindow._instance

    @staticmethod
    def show():
        from gui.plot_area import PlotArea
        vb = PlotArea.get_main_view().renderer.vb
        vb.addItem(EpochWindow.get())
        vb.addItem(EpochWindow.get().label)

    @staticmethod
    def hide():
        from gui.plot_area import PlotArea
        vb = PlotArea.get_main_view().renderer.vb
        vb.removeItem(EpochWindow.get())
        vb.removeItem(EpochWindow.get().label)

    @staticmethod
    def update_label():
        st, en, label = EpochModeConfig.get().get_window_data(EpochModeConfig.CURRENT_WINDOW_IDX.get())
        EpochWindow.hide()
        EpochWindow(label, start=st, end=en)
        EpochWindow.show()

    @staticmethod
    def is_out_of_scope():
        from gui.plot_area import PlotArea
        vb = PlotArea.get_main_view().renderer.vb
        x_min, x_max = vb.viewRange()[0]

        if EpochWindow.get().start < round(x_min, 12) or EpochWindow.get().start > round(x_max, 12):
            return True
        elif EpochWindow.get().end < round(x_min, 12) or EpochWindow.get().end > round(x_max, 12):
            return True
        else:
            return False

    @staticmethod
    def move_right():
        EpochWindow.hide()
        from logic.databases.DatabaseHandler import Database
        from gui.viewer import Viewer
        from gui.plot_area import PlotArea
        track = Database.get().tracks[Database.get().main_track_label]

        success = EpochModeConfig.CURRENT_WINDOW_IDX.increase()
        if success:
            st, en, label = EpochModeConfig.get().get_window_data(EpochModeConfig.CURRENT_WINDOW_IDX.get())
            EpochWindow(label, start=st, end=en)

            while EpochWindow.is_out_of_scope():
                Viewer.get().shiftRight()

        EpochWindow.show()
        PlotArea.get_main_view().renderer.plot_area.setFocus()

    @staticmethod
    def move_left():
        EpochWindow.hide()
        from logic.databases.DatabaseHandler import Database
        from gui.viewer import Viewer
        from gui.plot_area import PlotArea
        track = Database.get().tracks[Database.get().main_track_label]

        success = EpochModeConfig.CURRENT_WINDOW_IDX.decrease()
        if success:
            st, en, label = EpochModeConfig.get().get_window_data(EpochModeConfig.CURRENT_WINDOW_IDX.get())
            EpochWindow(label, start=st, end=en)
            while EpochWindow.is_out_of_scope():
                Viewer.get().shiftLeft()

        EpochWindow.show()
        PlotArea.get_main_view().renderer.plot_area.setFocus()
