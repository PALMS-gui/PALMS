"""
MIT license
Copyright (c) 2005-2017 TimeView Developers
License can be found in gui\LICENSE.txt
"""
import logging
from abc import ABCMeta, abstractmethod
from math import floor, ceil
from typing import List, Union, Tuple, Optional, Type, Dict

import numpy as np
import pyqtgraph as pg
from qtpy import QtCore, QtGui

from gui import tracking

logger = logging.getLogger()
logger.setLevel(logging.INFO)



class Renderer(metaclass=ABCMeta):  # MixIn
    accepts = tracking.Track
    z_value: int = 0
    name = 'metaclass'

    def __init__(self, *args, **parameters):
        self.track: Optional[tracking.Wave] = None
        self.view = None
        self.item: Union[pg.PlotItem, pg.PlotCurveItem, pg.ImageItem, None] = None
        self.ax: Optional[pg.AxisItem] = None
        self.vb: Optional[pg.ViewBox] = None
        self.segments: List[pg.InfiniteLine] = []
        self.names: List[pg.TextItem] = []
        self.filter: Optional[QtCore.QObject] = None
        self.pen: Optional[QtGui.QPen] = None
        self.plot_area: pg.GraphicsView = None
        self.parameters = parameters
        if 'y_min' not in self.parameters:
            self.parameters['y_min'] = 0
        if 'y_max' not in self.parameters:
            self.parameters['y_max'] = 1
        if 'x_min' not in self.parameters:
            self.parameters['x_min'] = 0
        if 'x_max' not in self.parameters:
            self.parameters['x_max'] = 1

    def __str__(self) -> str:
        return self.name

    def set_track(self, track: accepts):
        self.track = track

    def set_view(self, view, **kwargs):
        self.view = view
        self.set_track(view.track)
        self.parameters['y_min'], self.parameters['y_max'] = self.getDefaultYRange()
        self.parameters = {**self.parameters, **kwargs}


    def check_y_limits(self):
        y_min = self.parameters['y_min']
        y_max = self.parameters['y_max']

        if y_min >= y_max:
            logger.warning('y-min value set greater or equal to y-max value')
            return False
        return True

    def check_x_limits(self):
        x_min = self.parameters['x_min']
        x_max = self.parameters['x_max']

        if x_min >= x_max:
            logger.warning('x-min value set greater or equal to x-max value')
            return False
        return True

    def get_parameters(self) -> Dict[str, str]:
        return {k: str(v) for k, v in self.parameters.items()}

    def strColor(self) -> str:
        q_color = QtGui.QColor.fromRgb(self.view.color[0], self.view.color[1], self.view.color[2])
        return f'#{pg.colorStr(q_color)[:6]}'

    def setAxisLabel(self):
        self.ax.setLabel(self.track.label, color=self.strColor(), units=self.track.unit)

    def configNewAxis(self):
        assert isinstance(self.ax, pg.AxisItem)
        assert isinstance(self.vb, pg.ViewBox)
        self.ax.setZValue(self.z_value)
        axis_width = self.plot_area.main_window.axis_width
        self.setAxisLabel()
        self.ax.linkToView(self.vb)
        if self.ax.preferredWidth() <= axis_width:
            self.ax.setWidth(w=axis_width)
        old_axis = self.plot_area.layout.getItem(0, 0)
        if isinstance(old_axis, pg.AxisItem):
            if old_axis.width() > self.ax.width():
                axis_width = old_axis.width()
                self.ax.setWidth(w=axis_width)
            self.plot_area.layout.removeItem(old_axis)
        self.ax.update()
        self.plot_area.layout.addItem(self.ax, row=0, col=0)
        """
        By default the major bottom (x) axis of the plot area has its tick labels hidden, 
        in case multiple plotted signals are not synced. Each time a new view is added a separate GridItem is created.
        pg.GridItem() does not accept any inputs, thus changing grid line style has to be done inside, 
        or GridItem class needs an update.
        """
        gr = pg.GridItem()
        self.vb.addItem(gr)
        self.ax.geometryChanged.connect(self.plot_area.maxWidthChanged)

    def configNewViewBox(self):
        assert isinstance(self.vb, pg.ViewBox)
        self.setLimits()
        self.vb.setZValue(self.z_value)
        self.vb.setXLink(self.plot_area.main_vb)
        self.plot_area.layout.addItem(self.vb, row=0, col=1)
        self.vb.temporary_items = []

    def render(self, plot_area) -> Tuple[pg.AxisItem, pg.ViewBox]:
        """generates pg.AxisItem and pg.ViewBox"""
        self.plot_area = plot_area
        self.generateBlankPlotItems()
        self.vb.setMouseEnabled(x=True, y=False)
        self.vb.setMenuEnabled(False)
        # self.vb.enableAutoRange(axis=pg.ViewBox.XYAxes)
        return self.ax, self.vb

    @abstractmethod
    def reload(self):
        """clears current plot items, and reloads the track"""

    @abstractmethod
    def perRendererParameterProcessing(self, parameters):
        """depending on what the parameters changed call different methods"""

    @abstractmethod
    def generateBlankPlotItems(self):
        """creates plot items"""

    @abstractmethod
    def getDefaultYRange(self) -> Tuple[Union[int, float], Union[int, float]]:
        """returns the default y-bounds of this renderer"""

    def changePen(self):
        """changes the color/colormap of the plot"""
        self.setPen()
        self.setAxisLabel()
        self.item.setPen(self.pen)

    def setPen(self):
        self.pen = pg.mkPen(self.view.color)

    def setLimits(self):
        assert isinstance(self.vb, pg.ViewBox)
        self.check_y_limits()
        self.check_x_limits()
        self.vb.setYRange(self.parameters['y_min'], self.parameters['y_max'])
        self.vb.setLimits(yMin=self.parameters['y_min'], yMax=self.parameters['y_max'], xMin=self.parameters['x_min'],
                          xMax=self.parameters['x_max'])
        self.vb.enableAutoRange(axis='y', enable=True)
        self.vb.setAutoPan(x=True, y=True)
        self.vb.setAutoVisible(y=True)


def get_renderer_classes(accepts: Optional[tracking.Track] = None) -> List[Type[Renderer]]:
    def all_subclasses(c: Type[Renderer]):
        return c.__subclasses__() + [a for b in c.__subclasses__() for a in all_subclasses(b)]

    if accepts is None:
        return [obj for obj in all_subclasses(Renderer) if obj.accepts is not None]
    else:
        return [obj for obj in all_subclasses(Renderer) if accepts in obj.accepts]


# first renderer will be the default for that track type
# | | |
# v v v
class Waveform(Renderer):
    name = 'Waveform'
    accepts = [tracking.Wave, tracking.Derived]
    z_value = 10

    def getDefaultYRange(self) -> Tuple[float, float]:
        if self.track.min and self.track.max:
            return self.track.min, self.track.max
        else:
            return {np.dtype('int16'): (-32768, 32768), np.dtype('float'): (-1, 1)}[self.track.viewvalue.dtype]

    def reload(self):
        # TODO: waveform needs some kind of update scheme
        pass

    def perRendererParameterProcessing(self, parameters):
        # TODO: look at parameters and modify things accordingly
        pass

    def generateBlankPlotItems(self):
        self.item = pg.PlotDataItem()  # PlotCurveItem()
        self.item.setClipToView(True)
        self.item.setDownsampling(ds=1, auto=False, method='subsample')  # TODO: set downsampling for plotting!!! PARAMETRIZE via GUI
        # TODO: check https://stackoverflow.com/questions/30497997/using-pre-downsampled-data-when-plotting-large-time-series-in-pyqtgraph
        self.item.setZValue(self.z_value)
        self.vb = pg.ViewBox()
        self.vb.addItem(self.item, ignoreBounds=True)
        self.ax = pg.AxisItem('left', showValues=False)  # ticks are disabled, because each view has separately created GridItem()
        self.configNewAxis()
        self.configNewViewBox()
        self.vb.setMouseEnabled(x=True, y=False)
        self.vb.sigXRangeChanged.connect(self.generatePlotData, QtCore.Qt.DirectConnection)

    def generatePlotData(self):
        # don't bother computing if there is no screen geometry
        if not self.vb.width():
            return
        # x_min, x_max = self.plot_area.main_vb.viewRange()[0]
        x_min, x_max = self.vb.viewRange()[0]
        start = max([int(0), int(floor(x_min * self.track.fs))])
        assert start >= 0
        if start > self.track.duration:
            return
        stop = min([self.track.duration, int(ceil(x_max * self.track.fs)) + 1])
        ds = int(round((stop - start) / self.vb.screenGeometry().width())) + 1
        if ds <= 0:
            logger.exception('ds should be > 0')
            return

        if ds == 1:
            visible = self.track.viewvalue[start:stop]
        else:
            samples = 1 + ((stop - start) // ds)
            visible = np.empty(samples * 2, dtype=self.track.viewvalue.dtype)
            source_pointer = start
            target_pointer = 0

            chunk_size = int(round((1e6 // ds) * ds))
            # assert isinstance(source_pointer, int)
            # assert isinstance(chunk_size, int)
            while source_pointer < stop - 1:
                chunk = self.track.viewvalue[source_pointer:min([stop, source_pointer + chunk_size])]
                source_pointer += len(chunk)
                chunk = chunk[:(len(chunk) // ds) * ds].reshape(len(chunk) // ds, ds)
                chunk_max = chunk.max(axis=1)
                chunk_min = chunk.min(axis=1)
                chunk_len = chunk.shape[0]
                visible[target_pointer:target_pointer + chunk_len * 2:2] = chunk_min
                visible[1 + target_pointer:1 + target_pointer + chunk_len * 2:2] = chunk_max
                target_pointer += chunk_len * 2
            visible = visible[:target_pointer]
        self.item.setData(x=np.linspace(start, stop, num=len(visible), endpoint=True) / self.track.fs, y=visible, pen=self.view.color)
