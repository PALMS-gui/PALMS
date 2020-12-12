import errno
import os
import pathlib
import sys
from typing import Tuple, Union

import numpy as np
import pandas as pd
import scipy
from scipy import signal
from scipy.signal import butter, filtfilt

from utils import detect_peaks


def get_spectrum_peaks(s: np.ndarray, Fs: int, npeaks: int = 1, limits: list = None) -> list:
    # s = data_raw['gyro_2']-np.mean(data_raw['gyro_2'])
    f, Pxx_spec = scipy.signal.welch(s, Fs, 'flattop', nperseg=Fs * 10, noverlap=round(Fs * 10 / 2), nfft=4096, scaling='spectrum',
                                     detrend=False)
    if limits is not None:
        idxs = np.argwhere(np.bitwise_and(f >= limits[0], f <= limits[1]))
        idxs = np.stack(idxs, axis=1)[0]
        f = f[idxs]
        Pxx_spec = Pxx_spec[idxs]

    peak_ind = detect_peaks.detect_peaks(np.log10(np.sqrt(Pxx_spec)), mpd=0.25 // np.diff(f)[0], show=False)
    amp = np.log10(np.sqrt(Pxx_spec))[peak_ind]
    # peak_ind = peak_ind[amp>0]
    # amp = amp[amp>0]
    max_peak_ind = peak_ind[np.argsort(amp)[::-1][:npeaks]]
    max_peak_freq = f[max_peak_ind]

    if 0:
        plt.figure()
        plt.semilogy(f, np.sqrt(Pxx_spec))
        plt.xlabel('frequency [Hz]')
        plt.ylabel('Linear spectrum [V RMS]')
        plt.title('Power spectrum (scipy.signal.welch)')
        plt.show()
    return max_peak_freq


def dict_to_df_with_nans(d: dict) -> pd.DataFrame:
    return pd.DataFrame(dict([(k, pd.Series(v)) for k, v in d.items()]))


def silentremove(filename):
    try:
        os.remove(filename)
    except OSError as e:  # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
            raise  # re-raise exception if a different error occurred


def round_to_odd(x: float) -> int:
    if int(x) % 2 == 0:
        return int(x) + 1
    else:
        return int(x)


def get_project_root() -> pathlib.Path:
    """Returns project root folder."""
    return pathlib.Path(sys.argv[0]).parent.absolute()

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = get_project_root()

    return pathlib.Path(base_path, relative_path).resolve()


def list_intersection(lst1: list, lst2: list) -> list:
    if lst1 is None or lst2 is None:
        return []
    return sorted(list(set(lst1) & set(lst2)))


def list_difference(lst1: list, lst2: list) -> list:
    """ be aware it returns what is in lst1 and not in lst2. search for symmetrical difference in case you also need what in lst2 and not in lst1"""
    return list(set(lst1) - set(lst2))

def string_to_path(string:Union[str,pathlib.Path])->pathlib.Path:
    if isinstance(string,str):
        return pathlib.Path(string)
    elif isinstance(string,pathlib.Path):
        return string
    else:
        raise TypeError


def butter_highpass(cutoff, fs, order=2):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='high', analog=False)
    return b, a

def butter_highpass_filter(data, cutoff, fs, order=2):
    b, a = butter_highpass(cutoff, fs, order=order)
    y = filtfilt(b, a, data)
    return y

def butter_lowpass(cutoff, fs, order=2):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return b, a

def butter_lowpass_filter(data, cutoff, fs, order=2):
    b, a = butter_lowpass(cutoff, fs, order=order)
    y = filtfilt(b, a, data)
    return y


def find_closest(input_array: np.ndarray, target_array: np.ndarray, tol: float = 1e6) -> Tuple[np.ndarray, ...]:
    """
    Find the set of elements in input_array that are closest to
    elements in target_array.  Record the indices of the elements in
    target_array that are within tolerance, tol, of their closest
    match. Also record the indices of the elements in target_array
    that are outside tolerance, tol, of their match.

    For example, given an array of observations with irregular
    observation times along with an array of times of interest, this
    routine can be used to find those observations that are closest to
    the times of interest that are within a given time tolerance.

    NOTE: input_array must be sorted! The array, target_array, does not have to be sorted.

    Inputs:
      input_array:  a sorted Float64 np
      target_array: a Float64 np
      tol:          a tolerance

    Returns:
      closest_indices:  the array of indices of elements in input_array that are closest to elements in target_array
      accept_indices:  the indices of elements in target_array that have a match in input_array within tolerance
      reject_indices:  the indices of elements in target_array that do not have a match in input_array within tolerance
    """

    input_array_len = len(input_array)
    closest_indices = np.searchsorted(input_array, target_array)  # determine the locations of target_array in input_array
    acc_rej_indices = [-1] * len(target_array)
    curr_tol = [tol] * len(target_array)

    est_tol = 0.0
    for i in range(len(target_array)):
        best_off = 0  # used to adjust closest_indices[i] for best approximating element in input_array

        if closest_indices[i] >= input_array_len:
            # the value target_array[i] is >= all elements in input_array so check whether it is within tolerance of the last element
            closest_indices[i] = input_array_len - 1
            est_tol = target_array[i] - input_array[closest_indices[i]]
            if est_tol < curr_tol[i]:
                curr_tol[i] = est_tol
                acc_rej_indices[i] = i
        elif target_array[i] == input_array[closest_indices[i]]:
            # target_array[i] is in input_array
            est_tol = 0.0
            curr_tol[i] = 0.0
            acc_rej_indices[i] = i
        elif closest_indices[i] == 0:
            # target_array[i] is <= all elements in input_array
            est_tol = input_array[0] - target_array[i]
            if est_tol < curr_tol[i]:
                curr_tol[i] = est_tol
                acc_rej_indices[i] = i
        else:
            # target_array[i] is between input_array[closest_indices[i]-1] and input_array[closest_indices[i]]
            # and closest_indices[i] must be > 0
            top_tol = input_array[closest_indices[i]] - target_array[i]
            bot_tol = target_array[i] - input_array[closest_indices[i] - 1]
            if bot_tol <= top_tol:
                est_tol = bot_tol
                best_off = -1  # this is the only place where best_off != 0
            else:
                est_tol = top_tol

            if est_tol < curr_tol[i]:
                curr_tol[i] = est_tol
                acc_rej_indices[i] = i

        if est_tol <= tol:
            closest_indices[i] += best_off

    accept_indices = np.compress(np.greater(acc_rej_indices, -1), acc_rej_indices)
    reject_indices = np.compress(np.equal(acc_rej_indices, -1), np.arange(len(acc_rej_indices)))
    return closest_indices, accept_indices, reject_indices
