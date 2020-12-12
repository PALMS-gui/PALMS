"""
Copyright (c) 2020 Stichting imec Nederland (https://www.imec-int.com/en/imec-the-netherlands)
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
import os
import pathlib

import pandas as pd
from PyQt5.QtCore import qInfo

from gui.tracking import Wave
from logic.databases.DatabaseHandler import Database
from utils.utils_general import get_project_root, butter_highpass_filter, butter_lowpass_filter, resource_path
from utils.utils_gui import Dialog
import numpy as np
from utils.QRSDetectorOffline import QRSDetectorOffline as PanTomkinsQRSDetector

#NB: for this example to work one needs to put some of the PhysioNet/CinC Challenge 2011 .txt data files into docs\examples\example_Physionet2011
# https://archive.physionet.org/physiobank/database/challenge/2011/

class ECG_Physionet2011(Database):  # NB: !!!!!!!!!!!  class name should be equal to database name (this filename)
    def __init__(self):
        super().__init__()
        self.filetype = 'txt'  # NB: files to be used as source of the data
        self.DATAPATH = pathlib.Path(r'')  # NB: top-level folder with the data
        self.file_template = r'**/*' + r'.' + self.filetype or '**/*.' + self.filetype  # NB: source file filter, also in subfolders
        self.output_folder: pathlib.Path = self.DATAPATH  # NB: where to save files; it is overwritten in self.save() once file location is known
        self.existing_annotations_folder: pathlib.Path = self.output_folder  # NB: where to look for existing annotations
        self.main_track_label = 'ecg_filt'   # NB: signal to which all annotations will apply, should be one of the labels assigned in self.get_data()
        self.tracks_to_plot_initially = [self.main_track_label]  # NB: signals to be visible from the start of the app
        # NB: see !README_AnnotationConfig.xlsx: in this case we want to annotate 2 fiducial: peak and foot
        self.annotation_config_file = resource_path(pathlib.Path('config', 'AnnotationConfig', 'AnnotationConfig_ECG.csv'))
        self.epoch_config_file = resource_path(pathlib.Path('config', 'EpochConfig', 'EpochConfig_ECG_Physionet2011.csv'))
        self.RR_interval_as_HR = True  # NB: True: RR intervals in BPM, False: in seconds
        self.outputfile_prefix = ''  # NB: set here your initials, to distinguish multiple annotators' files
        assert 'csv' in self.annotation_config_file.suffix, 'Currently only .csv are supported as annotation configuration'

    def get_data(self, filename):
        # NB: here one needs to define the way data is fetched from the source
        #  In the end the annotated signal and all references have to be defined as Wave-instances

        # NB: 1. Run base class to initialize some variables:
        super().get_data(filename)
        # self.output_folder = self.fullpath.parent  # to save in the same location
        # self.output_folder = get_project_root()  # to save in project root/near the executable
        self.output_folder = self.fullpath.parent
        self.existing_annotations_folder = self.output_folder

        # NB: 2. Fetch data from self.fullpath and create tracks: Dict[label:str,track:Wave]
        #  At this step signals from the source can be filtered (one also can have multiple versions of the same signal),
        #  resampled (for faster browsing when zoom-in/zoom-out), sync, etc.

        tracks = {}
        # NB: 2.1 Load data from a file
        txt_data = pd.read_csv(self.fullpath.as_posix(), header=None)
        ecg = txt_data.iloc[:, 1].values
        Fs_ecg = 500

        ecg_data = ecg
        # NB: 2.2 Convert\preprocess data, create new representations

        ecg_data_filt = butter_highpass_filter(ecg_data, 0.05, Fs_ecg, order=2)  # NB: created and filtered data
        ecg_data_filt = butter_lowpass_filter(ecg_data_filt, 40, Fs_ecg, order=2)

        # NB 3. Create tracks and save them to the DB
        # signals start at time=0
        ecg = Wave(ecg_data, Fs_ecg, label='ecg', filename=self.fullpath.parts[-1][:-1])
        ecg_filt = Wave(ecg_data_filt, Fs_ecg, label='ecg_filt', filename=self.fullpath.parts[-1][:-1])

        for s in [ecg_filt, ecg]:
            tracks[s.label] = s

        self.tracks = tracks
        self.track_labels = list(tracks.keys())
        self.tracks_to_plot_initially = self.track_labels
        super().test_database_setup()  # NB: test to early catch some of the DB initialization errors
        return tracks

    def set_annotation_data(self):
        # NB: used to set initial guesses for annotations, otherwise, one has to start annotation from scratch
        #  one can use here simple findpeaks() type algos, or more signal-specific python algorigthms
        #  also possible to run an algo beforehand (e.g. in Matlab), store the results and load them here

        # NB: OPTIONAL!!! Load existing annotation if an .h5 file with the same name found in self.existing_annotation_folder (be careful with self.outputfile_prefix)
        existing_annotation_file = pathlib.Path(self.existing_annotations_folder, self.fullpath.stem + '.h5')
        existing_annotation_file_with_prefix = pathlib.Path(self.existing_annotations_folder, self.outputfile_prefix + self.fullpath.stem + '.h5')

        existing_annotation_files = self.get_annotation_file(self.fullpath.stem)
        if existing_annotation_files is not None:
            latest_file_idx = np.argmax([os.path.getmtime(f) for f in existing_annotation_files])
            try:
                self.load(existing_annotation_files[latest_file_idx])
                qInfo('Loading annotations from {}'.format(existing_annotation_file_with_prefix))
            except Exception as e:
                Dialog().warningMessage('Loading annotations from {} failed\r\n'.format(existing_annotation_file_with_prefix) + str(e))
        else:
            # # NB: 1. Find\fetch preliminary annotation data
            ecg = self.tracks[self.main_track_label].value
            fs = self.tracks[self.main_track_label].fs
            try:
                qrs_detector = PanTomkinsQRSDetector(ecg, fs, verbose=True, log_data=False, plot_data=False, show_plot=False)

                # # NB: 2. Use inherited functions to assign annotations to the main signal
                # #  all annotation labels should be also in the provided AnnotationConfig file
                # #  User can use _set_annotation_from_time or _set_annotation_from_idx
                self._set_annotation_from_idx('rpeak', qrs_detector.qrs_peaks_indices)
            except Exception as e:
                Dialog().warningMessage('Failed to use beat detector\r\n'
                                        'Currently you do not have any initial annotations loaded, but\r\n'
                                        'You can fix the issue, or implement another way in set_annotation_data()')

    def save(self, **kwargs):
        # NB: save annotation data. By default annotations and partitions are saved as .h5 file.
        #  All tracks can be saved too (see Settings in the menu bar).
        #  One can also define custom save protocol here
        # self.output_folder = self.fullpath.parent  # to save in the same location
        # self.output_folder = get_project_root()  # to save in project root/near the executable
        try:
            self.output_folder = self.fullpath.parent
            super().save(filename=self.fullpath.stem, **kwargs)
        except Exception as e:
            Dialog().warningMessage('Save crashed with: \r\n' + str(e))

    def load(self, filename):
        # NB: load previously saved annotations and partitions.
        #  Inherited method loads data from .h5 files, but one can define custom protocol here
        super().load(filename)
