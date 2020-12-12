"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
import bisect
import weakref
from typing import List

import numpy as np
import pandas as pd
import win32com
from PyQt5.QtCore import pyqtSlot, QObject, pyqtSignal, qInfo
from pyqtgraph import mkBrush, mkPen
from qtpy.QtCore import Signal
from win32com.client import Dispatch

from logic.databases.DatabaseHandler import Database
from utils.detect_peaks import detect_peaks
from utils.utils_general import find_closest, dict_to_df_with_nans


class Annotation(QObject):
    signal_annotate = pyqtSignal(float)
    signal_delete_annotation = pyqtSignal(float)

    def __init__(self, fiducial_name, x_=np.array([]), y_=np.array([]), parent=None):
        super(QObject, self).__init__(parent)
        self.name = fiducial_name.lower()
        self.x = x_
        self.y = y_
        self.idx = np.array([])
        self.signal_annotate.connect(self.add)
        self.signal_delete_annotation.connect(self.delete)

    def find_annotation_between_two_ts(self, x1, x2):
        """
        finds annotation points within given x-limits. used to redraw only part of the annotations when zooming\moving a plot
        !!! MUST be computationally efficient otherwise will slow down browsing through the plot
        """
        x, y = np.array([]), np.array([])

        # import time
        # s = time.time()
        # for i in np.arange(10000):
        #     idx = np.arange(np.searchsorted(self.x, x1, 'right'), np.searchsorted(self.x, x2, 'left'))
        idx = np.arange(bisect.bisect_right(self.x, x1), bisect.bisect_left(self.x, x2))
        # en = time.time() - s

        if idx.size > 0:
            x = self.x[idx]
            y = self.y[idx]
        return np.array(x), np.array(y)

    @pyqtSlot(float)
    def delete(self, x):
        from gui.viewer import Viewer
        plot_area = Viewer.get().selectedDisplayPanel.plot_area

        fiducial_name = self.name
        fConf = AnnotationConfig.get()[fiducial_name]
        if fConf.annotation.x.size > 0:
            # closest_idx, _, _ = find_closest(fConf.annotation.x, np.array([x]))
            closest_idx = np.argmin(abs(x - fConf.annotation.x))
            deleted_x, deleted_y = fConf.annotation.x[closest_idx], fConf.annotation.y[closest_idx]

            fConf.annotation.x = np.delete(fConf.annotation.x, closest_idx)
            fConf.annotation.y = np.delete(fConf.annotation.y, closest_idx)
            fConf.annotation.idx = np.delete(fConf.annotation.idx, closest_idx)

            Viewer.get().selectedDisplayPanel.plot_area.redraw_fiducials()
            plot_area.signal_annotation_added.emit(deleted_x, deleted_y, 'deleted')
            qInfo('{n} deleted'.format(n=fiducial_name))
        else:
            qInfo('No {n} to be deleted'.format(n=fiducial_name))

    @pyqtSlot(float)
    def add(self, x):
        fiducial_name = self.name
        from gui.viewer import Viewer
        plot_area = Viewer.get().selectedDisplayPanel.plot_area
        track = plot_area.main_window.selectedTrack  # annotation can only be added to the main track, but there are checks on this before
        fs = track.fs

        amp = track.value
        ts = track.get_time()
        fConf = AnnotationConfig.get()[fiducial_name]

        insert_index = bisect.bisect_right(fConf.annotation.x, x)

        min_distance_samples = round(fs * fConf.min_distance)
        blocked_region = np.array([])
        if insert_index > 0:
            blocked_region = np.arange(fConf.annotation.idx[insert_index - 1],
                                       fConf.annotation.idx[insert_index - 1] + min_distance_samples)
        if len(fConf.annotation.idx) > insert_index:
            blocked_region = np.append(blocked_region, np.arange(fConf.annotation.idx[insert_index] - min_distance_samples,
                                                                 fConf.annotation.idx[insert_index] + 1))

        if insert_index > 0 and fConf.annotation.idx.size > insert_index:
            allowed_region = np.arange(fConf.annotation.idx[insert_index - 1] + min_distance_samples,
                                       fConf.annotation.idx[insert_index] - min_distance_samples)
        elif insert_index > 0 and fConf.annotation.idx.size == insert_index:
            allowed_region = np.arange(fConf.annotation.idx[insert_index - 1] + min_distance_samples,
                                       ts.shape[0])
        elif insert_index == 0 and fConf.annotation.idx.size > insert_index:
            allowed_region = np.arange(0, fConf.annotation.idx[insert_index] - min_distance_samples)
        elif insert_index == 0 and fConf.annotation.idx.size == insert_index:
            allowed_region = np.arange(0, ts.shape[0])

        pinned_to_track = plot_area.main_window.selectedPanel.get_view_from_track_label(fConf.pinned_to_track_label).track
        if fConf.is_pinned:
            # TODO: pin should take into account blocked region, as more important requirement
            x = fConf.annotation.pin(x, pinned_to_track, fConf.pinned_to_location, fConf.pinned_window, allowed_region)

        if x is None:
            qInfo('{}: duplicate annotation; min_distance is set to {} s'.format(fiducial_name.upper(), fConf.min_distance))
            return
        ind, _, _ = find_closest(ts, np.array([x]))
        assert len(ind) == 1

        insert_index = bisect.bisect_right(fConf.annotation.x, x)

        # min_distance_samples = round(fs * fConf.min_distance)
        # blocked_region = np.array([])
        # if insert_index > 0:
        #     blocked_region = np.arange(fConf.annotation.idx[insert_index - 1],
        #                                fConf.annotation.idx[insert_index - 1] + min_distance_samples)
        # if len(fConf.annotation.idx) > insert_index:
        #     blocked_region = np.append(blocked_region, np.arange(fConf.annotation.idx[insert_index] - min_distance_samples,
        #                                                          fConf.annotation.idx[insert_index] + 1))

        if not ind[0] in blocked_region:
            fConf.annotation.idx = np.insert(fConf.annotation.idx, insert_index, ind[0])
            fConf.annotation.x = np.insert(fConf.annotation.x, insert_index, ts[ind[0]])
            y = amp[ind[0]]
            fConf.annotation.y = np.insert(fConf.annotation.y, insert_index, y)
            plot_area.signal_annotation_added.emit(x, y, 'added')
            qInfo('{n}: x= {X} y= {Y}'.format(n=fiducial_name, X=str(np.round(x, 2)), Y=str(np.round(y, 2))))
        else:
            qInfo('{}: duplicate annotation; min_distance is set to {} s'.format(fiducial_name.upper(), fConf.min_distance))
            return

    def pin(self, x: float, track, pinned_to: str, pinned_window: float, allowed_region_idx: List[int]):
        DEBUG = False
        window = pinned_window  # sec

        if len(allowed_region_idx) < 3:
            return None

        amp = track.value
        ts = track.get_time()
        fs = track.get_fs()

        x_ind = np.argmin(abs(ts - x))
        left_x_ind, right_x_ind = int(max([x_ind - round(fs * window), 0])), int(min([x_ind + round(fs * window), amp.size]))
        left_x_ind, right_x_ind = int(max([allowed_region_idx[0], left_x_ind])), int(min(
            [allowed_region_idx[-1], right_x_ind]))  # both within window and allowed region
        sx, sy = ts[left_x_ind:right_x_ind], amp[left_x_ind:right_x_ind]
        # sy = scipy.signal.medfilt(sy, round_to_odd(fs * 0.02))  # TODO: parametrize smoothing

        if pinned_to.lower().__contains__('peak'):
            ind = detect_peaks(sy, show=DEBUG)
        elif pinned_to.lower().__contains__('valley'):
            ind = detect_peaks(sy, valley=True, show=DEBUG)
        else:
            raise ValueError

        if ind.size > 0:
            closest, _, _ = find_closest(ind + left_x_ind, np.array([x_ind]))
            highest = np.argmax(abs(sy[ind] - np.mean(sy)))
            ind_to_return = highest  # take highest of all peaks found
            return sx[ind[ind_to_return]]
        else:
            qInfo('{p} not found'.format(p=pinned_to))
            return x

    def create_RRinterval_track(self):
        db = Database.get()
        to_HR = db.RR_interval_as_HR
        track_fs = db.tracks[db.main_track_label].fs
        track_ts = db.tracks[db.main_track_label].ts
        closest_int_fs = int(min([np.ceil(1 / min(np.diff(self.x))), track_fs]))

        fs = track_fs  # maximum zooming is defined by the lowest sampling freq of all tracks
        rr_ts = np.arange(track_ts[0], track_ts[-1], 1 / fs)
        new_ts_idx = np.arange(bisect.bisect_right(rr_ts, self.x[1]), bisect.bisect_left(rr_ts, self.x[-1]))
        rr = np.zeros_like(rr_ts)

        from gui.tracking import Wave
        if to_HR:
            rr[new_ts_idx] = np.interp(rr_ts[new_ts_idx], self.x[1:], 60 / np.diff(self.x))
            rr_int_wave = Wave(rr, fs, rr_ts, offset=0, label='HR(' + self.name + ')', unit='BPM')
            rr_int_wave.type = 'HR'
        else:
            rr[new_ts_idx] = np.interp(rr_ts[new_ts_idx], self.x[1:], np.diff(self.x))
            rr_int_wave = Wave(rr, fs, rr_ts, offset=0, label='RR(' + self.name + ')', unit='sec')
            rr_int_wave.type = 'RR'

        return rr_int_wave


class SingleFiducialConfig:
    def __init__(self, data: dict):
        from gui import PALMS
        assert all([k in data for k in PALMS.config['annotationConfig_columns']])
        name = data['name'].lower()
        key = data['key']
        is_pinned = data['is_pinned']
        pinned_to = data['pinned_to']
        pinned_window = data['pinned_window']
        min_distance = data['min_distance']
        symbol = data['symbol']
        symbol_size = data['symbol_size']
        symbol_colour = data['symbol_colour']

        self.name = name
        self.key, self.is_pinned, self.pinned_to, self.pinned_window, self.min_distance = key, is_pinned, pinned_to, pinned_window, min_distance
        self.symbol = symbol
        self.symbol_size = symbol_size
        self.symbol_colour = symbol_colour
        self.symbol_pen = mkPen(cosmetic=False, width=1, color=self.symbol_colour)
        self.symbol_brush = mkBrush(self.symbol_colour)
        self.pxMode = True
        self.annotation = Annotation(self.name)

        self.split_pinned_to()

    def split_pinned_to(self):
        try:
            from gui.viewer import PALMS
            if self.pinned_to in PALMS.config['pinned_to_options']:
                self.pinned_to = self.pinned_to + ' ' + Database.get().main_track_label

            pinned_to_split = self.pinned_to.split()
            # TODO: make it more generic and foolproof, now it is assumed that pinned_to consists of two words: peak\valley + track_label
            assert_text = '{} pinned_to setting must consist of two words:\r\n' \
                          '"peak" or "valley" + track_label from the database;\r\n' \
                          'Current pinned_to value is {}\r\n' \
                          'Check your AnnotationConfig file {} and run the tool again'.format(self.name, self.pinned_to,
                                                                                              Database.get().annotation_config_file.stem)
            assert len(pinned_to_split) == 2, assert_text
            assert pinned_to_split[0] in PALMS.config['pinned_to_options'], assert_text
            self.pinned_to_location = pinned_to_split[0]
            self.pinned_to_track_label = pinned_to_split[1]
        except Exception as e:
            from utils.utils_gui import Dialog
            Dialog().warningMessage('Error in split_pinned_to():\r\n' + str(e))
            raise ValueError

    def print(self):
        print(self.__str__())

    def set_annotation_from_time(self, ts, track):
        # TODO: make it properly via init of Annotation(...)
        ts = ts[~np.isnan(ts)]
        self.annotation.x = ts
        idx, _, _ = find_closest(track.time, ts)
        self.annotation.y = track.value[idx]
        self.annotation.idx = idx

    def set_annotation_from_idx(self, idx, track):
        # TODO: make it properly via init of Annotation(...)
        idx = idx[~np.isnan(idx)]
        self.annotation.idx = idx
        self.annotation.x = track.time[idx]
        self.annotation.y = track.value[idx]


class AnnotationConfig(QObject):
    signal_config_changed = Signal(list, name='config_changed')
    _instance = None

    def __init__(self, parent=None):
        super(QObject, self).__init__(parent)
        self.fiducials = []
        AnnotationConfig._instance = weakref.ref(self)()
        self.signal_config_changed.connect(self.reload_config)

    def clear(self):
        self.fiducials = []
        from gui.dialogs.AnnotationConfigDialog import AnnotationConfigDialog
        AnnotationConfigDialog.get().aConf_to_table(AnnotationConfig.get())

    def reset_fiducials_config(self, fiducials):
        for f in fiducials:
            if self.find_idx_by_name(f.name) is not None:
                idx = self.find_idx_by_name(f.name)
                # TODO: copy annotation
                tmp_annotation = self.fiducials[idx].annotation
                self.fiducials[idx] = f
                self.fiducials[idx].annotation = tmp_annotation
            else:
                self.fiducials.append(f)

    @classmethod
    def get(cls):
        return AnnotationConfig._instance if AnnotationConfig._instance is not None else cls()

    def find_idx_by_name(self, name: str):
        if not self.fiducials:
            return None
        else:
            idx = [i for i, f in enumerate(self.fiducials) if name == f.name]
            assert len(idx) in [0, 1]
            if len(idx) == 0:
                return None  # TODO: if not found case
            else:
                return idx[0]

    def __getitem__(self, item):
        if isinstance(item, str):
            return self.fiducials[self.find_idx_by_name(item)]
        elif isinstance(item, int):
            return self.fiducials[item]

    def is_valid(self):
        if len(self.fiducials) > 0:
            return True
        return False

    @staticmethod
    def all_fiducials():
        return [f.name for f in AnnotationConfig.get().fiducials]

    @classmethod
    # TODO: generalize and combine with refreshing aConf from GUI
    def from_csv(cls, csv):
        from gui import PALMS
        settings_init = pd.read_csv(csv)
        db = Database.get()
        fiducials = []
        for _, row_data in settings_init.iterrows():
            assert all([k in row_data for k in PALMS.config['annotationConfig_columns']])
            # NB: recover aConf.pinned_to changes from json
            #  it is not needed as one can rewrite annotation config from AnnotationConfigDialog Save button
            # see also AnnotationConfigDialog where applied data is saved
            # try:
            #     tmp_singleFiducialConfig = SingleFiducialConfig(row_data)
            #     pinned_to_prev_state = PALMS.config['pinned_to_last_state'][tmp_singleFiducialConfig.name]
            #     pinned_to_prev_state = pinned_to_prev_state.split()
            #     if pinned_to_prev_state[0] in PALMS.config['pinned_to_options'] and \
            #         pinned_to_prev_state[1] in db.tracks_to_plot_initially:
            #         row_data['pinned_to'] = " ".join(pinned_to_prev_state)
            #     qInfo('Annotation Config updated with config.json data')
            # except Exception as e:
            #     pass
            fiducials.append(SingleFiducialConfig(row_data))
        aConf = AnnotationConfig.get()
        aConf.reset_fiducials_config(fiducials)
        try:  # NB: nice to do it here, but Viewer object might still not be created
            from gui.viewer import Viewer
            Viewer.get().annotationConfig.aConf_to_table(aConf)
            Viewer.get().annotationConfig.reset_pinned_to_options_to_existing_views()
        except:
            pass
        return aConf

    def to_csv(self, filename: str, save_idx: bool = False):
        # TODO: pop up window save as and multiple choice of file formats???
        d = {}
        for f in self.fiducials:
            if save_idx:
                d[f.name] = np.sort(f.annotation.idx)
            else:
                d[f.name] = np.sort(f.annotation.x)

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
                print(e)

    def size(self):
        return len(self)

    @pyqtSlot(list, name='reload_config')
    def reload_config(self, data):
        aConf = AnnotationConfig.get()
        for i, idx in enumerate(data):
            if i > 0:
                aConf.fiducials.append(
                    SingleFiducialConfig(data[i][0], data[i][1], data[i][2], data[i][3], data[i][4], data[i][5], symbol=data[i][6],
                                         symbol_size=data[i][7], symbol_colour=data[i][8]))
        print(AnnotationConfig.get())
