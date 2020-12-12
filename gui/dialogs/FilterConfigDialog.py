"""
Copyright (c) 2020 Stichting imec Nederland (PALMS@imec.nl)
https://www.imec-int.com/en/imec-the-netherlands
@license GPL-3.0+ <http://spdx.org/licenses/GPL-3.0+>
See COPYING, README.
"""
from _weakrefset import WeakSet
from functools import partial

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QVBoxLayout, QSlider, QGroupBox, QGridLayout, QLabel, QStyle, QStyleOptionSlider
import numpy as np

from utils.utils_general import butter_highpass_filter, butter_lowpass_filter


class DoubleSlider(QSlider):
    # create our our signal that we can connect to if necessary
    doubleValueChanged = pyqtSignal(float)

    def __init__(self, decimals=1, *args, **kwargs):
        super(DoubleSlider, self).__init__(*args, **kwargs)
        self._multi = 10 ** decimals

        self.valueChanged.connect(self.emitDoubleValueChanged)

    def emitDoubleValueChanged(self):
        value = float(super(DoubleSlider, self).value()) / self._multi
        self.doubleValueChanged.emit(value)

    def value(self):
        return float(super(DoubleSlider, self).value()) / self._multi

    def setMinimum(self, value):
        return super(DoubleSlider, self).setMinimum(value * self._multi)

    def setMaximum(self, value):
        return super(DoubleSlider, self).setMaximum(value * self._multi)

    def setSingleStep(self, value):
        return super(DoubleSlider, self).setSingleStep(value * self._multi)

    def singleStep(self):
        return float(super(DoubleSlider, self).singleStep()) / self._multi

    def setValue(self, value):
        super(DoubleSlider, self).setValue(int(value * self._multi))

class LabeledSlider(QtWidgets.QWidget):
    # TODO: make it accept float steps, adjust max\min
    # TODO: add labels https://stackoverflow.com/questions/47494305/python-pyqt4-slider-with-tick-labels
    def __init__(self, minimum, maximum, interval=1, orientation=Qt.Horizontal, labels=None, parent=None):
        super(LabeledSlider, self).__init__(parent=parent)

        levels = range(minimum, maximum + interval, interval)
        if labels is not None:
            if not isinstance(labels, (tuple, list)):
                raise Exception("<labels> is a list or tuple.")
            if len(labels) != len(levels):
                raise Exception("Size of <labels> doesn't match levels.")
            self.levels = list(zip(levels, labels))
        else:
            self.levels = list(zip(levels, map(str, levels)))

        if orientation == Qt.Horizontal:
            self.layout = QtWidgets.QVBoxLayout(self)
        elif orientation == Qt.Vertical:
            self.layout = QtWidgets.QHBoxLayout(self)
        else:
            raise Exception("<orientation> wrong.")

        # gives some space to print labels
        self.left_margin = 10
        self.top_margin = 10
        self.right_margin = 10
        self.bottom_margin = 10

        self.layout.setContentsMargins(self.left_margin, self.top_margin, self.right_margin, self.bottom_margin)

        self.slider = QtWidgets.QSlider(orientation, self)
        self.slider.setMinimum(minimum)
        self.slider.setMaximum(maximum)
        self.slider.setValue(minimum)
        if orientation == Qt.Horizontal:
            self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
            self.slider.setMinimumWidth(300)  # just to make it easier to read
        else:
            self.slider.setTickPosition(QtWidgets.QSlider.TicksLeft)
            self.slider.setMinimumHeight(300)  # just to make it easier to read
        self.slider.setTickInterval(interval)
        self.slider.setSingleStep(interval)
        self.slider.setPageStep(interval)

        self.layout.addWidget(self.slider)

    def paintEvent(self, e):

        super(LabeledSlider, self).paintEvent(e)

        style = self.slider.style()
        painter = QPainter(self)
        st_slider = QStyleOptionSlider()
        st_slider.initFrom(self.slider)
        st_slider.orientation = self.slider.orientation()

        length = style.pixelMetric(QStyle.PM_SliderLength, st_slider, self.slider)
        available = style.pixelMetric(QStyle.PM_SliderSpaceAvailable, st_slider, self.slider)

        for v, v_str in self.levels:

            # get the size of the label
            rect = painter.drawText(QRect(), Qt.TextDontPrint, str(v_str))

            if self.slider.orientation() == Qt.Horizontal:
                # I assume the offset is half the length of slider, therefore
                # + length//2
                x_loc = QStyle.sliderPositionFromValue(self.slider.minimum(), self.slider.maximum(), v, available) + length // 2

                # left bound of the text = center - half of text width + L_margin
                left = x_loc - rect.width() // 2 + self.left_margin
                bottom = self.rect().bottom()

                # enlarge margins if clipping
                if v == self.slider.minimum():
                    if left <= 0:
                        self.left_margin = rect.width() // 2 - x_loc
                    if self.bottom_margin <= rect.height():
                        self.bottom_margin = rect.height()

                    self.layout.setContentsMargins(self.left_margin, self.top_margin, self.right_margin, self.bottom_margin)

                if v == self.slider.maximum() and rect.width() // 2 >= self.right_margin:
                    self.right_margin = rect.width() // 2
                    self.layout.setContentsMargins(self.left_margin, self.top_margin, self.right_margin, self.bottom_margin)

            else:
                y_loc = QStyle.sliderPositionFromValue(self.slider.minimum(), self.slider.maximum(), v, available, upsideDown=True)

                bottom = y_loc + length // 2 + rect.height() // 2 + self.top_margin - 3
                # there is a 3 px offset that I can't attribute to any metric

                left = self.left_margin - rect.width()
                if left <= 0:
                    self.left_margin = rect.width() + 2
                    self.layout.setContentsMargins(self.left_margin, self.top_margin, self.right_margin, self.bottom_margin)

            pos = QPoint(left, bottom)
            painter.drawText(pos, str(v_str))

        return


class FilterConfigDialog(QtWidgets.QDialog):
    _instances = WeakSet()  # keep weak references to every instance of this class

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self._instances.add(self)
        self.application = app  # TODO: make main_window accesible, not app
        self.setWindowTitle('Filter Configuration')
        self.setMinimumSize(540, 30)  # TODO: resize automatically to fit everything
        self.resize(540, 30)

    def createFilterGroup(self, header: str, min: int, max: int, interval:int=1):  # https://pythonprogramminglanguage.com/pyqt5-sliders/
        labels = list(np.arange(min, max + interval, interval))

        groupBox = QGroupBox(header)
        groupBox.labeled_slider = LabeledSlider(min, max, interval, orientation=QtCore.Qt.Horizontal,labels=labels)
        groupBox.labeled_slider.setFocusPolicy(QtCore.Qt.StrongFocus)

        # slider = DoubleSlider(decimals=1)
        # slider.setMaximum(max)
        # slider.setMinimum(min)
        # slider.setTickPosition(QSlider.TicksBothSides)
        # slider.setTickInterval(1)
        # slider.setSingleStep(0.1)
        # label = QLabel()
        # label.setText(str(slider.value()))

        vbox = QVBoxLayout()
        vbox.addWidget(groupBox.labeled_slider)
        # vbox.addWidget(label)
        vbox.addStretch(1)
        groupBox.setLayout(vbox)

        return groupBox

    def set_layout(self,view):
        self.layoutVertical = QtWidgets.QVBoxLayout(self)
        self.groupbox_lpf = self.createFilterGroup('LPF', 0, 10, 1)
        self.groupbox_hpf = self.createFilterGroup('HPF', 0, 10, 1)

        self.pushButton_filter = QtWidgets.QPushButton(self)
        self.pushButton_filter.setText('Filter ' + view.track.label)
        self.pushButton_filter.clicked.connect(partial(self.on_clicked_filter, view))

        self.pushButton_reset = QtWidgets.QPushButton(self)
        self.pushButton_reset.setText('Reset ' + view.track.label)
        self.pushButton_reset.clicked.connect(partial(self.on_clicked_reset, view))

        self.layoutVertical.addWidget(self.groupbox_lpf)
        self.layoutVertical.addWidget(self.groupbox_hpf)
        self.layoutVertical.addWidget(self.pushButton_filter)
        self.layoutVertical.addWidget(self.pushButton_reset)
        # spacerItem = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        # self.layoutVertical.addItem(spacerItem)
        self.layoutVertical.setAlignment(QtCore.Qt.AlignCenter)
        self.layoutVertical.setContentsMargins(0, 0, 0, 0)

    def show(self, view):
        self.__init__(self.application)
        self.set_layout(view)
        self.adjustSize()
        super().show()

    def on_clicked_reset(self, view):
        view.track.reset_viewvalue()
        self.groupbox_hpf.labeled_slider.slider.setValue(0)
        self.groupbox_lpf.labeled_slider.slider.setValue(0)

    def on_clicked_filter(self, view):
        hpf = self.groupbox_hpf.labeled_slider.slider.value()
        lpf = self.groupbox_lpf.labeled_slider.slider.value()
        if hpf<=lpf:
            Warning('HPF < LPF')
        if not hpf<=lpf:
            y = view.track.value
            if not (hpf == 0):
                y = butter_highpass_filter(y, hpf, view.track.fs)
            if not (lpf == 0):
                y = butter_lowpass_filter(y, lpf, view.track.fs)

            view.track.viewvalue = y
        #TODO: still not finished, not clear what should annotations be pinned to, etc...
        # should filtered wave become a separete track or saved within current track as self.viewvalue(as it is now)
