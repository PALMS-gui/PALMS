"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
import abc
import inspect
import json
import os
import pathlib
import weakref
from time import strftime, gmtime
from typing import List, Dict

import h5py
import numpy as np
from PyQt5.QtCore import qInfo
from deprecated import deprecated
from numpy.lib.format import magic
from scipy.io import loadmat
import pandas as pd
from gui.tracking import Track
from logic.operation_mode.partitioning import Partitions
from logic.operation_mode.epoch_mode import EpochModeConfig
from utils.utils_general import string_to_path, get_project_root
from utils.utils_gui import Dialog


class Database(metaclass=abc.ABCMeta):
    """base class for all custom databases."""
    _instance = None

    @classmethod
    def get(cls):
        """
        method allows to get the only Database instance from anywhere in the code by running Database.get()
        :return: object of one of the classes in this module
        """
        if Database._instance is not None:
            return Database._instance
        else:
            Dialog().warningMessage('Databse not initialized yet\r\n return None')
            return None

    def annotation_exists(self, filename):
        """checks whether an annotation file already exists"""
        # existing_annotation_file = pathlib.Path(self.existing_annotations_folder, filename + '.h5')
        existing_annotation_file = list(pathlib.Path(self.existing_annotations_folder).rglob('*' + filename + '*' + '.h5'))
        if len(existing_annotation_file) > 0:
            return True
        else:
            return False

    def get_annotation_file(self, filename):
        existing_annotation_file = list(pathlib.Path(self.existing_annotations_folder).rglob('*' + filename + '*' + '.h5'))
        if len(existing_annotation_file) > 0:
            return existing_annotation_file
        else:
            return None

    @classmethod
    def ntracks(cls):
        db = Database.get()
        return len(db.tracks)

    def __init__(self, *args, **kwargs):
        self.name: str = type(self).__name__
        self.filetype: str = None  # e.g. 'mat' or 'csv'
        self.DATAPATH: pathlib.Path = None  # top folder which contains all data
        self.file_template: str = None  # '**/*.' + self.filetype  # TODO: use regex,then also need to advance SelectFileDialog.py
        self.output_folder: pathlib.Path = get_project_root()
        self.existing_annotations_folder: pathlib.Path = self.output_folder
        self.main_track_label: str = None  # signal which will be annotated and plotted in the first place
        self.tracks_to_plot_initially: List[str] = None  # self.main_track_label will be added once known
        self.annotation_config_file: pathlib.Path = None  # resource_path(pathlib.Path(get_project_root(), 'config', 'AnnotationConfig_SOMETHING.csv'))
        self.epoch_config_file: pathlib.Path = None  # resource_path(pathlib.Path('config', 'EpochConfig', 'EpochConfig_default_start_with_None.csv'))
        self.RR_interval_as_HR = True  # True: RR intervals in BPM, False: in seconds
        self.outputfile_prefix = ''  # set here your initials, to distinguish multiple annotators
        Database._instance = weakref.ref(self)()
        Database.get()

    @abc.abstractmethod
    def get_data(self, filename: pathlib.Path):
        """
        describes the way how to get necessary data for each particular database case
        :param filename: ONE file to contain all tracks
        :return: should fill in self.fullpath, self.tracks, self.track_labels
        self.tracks and self.track_labels should be populated in Database subclases
        Wave objects in self.tracks should be np.array with floats
        """
        filename = string_to_path(filename)  # make sure it is pathlib.Path
        if None in [filename]:
            raise ValueError('kwargs to {f} must contain filename'.format(f=inspect.stack()[0][3]))
        if filename.as_posix().endswith(self.filetype):
            filename = pathlib.Path(filename.as_posix()[:-(len(self.filetype))])
        fullpath = pathlib.Path(self.DATAPATH, filename.as_posix() + self.filetype)
        self.fullpath: pathlib.Path = fullpath
        self.tracks: Dict[str, Track] = None
        self.track_labels: List[str] = None

    @abc.abstractmethod
    def set_annotation_data(self):
        raise NotImplementedError

    def set_annotation_config(self):
        # TODO: bind this to button load csv in annotationConfigDialog
        assert self.annotation_config_file is not None and self.tracks is not None
        from logic.operation_mode.annotation import AnnotationConfig
        self.tracks[self.main_track_label].aConf = AnnotationConfig.from_csv(csv=self.annotation_config_file.as_posix())

    def set_epochMode_config(self):
        from logic.operation_mode.epoch_mode import EpochModeConfig
        if not self.epoch_config_file is None:
            EpochModeConfig.initialize_epoch_mode_settings_from_csv(csv=self.epoch_config_file.as_posix())
        else:
            EpochModeConfig()

    @abc.abstractmethod
    def load(self, fullpath):
        try:
            hf = self._get_matfile_object(fullpath)
            assert all(s in hf.keys() for s in ['annotations', 'partitions']), r'h5 must have {} groups'.format(
                ['annotations', 'partitions'])

            assert all([s in hf['partitions'] for s in ['label', 'start', 'end']]), r'h5.partitions must have {} groups'.format(
                ['label', 'start', 'end'])
            labels = hf['partitions/label']
            labels = [n.decode('ascii', 'ignore') for n in labels]
            start = np.array(hf['partitions/start'])
            end = np.array(hf['partitions/end'])
            assert len(labels) == start.size & start.size == end.size, 'Every partition should have label, start and end'
            Partitions.add_all(labels, start, end)

            from logic.operation_mode.annotation import AnnotationConfig
            assert all([s in AnnotationConfig.all_fiducials() for s in hf['annotations']]), 'All h5.annotations must be in {} groups'.format(
                AnnotationConfig.all_fiducials())
            for f_name in hf['annotations'].keys():
                self._set_annotation_from_time(f_name, np.array(hf['annotations/' + f_name + '/ts']))
            from gui.viewer import Viewer
            try:  # when loaded during initialization
                Viewer.get().selectedDisplayPanel.plot_area.redraw_fiducials()  # to update and show loaded data
            except:
                pass

            try:  # can be removed after thorough testing
                if 'epoch' in hf.keys():
                    assert all(
                        [f in hf['epoch'] for f in
                         ['start', 'end', 'is_modified', 'label', 'all_labels', 'keys',
                          'default_label']]), 'Loaded file contains incorrect epoch mode data'

                    labels = [n.decode('ascii', 'ignore') for n in hf['epoch/label']]
                    epoch_data = pd.DataFrame(
                        {'start': hf['epoch/start'], 'end': hf['epoch/end'], 'is_modified': hf['epoch/is_modified'], 'label': labels})
                    keys = [n.decode('ascii', 'ignore') for n in hf['epoch/keys']]
                    all_labels = [n.decode('ascii', 'ignore') for n in hf['epoch/all_labels']]
                    description = [n.decode('ascii', 'ignore') for n in hf['epoch/description']]
                    default_label = hf['epoch/default_label'][0]
                    NONE_LABEL = hf['epoch/NONE_LABEL'][0]

                    EpochModeConfig.load_from_hdf5(epoch_data, keys, all_labels, default_label, NONE_LABEL, description=description)
            except Exception as e:
                Dialog().warningMessage('Epoch mode data cannot be loaded\r\n' +
                                        'The error was:\r\n' + str(e))

        except Exception as e:
            Dialog().warningMessage('Loading existing annotations failed\r\n' +
                                    'The error was:\r\n' + str(e))

    @abc.abstractmethod
    def save(self, **kwargs):
        # TODO: popup warning when rewriting existing files
        try:
            from gui.viewer import Viewer
            filename = kwargs.get('filename', self.fullpath.stem)

            try:
                filename = self.outputfile_prefix + filename
            except Exception as e:
                qInfo('Output file prefix could not be added')

            fullpath = pathlib.Path(self.output_folder, filename + '.h5')
            OVERWRITE = kwargs.get('OVERWRITE', Viewer.get().settings_menu.save_overwrite_action.isChecked())
            if fullpath.is_file():  # don't overwrite files
                if not OVERWRITE:
                    path, filename = os.path.split(fullpath)
                    filename = os.path.splitext(filename)[0]
                    newfilename = filename + '_' + strftime("%Y_%m_%d_%H_%M_%S", gmtime()) + fullpath.suffix
                    fullpath = pathlib.Path(path, newfilename)
                    qInfo('Existing file found. Not overwriting')
                else:
                    qInfo('Existing file OVERWRITTEN!')

            from logic.operation_mode.annotation import AnnotationConfig
            aConf = AnnotationConfig.get()
            hf = h5py.File(fullpath, 'w')

            group_annotations = hf.create_group('annotations')
            for f_idx, f in enumerate(aConf.fiducials):
                group_annotations.create_group(f.name)
                group_annotations.create_dataset(f.name + '/ts', data=f.annotation.x)
                group_annotations.create_dataset(f.name + '/idx', data=f.annotation.idx)
                group_annotations.create_dataset(f.name + '/amp', data=f.annotation.y)

            group_partitions = hf.create_group('partitions')
            asciiList = [n.encode("ascii", "ignore") for n in Partitions.all_labels()]
            group_partitions.create_dataset('label', data=asciiList)
            group_partitions.create_dataset('start', data=Partitions.all_startpoints())
            group_partitions.create_dataset('end', data=Partitions.all_endpoints())

            group_epoch = hf.create_group('epoch')
            group_epoch.create_dataset('start', data=EpochModeConfig.get().window_data['start'].values)
            group_epoch.create_dataset('end', data=EpochModeConfig.get().window_data['end'].values)
            group_epoch.create_dataset('is_modified', data=EpochModeConfig.get().window_data['is_modified'].values)
            asciiList = [n.encode("ascii", "ignore") for n in EpochModeConfig.get().window_data['label'].values]
            group_epoch.create_dataset('label', data=asciiList)
            asciiList = [n.encode("ascii", "ignore") for n in EpochModeConfig.get().keys]
            group_epoch.create_dataset('keys', data=asciiList)

            asciiList = [n.encode("ascii", "ignore") for n in EpochModeConfig.get().labels]
            group_epoch.create_dataset('all_labels', data=asciiList)

            asciiList = [n.encode("ascii", "ignore") for n in EpochModeConfig.get().description]
            group_epoch.create_dataset('description', data=asciiList)

            dt = h5py.special_dtype(vlen=str)
            group_epoch.create_dataset('default_label', (1,), dtype=dt)
            group_epoch['default_label'][:] = EpochModeConfig.get().default_label
            group_epoch.create_dataset('NONE_LABEL', (1,), dtype=dt)
            group_epoch['NONE_LABEL'][:] = EpochModeConfig.get().NONE_LABEL

            group_meta = hf.create_group('meta')
            dt = h5py.special_dtype(vlen=str)
            group_meta.create_dataset('timestamp', (1,), dtype=dt)
            group_meta['timestamp'][:] = strftime("%Y_%m_%d_%H_%M_%S", gmtime())

            group_meta.create_dataset('filename', (1,), dtype=dt)
            group_meta['filename'][:] = self.fullpath.stem
            group_meta.create_dataset('filepath', (1,), dtype=dt)
            group_meta['filepath'][:] = self.fullpath.parent.as_posix()
            group_meta.create_dataset('main_track_label', (1,), dtype=dt)
            group_meta['main_track_label'][:] = self.main_track_label

            if Viewer.get().settings_menu.save_tracks_action.isChecked():
                group_tracks = hf.create_group('tracks')
                for label, track in Database.get().tracks.items():
                    group_tracks.create_dataset(label + '/ts', data=track.ts)
                    group_tracks.create_dataset(label + '/amp', data=track.value)
                    group_tracks.create_dataset(label + '/offset', data=track.offset)
                    group_tracks.create_dataset(label + '/fs', data=track.fs)

            hf.close()
            qInfo('{} saved'.format(fullpath.as_posix()))
        except Exception as e:
            try:
                hf.close()
            except:
                pass
            self._save_as_csv(filename=self.fullpath.stem, save_idx=False)
            Dialog().warningMessage('Default save crashed\r\n' +
                                    e.__repr__() +
                                    '\r\nSaved using deprecated method, as CSV files.')

    @deprecated('Default way is to save annotations and partitions together as hdf5')
    def _save_as_csv(self, *, filename: str, save_idx: bool):
        from logic.operation_mode.annotation import AnnotationConfig
        aConf = AnnotationConfig.get()
        fullpath = pathlib.Path(self.output_folder, 'annotation_' + filename).as_posix()
        aConf.to_csv(fullpath, save_idx=save_idx)
        fullpath = pathlib.Path(self.output_folder, 'partition_' + filename).as_posix()
        Partitions.to_csv(fullpath)
        fullpath = pathlib.Path(self.output_folder, 'epoch_' + filename).as_posix()
        EpochModeConfig.to_csv(fullpath)
        qInfo('{} saved'.format(fullpath))

    def aConf_is_loaded(self):
        """
        check if the main signal has AnnotationConfiguration loaded
        :return: bool
        """
        if hasattr(self.tracks[self.main_track_label], 'aConf'):
            return True
        return False

    def test_database_setup(self):
        """
        place all asserts\tests in one place
        :return: bool
        """
        # check type of the data (floats) and dimensions
        assert self.output_folder.is_dir(), 'self.output_folder is not a directory'
        assert self.existing_annotations_folder.is_dir(), 'self.existing_annotations_folder is not a directory'
        assert self.DATAPATH.is_dir(), 'self.DATAPATH is not a directory'
        assert self.tracks is not None, 'self.tracks is None'
        assert self.annotation_config_file is not None, 'self.annotation_config_file is None'
        assert self.main_track_label is not None, 'self.main_track_label is None'
        assert len(self.track_labels) == len(set(self.track_labels)),'not all track labels are unique'
        assert self.main_track_label in self.track_labels, 'self.main_track_label is not in self.track_labels'
        assert self.main_track_label in self.tracks_to_plot_initially, 'self.main_track_label not in self.tracks_to_plot_initially'
        assert all([tp in self.track_labels for tp in self.tracks_to_plot_initially]), 'not all self.tracks_to_plot_initially are in self.track_labels'
        assert self.main_track_label in self.track_labels, 'self.main_track_label not in self.track_labels'
        assert not any([' ' in l for l in self.track_labels]),'all self.track_labels should be one word, no spaces'

        # make the main track label to always go first for plotting, otherwise errors will appear for other views, when the main view is not created yet
        main_track_idx = np.argwhere([self.main_track_label == l for l in self.tracks_to_plot_initially])[0][0]
        if not main_track_idx == 0:
            tmp = self.tracks_to_plot_initially[0]
            self.tracks_to_plot_initially[0] = self.main_track_label
            self.tracks_to_plot_initially[main_track_idx] = tmp

        l = [l.get_time()[-1] for l in self.tracks.values()]
        x = np.reshape(l, (len(l), 1))
        x = np.concatenate(x - x.transpose())  # all differences between track durations
        if max(abs(x)) > 1:
            Dialog().warningMessage('Some of the tracks differ in their duration more than {} seconds\r\n'.format(max(abs(x))) +
                                    'You can continue working if this is expected.')
        # assert max(abs(x)) < 0.5  # tracks should be the same duration (0.5 sec difference allowed), otherwise smth is wrong
        pass

    def _set_annotation_from_time(self, fiducial_name, ts):
        assert self.tracks is not None and self.main_track_label is not None
        assert self.aConf_is_loaded()
        assert fiducial_name in [s.name for s in self.tracks[self.main_track_label].aConf.fiducials], '{} fiducial is not listed in {}'.format(
            fiducial_name, self.annotation_config_file.stem)
        from logic.operation_mode.annotation import AnnotationConfig
        aConf = AnnotationConfig.get()
        aConf.fiducials[aConf.find_idx_by_name(fiducial_name)].set_annotation_from_time(ts, self.tracks[self.main_track_label])

    def _set_annotation_from_idx(self, fiducial_name, idx: np.ndarray):
        idx = idx.astype(int)
        assert self.tracks is not None and self.main_track_label is not None, 'tracks are not set or main_track_label is not specified'
        assert self.aConf_is_loaded(), 'annotation configuration is not loaded at the moment you try to set annotation'
        assert fiducial_name in [s.name for s in self.tracks[self.main_track_label].aConf.fiducials]
        from logic.operation_mode.annotation import AnnotationConfig
        aConf = AnnotationConfig.get()
        aConf.fiducials[aConf.find_idx_by_name(fiducial_name)].set_annotation_from_idx(idx, self.tracks[self.main_track_label])

    def _get_matfile_object(self, fullpath: pathlib.Path):
        try:  # MATLAB 7.3 file needs to be loaded as HDF5 [install HDF5 on your pc from hdfgroup.org]
            return h5py.File(fullpath, 'r')
        except OSError as e1:  # MATLAB < 7.3
            try:
                return loadmat(fullpath.as_posix(), struct_as_record=False, squeeze_me=True)
            except Exception as e2:
                Dialog().warningMessage(
                    'Loading {}.mat with h5py.File() failed\r\n'.format(fullpath.stem) + str(
                        e1) + '\r\n' + 'Install HDF5 on your pc from hdfgroup.org\r\n' + 'Now attempting to use loadmat()\r\n')
                Dialog().warningMessage('Sorry, unsuccessful...\r\n' + str(e2))

    def get_all_files_in_database(self):
        tmp = '**/*.' + self.filetype if self.file_template is None else self.file_template
        return list(pathlib.Path(self.DATAPATH).glob(tmp))

    def get_next_database_file(self):
        all_files = self.get_all_files_in_database()
        this_file = self.fullpath.as_posix()
        this_idx = [i for i, s in enumerate(all_files) if this_file in s.as_posix()]
        this_idx = this_idx[0]
        if this_idx < len(all_files) - 1:
            next_file = all_files[this_idx + 1]
        else:
            next_file = None
        return next_file

    def get_prev_database_file(self):
        all_files = self.get_all_files_in_database()
        this_file = self.fullpath.as_posix()
        this_idx = [i for i, s in enumerate(all_files) if this_file in s.as_posix()]
        this_idx = this_idx[0]
        if this_idx > 0:
            prev_file = all_files[this_idx - 1]
        else:
            prev_file = None
        return prev_file

    def get_longest_track_duration(self):
        l = [l.get_time()[-1] for l in self.tracks.values()]
        return max(l)
