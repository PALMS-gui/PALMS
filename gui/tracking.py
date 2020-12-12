"""
Copyright (c) 2005-2017 TimeView Developers
MIT license (see in gui\LICENSE.txt)
"""

import abc
import bisect
import datetime
import logging
from pathlib import Path
from typing import List

import numpy as np
from pyqtgraph import downsample

from utils.utils_gui import Dialog

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# logger.setLevel(logging.WARNING)
# logger.setLevel(logging.ERROR)

"""Tracks
Each track has a fs and a duration. There are 4 kinds of tracks:

1 Event - times
2 Wave - values
3 TimeValue - values at times, duration
4 Partition - values between times

All track intervals are of the type [), and duration points to the next unoccupied sample == length
"""


class Track(metaclass=abc.ABCMeta):
    def __init__(self, label):
        self._fs = 0
        self.type = None
        self.min = None
        self.max = None
        self.unit = None
        self.label = None
        if label is None:
            label = str(id(self))
        self.label = label

    def get_time(self):
        raise NotImplementedError

    def set_time(self, time):
        raise NotImplementedError

    time = property(get_time, set_time)

    def get_value(self):
        raise NotImplementedError

    def set_value(self, value):
        raise NotImplementedError

    value = property(get_value, set_value)

    def get_viewvalue(self):
        raise NotImplementedError

    def set_viewvalue(self, viewvalue):
        raise NotImplementedError

    viewvalue = property(get_viewvalue, set_viewvalue)

    def get_fs(self):
        return self._fs

    def set_fs(self, _value):
        raise Exception("Cannot change fs, try resample()")

    fs = property(get_fs, set_fs, doc="sampling frequency")

    @abc.abstractmethod
    def get_duration(self):
        raise NotImplementedError

    def set_duration(self, duration):
        raise NotImplementedError

    duration = property(get_duration, set_duration)

    def write(self, name, *args, **kwargs):
        """Saves object to name, adding default extension if missing."""
        raise NotImplementedError


def get_track_classes() -> List[Track]:
    def all_subclasses(c):
        return c.__subclasses__() + [a for b in c.__subclasses__() for a in all_subclasses(b)]

    return [obj for obj in all_subclasses(Track)]


class Wave(Track):

    def __init__(self, y: np.ndarray, fs, ts=None, duration=None, offset=0, label=None, unit='au', filename=None):
        super().__init__(label)
        assert isinstance(y, np.ndarray)
        assert 1 <= y.ndim, "only a single channel is supported"
        assert isinstance(fs, int)
        assert fs > 0
        self._value = y.astype(float)
        self._fs = fs
        self._offset = offset  # this is required to support heterogenous fs in multitracks
        self.type = 'Wave'
        self.ts = ts if ts is not None else np.linspace(0, stop=(len(self._value) - 1) / fs, num=len(self._value)) + self._offset

        self.filename = self.label + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") if filename is None else filename
        if not duration:
            duration = len(self._value)
        assert len(self._value) <= duration < len(
            self._value) + 1, "Cannot set duration of a wave to other than a number in [length, length+1) - where length = len(self.y)"
        self._duration = duration
        from gui import PALMS
        yrange_margin = PALMS.config['yrange_margin']
        self.minY = np.min(self._value) * (1 + yrange_margin) if np.min(self._value) < 0 else np.min(self._value) * (1 - yrange_margin)
        self.maxY = np.max(self._value) * (1 - yrange_margin) if np.max(self._value) < 0 else np.max(self._value) * (1 + yrange_margin)
        self.minX = np.min(self.ts)
        self.maxX = np.max(self.ts)

        self.unit = unit

        self._viewvalue = self._value.copy()

    def invert(self):
        self._value = -self._value

    def derive_1der(self):
        return Derived(self, '1der')

    def derive_2der(self):
        return Derived(self, '2der')

    def add_annotation_config(self, aConf):
        self.aConf = aConf

    def get_offset(self):
        return self._offset

    def set_offset(self, offset):
        self._offset = offset

    offset = property(get_offset, set_offset)

    def get_time(self):
        return self.ts

    def set_time(self, time):
        raise Exception("can't set times for Wave")

    time = property(get_time, set_time)

    def get_value(self):
        return self._value

    def set_value(self, value):
        assert isinstance(value, np.ndarray)
        assert 1 == value.ndim, 'only a single channel is supported'
        self._value = value
        if not (len(self._value) <= self._duration < len(self._value) + 1):
            self._duration = len(self._value)

    value = property(get_value, set_value)

    def get_viewvalue(self):
        return self._viewvalue

    def set_viewvalue(self, viewvalue):
        assert isinstance(viewvalue, np.ndarray)
        assert 1 == viewvalue.ndim, 'only a single channel is supported'
        self._viewvalue = viewvalue
        if not (len(self._viewvalue) <= self._duration < len(self._viewvalue) + 1):
            self._duration = len(self._viewvalue)

    def reset_viewvalue(self):
        self._viewvalue = self._value

    viewvalue = property(get_viewvalue, set_viewvalue)

    def get_duration(self):
        return self._duration

    def set_duration(self, duration):
        assert len(self._value) <= duration < len(
            self._value) + 1, "Cannot set duration of a wave to other than a number in [length, length+1) - where length = len(self.value)"
        self._duration = duration

    duration = property(get_duration, set_duration)

    def get_yrange_between(self, xmin, xmax):
        ymin, ymax = 0, 1
        sig = self._value
        ts = self.ts

        # import time
        # s = time.time()
        # for i in np.arange(100000):
        #     idx = np.arange(np.searchsorted(ts, xmin, 'right'), np.searchsorted(ts, xmax, 'left'))
        idx = np.arange(bisect.bisect_right(ts, xmin), bisect.bisect_left(ts, xmax))
        # en = time.time() - s

        if any(idx):
            sig = sig[idx]
            ymin, ymax = np.min(sig), np.max(sig)
        return ymin, ymax

    def get_dtype(self):
        return self._value.dtype

    dtype = property(get_dtype)


class Derived(Wave):
    def __init__(self, wave: Wave, type: str):
        if type in ['d', 'd1', 'derivative', '1derivative', 'derivative1', 'der1', '1der']:
            y = np.gradient(wave.value)
            label = 'd_' + wave.label
            unit = 'd_' + wave.unit
        elif type in ['d2', 'derivative2', '2derivative', 'der2', '2der']:
            y = np.gradient(np.gradient(wave.value))
            label = 'd2_' + wave.label
            unit = 'd2_' + wave.unit
        else:
            raise ValueError

        super().__init__(y, wave.fs, wave.ts, offset=wave.offset, label=label, unit=unit)
        self.type = 'Derived'
