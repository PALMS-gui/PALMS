"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""

import bisect
from typing import List

import numpy as np
import pyqtgraph as pg
import win32com
from PyQt5.QtCore import QObject, qInfo, qWarning
from PyQt5.QtGui import QFont, QColor
from qtpy import QtWidgets
from setuptools.package_index import unique_everseen

from utils.utils_general import dict_to_df_with_nans
from utils.utils_gui import Dialog


class SinglePartition(pg.LinearRegionItem):
    """
    represents non-overlapping regions defined by start/end borders and left/right bounds (limits)
    start\end can be dragged/moved in Partition mode, but cannot reach its limits
    """

    def __init__(self, name: str, *, start: float = None, end: float = None):
        """
        constructor when start/end are given explicitly. when created from mouse click (single point) see self.from_click
        """
        from gui import PALMS
        from logic.databases.DatabaseHandler import Database
        track = Database.get().tracks[Database.get().main_track_label]
        left_bound, right_bound = Partitions.calculate_boundaries(start, end)
        left_bound = left_bound if left_bound is not None else track.minX
        right_bound = right_bound if right_bound is not None else track.maxX

        start = max([max([start, track.minX]), left_bound])
        end = min([min([end, track.maxX]), right_bound])

        super().__init__((start, end))
        self.setBounds([left_bound, right_bound])
        self.track = track
        self.start = start
        self.end = end
        self.mid = self.start + (self.end - self.start) / 2
        self.name = name
        self.label = pg.TextItem(name)

        self.label.setFont(QFont("", PALMS.config['partition_labels_font_size'], QFont.Bold))
        # self.label.setColor(QColor('k'))
        self.label.setAnchor((0.5, 1))
        self.label.setPos(self.mid, self.track.get_yrange_between(self.start, self.end)[0])
        Partitions.add(self)

        Partitions.update_all_bounds(self)

        # # update config with new partition name
        # from gui.viewer import PALMS
        # PALMS.config['default_partition_labels'] = list(
        #     unique_everseen(PALMS.config['default_partition_labels'] + Partitions.unique_labels()))

        self.sigRegionChangeFinished.connect(self.region_moved)
        qInfo('Region {} [{:0.2f}; {:0.2f}] created'.format(self.name, self.start, self.end))

    @classmethod
    def from_click(cls, name: str, *, click_x: float):
        """construct SinglePartition from single point: calculate its start/end considering other partitions"""
        from logic.databases.DatabaseHandler import Database
        from gui import PALMS
        track = Database.get().tracks[Database.get().main_track_label]
        initial_span = (track.maxX - track.minX) * 0.01
        initial_span = PALMS.config['initial_partition_span_sec']  # NB: set initial span of just created partition
        left_bound, right_bound = Partitions.calculate_boundaries(click_x, click_x)
        left_bound = left_bound if left_bound is not None else track.minX
        right_bound = right_bound if right_bound is not None else track.maxX

        start = max([max([click_x - initial_span / 2, track.minX]), left_bound])
        end = min([min([click_x + initial_span / 2, track.maxX]), right_bound])
        return cls(name, start=start, end=end)

    def region_moved(self):
        self.start, self.end = self.getRegion()
        self.mid = self.start + (self.end - self.start) / 2
        self.label.setPos(self.mid, self.track.get_yrange_between(self.start, self.end)[0])
        Partitions.remove_zero_partitions()
        Partitions.update_all_bounds()
        qInfo('Region {} moved'.format(self.name))

    def region_deleted(self):
        if self is not None:
            self.label.getViewBox().removeItem(self.label)
            self.getViewBox().removeItem(self)
            Partitions.delete(self)
            Partitions.update_all_bounds()
            qInfo('Region {} [{:0.2f}; {:0.2f}] deleted'.format(self.name, self.start, self.end))


class Partitions(QObject):
    """
    static class to operate on all existing SinglePartition instances
    """
    partitions: List[SinglePartition] = []  # keep sorted list of all SinglePartition instances

    def __new__(*args):  # instead of creating, return list of SinglePartition
        return Partitions.partitions

    @staticmethod
    def remove_zero_partitions():  # if start==end --> SinglePartition is flat
        for p in Partitions():
            x1, x2 = p.getRegion()
            if x1 == x2:
                p.region_deleted()

    @staticmethod
    def update_all_bounds(avoid_this_p: SinglePartition = None):
        """
        As SinglePartitions cannot overlap, after creating\moving\deleting it is necessary to update
        the limits to which every SinglePartition can be moved\dragged
        """
        for p in Partitions():
            if not p == avoid_this_p:
                left_bound, right_bound = Partitions.calculate_boundaries(p.start, p.end)
                left_bound = left_bound if left_bound is not None else p.track.minX
                right_bound = right_bound if right_bound is not None else p.track.maxX
                p.setBounds([left_bound, right_bound])

    @staticmethod
    def calculate_boundaries(this_left: float, this_right: float):
        """
        check nearest left and nearest right SinglePartition borders and set limits for this SinglePartition
        """
        nearest_left = bisect.bisect_right(Partitions.all_endpoints(), this_left) - 1
        nearest_right = bisect.bisect_left(Partitions.all_startpoints(), this_right)
        try:
            left_boundary = Partitions()[nearest_left].end if nearest_left >= 0 else None
        except:
            left_boundary = None

        try:
            right_boundary = Partitions()[nearest_right].start if nearest_right >= 0 else None
        except:
            right_boundary = None

        return left_boundary, right_boundary

    @staticmethod
    def unhide_all_partitions():
        from gui.viewer import Viewer
        for i in Partitions():
            Viewer.get().selectedView.renderer.vb.addItem(i)
            Viewer.get().selectedView.renderer.vb.addItem(i.label)

    @staticmethod
    def hide_all_partitions():
        from gui.viewer import Viewer
        for i in Partitions():
            Viewer.get().selectedView.renderer.vb.removeItem(i)
            Viewer.get().selectedView.renderer.vb.removeItem(i.label)

    @staticmethod
    def add(p: SinglePartition):
        idx = bisect.bisect_left(Partitions.all_midpoints(), p.mid)
        Partitions.partitions.insert(idx, p)

    @staticmethod
    def add_all(labels: List[str], start: np.ndarray, end: np.ndarray):
        """
        batch adding partitions, e.g. from loaded annotations file

        """
        try:
            Partitions.delete_all()
            assert len(labels) == start.size & start.size == end.size, 'Every loaded partition should have label, start and end'
            for l, s, e in zip(labels, start, end):
                SinglePartition(l, start=s, end=e)
        except Exception as e:
            Dialog().warningMessage('Partitions cannot be loaded\r\n' + str(e))

    @staticmethod
    def delete(p: SinglePartition):
        Partitions.partitions.remove(p)

    @staticmethod
    def delete_all():
        Partitions.hide_all_partitions()
        Partitions.partitions = []

    @staticmethod
    def find_partition_by_point(click_x: float):  # get partition under mouse click or None
        idx = np.where((click_x >= Partitions.all_startpoints()) & (click_x <= Partitions.all_endpoints()))[0]
        if len(idx) == 1:
            return Partitions()[idx[0]]
        elif len(idx) == 0:
            return None
        else:
            qWarning('More than one partition found! Return the first')  # should not happen, as partitions don't overlap
            return Partitions()[idx[0]]

    # TODO: ensure non overlapping partitions!!!
    # TODO: partitions outside signal
    @staticmethod
    def all_startpoints():
        return np.array([p.start for p in Partitions.partitions])

    @staticmethod
    def all_endpoints():
        return np.array([p.end for p in Partitions.partitions])

    @staticmethod
    def all_midpoints():
        return np.array([p.mid for p in Partitions.partitions])

    @staticmethod
    def all_labels():
        return [p.name for p in Partitions.partitions]

    @staticmethod
    def unique_labels():
        return list(unique_everseen(Partitions.all_labels()))

    @staticmethod
    def to_csv(filename: str):
        d = {'label': Partitions.all_labels(), 'start': Partitions.all_startpoints(), 'end': Partitions.all_endpoints()}
        df = dict_to_df_with_nans(d)
        try:
            df.to_csv(filename + '.csv', index=False)
        except OSError as e:
            try:
                xl = win32com.client.Dispatch("Excel.Application")
                xl.Quit()  # quit excel, as if user hit the close button/clicked file->exit.
                # xl.ActiveWorkBook.Close()  # close the active workbook
                df.to_csv(filename + '.csv', index=False)
            except Exception as e:
                Dialog().warningMessage('Save crashed with:\r\n' + str(e))

    @staticmethod
    def clear_annotations_in_this_partition(p: SinglePartition):
        """
        batch removing annotations which fall within a partition.
        good to have if it is needed to clean large artifact region from spurious fiducials
        """
        try:
            from logic.operation_mode.annotation import AnnotationConfig
            from gui.viewer import Viewer
            aConf = AnnotationConfig.get()
            for f in aConf.fiducials:
                ann = f.annotation
                remove_idx = np.arange(bisect.bisect_right(ann.x, p.start), bisect.bisect_left(ann.x, p.end))
                nn = max(remove_idx.shape)
                result = QtWidgets.QMessageBox.question(Viewer.get(), "Confirm Delete Annotations...",
                                                        "Are you sure you want to delete {nn} {name} annotations ?".format(nn=nn, name=ann.name),
                                                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
                if result == QtWidgets.QMessageBox.Yes:
                    ann.x = np.delete(ann.x, remove_idx)
                    ann.y = np.delete(ann.y, remove_idx)
                    ann.idx = np.delete(ann.idx, remove_idx)
                    Viewer.get().selectedDisplayPanel.plot_area.redraw_fiducials()
            Partitions.update_all_bounds()

        except Exception as e:
            Dialog().warningMessage('Deleting annotations failed with\r\n' + str(e))
