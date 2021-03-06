import warnings
import time

from PyQt4 import Qt
import pyqtgraph as pg
import pyqtgraph.opengl as gl
import pyqtgraph.dockarea
import numpy as np

from window import WindowMultiPlot

class MyDockArea(pg.dockarea.DockArea):
    def __init__(self, *args, **kwargs):
        pg.dockarea.DockArea.__init__(self, *args, **kwargs)
        self.insert_location = 'bottom'
        self.last_dock, self.second_last_dock = None, None
        self._docks = {}
        self.max_plot_count = 4
        self.update_log = []

    def remove_dock(self, dock):
        dock.setParent(None)
        dock.label.setParent(None)

        if not isinstance(dock, ItemWidget):
            return

        dock.label.hide()

        if len(dock._container.children()) is 0 and dock._container is not self.topContainer:
            dock._container.setParent(None)

        if self.insert_location == 'bottom':
            if dock is self.last_dock:
                self.last_dock = self.second_last_dock
                self.insert_location = 'right'
            elif dock is self.second_last_dock:
                self.insert_location = 'right'
        elif dock is self.last_dock:
                self.insert_location = 'bottom'

        if isinstance(dock, Rank2ItemWidget):
            if dock.img_view.cross_section_enabled:
                dock.img_view.hide_cross_section()

        self._docks.pop(dock.ident)
        dock.window_item.update_tree_item(visible=False)

    def set_max_plots(self, n):
        self.max_plot_count = n

    def add_dock_auto_location(self, dock):
        self._docks[dock.ident] = dock
        if not dock.label.isVisible():
            dock.label.show()
        dock.timestamp = time.time()
        while len(self._docks) > self.max_plot_count:
            least_recently_edited = sorted(self._docks.values(), key=lambda d: d.timestamp)[0]
            self.remove_dock(least_recently_edited)

        if self.insert_location == 'right':
            self.addDock(dock, self.insert_location, self.last_dock)
        else:
            self.addDock(dock, self.insert_location)
        self.insert_location = {'bottom':'right', 'right':'bottom'}[self.insert_location]
        self.second_last_dock, self.last_dock = self.last_dock, dock

    def hide_all_but(self, dock):
        for d in self._docks.values():
            if d is not dock:
                self.remove_dock(d)

class NodeEditWidget(Qt.QFrame):
    def __init__(self, path, attrs):
        Qt.QFrame.__init__(self)
        self.setFrameStyle(Qt.QFrame.Panel)
        self.path = path
        self.spin_widgets = {}
        self.proxy = None

        self.setLayout(Qt.QVBoxLayout())
        self.layout().addWidget(Qt.QLabel('Editing ' + '/'.join(self.path)))

        self.attr_list = Qt.QTreeWidget()
        self.attr_list.setRootIsDecorated(False)
        self.attr_list.setColumnCount(2)
        self.attr_list.setHeaderLabels(['Name', 'Value', 'Type'])

        for attr, value in attrs.items():
            self.attr_list.addTopLevelItem(Qt.QTreeWidgetItem([attr, self.repr_value(value), str(type(value))]))

        add_attr_box = Qt.QWidget()
        add_attr_box.setLayout(Qt.QHBoxLayout())
        self.attr_name_edit = Qt.QLineEdit()
        self.attr_value_edit = Qt.QLineEdit()
        self.attr_value_edit.returnPressed.connect(self.add_attribute)
        self.attr_list.itemClicked.connect(self.attr_clicked)
        self.add_attr_button = Qt.QPushButton('Add Attribute')
        self.add_attr_button = Qt.QPushButton('Add Attribute')
        self.add_attr_button.clicked.connect(self.add_attribute)
        add_attr_box.layout().addWidget(Qt.QLabel('name'))
        add_attr_box.layout().addWidget(self.attr_name_edit)
        add_attr_box.layout().addWidget(Qt.QLabel('value'))
        add_attr_box.layout().addWidget(self.attr_value_edit)
        add_attr_box.layout().addWidget(self.add_attr_button)

        self.new_attr = True
        self.attr_name_edit.textChanged.connect(self.check_attr_name)
        self.layout().addWidget(self.attr_list)
        self.layout().addWidget(add_attr_box)

        self.attr_list_items = {}

    def repr_value(self, v):
        if isinstance(v, float) and v > 1e4:
            return '%.2e' % v
        else:
            return str(v)

    def set_proxy(self, proxy):
        self.proxy = proxy

    def update_attrs(self, attrs):
        for k, v in attrs.items():
            if k not in self.attr_list_items:
                item = Qt.QTreeWidgetItem([k, self.repr_value(v), str(type(v))])
                self.attr_list_items[k] = item
                self.attr_list.addTopLevelItem(item)
            else:
                self.attr_list_items[k].setText(1, self.repr_value(v))
                self.attr_list_items[k].setText(2, str(type(v)))

    def check_attr_name(self, name):
        if any(i.text(0) == name for i in self.attr_list.findItems("", Qt.Qt.MatchContains)):
            if self.new_attr:
                self.new_attr = False
                self.add_attr_button.setText('Update Attribute')
        else:
            if not self.new_attr:
                self.new_attr = True
                self.add_attr_button.setText('Add Attribute')


    def attr_clicked(self, item):
        self.attr_name_edit.setText(item.text(0))
        self.attr_value_edit.setText(item.text(1))

    def add_attribute(self):
        name = str(self.attr_name_edit.text())
        value = str(self.attr_value_edit.text())
        if value.lower() in ('true', 'false'):
            if value.lower() == 'false':
                value = False
            else:
                value = True
        else:
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass

        if self.proxy is not None:
            self.proxy.set_attrs(**{name: value})
        else:
            if self.new_attr:
                self.attr_list.addTopLevelItem(Qt.QTreeWidgetItem([name, self.repr_value(value), str(type(value))]))
            else:
                i = self.attr_list.findItems(name, Qt.Qt.MatchExactly, 0)[0]
                i.setText(1, str(value))
            self.attr_name_edit.setText("")
            self.attr_value_edit.setText("")
            return name, value


class ItemWidget(pg.dockarea.Dock):
    dock_area = None
    def __init__(self, item, **kwargs):
        ident = item.strpath

        label_text = item.path[-1]
        for p in reversed(item.path[:-1]):
            new_label_text = p + '/' + label_text
            if len(new_label_text) > 25:
                label_text = '...' + label_text
                break
            label_text = new_label_text

        if ' :: ' in label_text and len(label_text) > 35:
            label_text = 'multiplot'

        pointSize = 14 if len(label_text) < 30 else 12

        pg.dockarea.Dock.__init__(self, label_text)
        self.timestamp = time.time()
        self.label.setFont(Qt.QFont('Helvetica', pointSize=pointSize))
        self.ident = ident
        self.window_item = item

        self.plots_widget = Qt.QWidget()
        self.plots_widget.setLayout(Qt.QVBoxLayout())
        self.addWidget(self.plots_widget)

        self.add_plot_widget(**kwargs)

        self.buttons_widget = Qt.QWidget() #QHBoxWidget()
        self.buttons_widget.setLayout(Qt.QHBoxLayout())
        self.remove_button = Qt.QPushButton('Hide')
        self.remove_button.clicked.connect(self.toggle_hide)
        self.maximize_button = Qt.QPushButton('Maximize')
        self.maximize_button.clicked.connect(lambda: self.dock_area.hide_all_but(self))
        self.update_toggle = Qt.QCheckBox('Update')
        self.update_toggle.setChecked(True)


        self.buttons_widget.layout().addWidget(self.remove_button)
        self.buttons_widget.layout().addWidget(self.maximize_button)
        self.buttons_widget.layout().addWidget(self.update_toggle)
        self.buttons_widget.setContentsMargins(0, 0, 0, 0)
        self.buttons_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.buttons_widget.layout().setAlignment(Qt.Qt.AlignLeft)
        self.plots_widget.setContentsMargins(0, 0, 0, 0)
        self.plots_widget.layout().setContentsMargins(0, 0, 0, 0)

        self.addWidget(self.buttons_widget)
        self.dock_area.add_dock_auto_location(self)

    def is_visible(self):
        return self.parent() is not None

    def toggle_hide(self, show=None):
        if show is None:
            show = not self.is_visible()

        if self.is_visible() and not show:
            self.dock_area.remove_dock(self)
        elif show:
            self.dock_area.add_dock_auto_location(self)

    def update_params(self, **kwargs):
        self.__dict__.update(kwargs)


    def add_plot_widget(self, **kwargs):
        raise NotImplementedError

    def update_plot(self, data, attrs=None):
        self.timestamp = time.time()

    def clear_plot(self):
        raise NotImplementedError


class Rank1ItemWidget(ItemWidget):
    rank = 1
    plot_attrs = ["x0", "xscale",
                  "xlabel", "ylabel",
                  "parametric", "plot_args"]
    def __init__(self, item, **kwargs):
        ItemWidget.__init__(self, item, **kwargs)

    def add_plot_widget(self, **kwargs):
        self.line_plt = CrosshairPlotWidget(**kwargs)
        self.line_plt.plotItem.showGrid(x=True, y=True)
        self.plots_widget.layout().addWidget(self.line_plt)
        self.curve = None

    def update_plot(self, data, attrs=None):
        super(Rank1ItemWidget, self).update_plot(data, attrs)
        if attrs is None:
            attrs = {}

        x0 = attrs.get("x0", 0)
        xscale = attrs.get("xscale", 1)
        xlabel = attrs.get("xlabel", "X")
        ylabel = attrs.get("ylabel", "Y")
        parametric = attrs.get("parametric", False)
        self.line_plt.parametric = parametric
        plot_args = attrs.get("plot_args", {})


        if data is None or data.shape[0] is 0:
            self.clear_plot()
            return

        if self.update_toggle.isChecked():
            if parametric:
                if data.shape[0] == 2:
                    xdata, ydata = data
                elif data.shape[1] == 2:
                    xdata, ydata = data.T
                else:
                    raise ValueError('data claims to be parametric, but shape is ' + str(data.shape))
            else:
                ydata = data
                xdata = np.linspace(x0, x0+(xscale*(len(ydata)-1)), len(data))

        self.line_plt.plotItem.setLabels(bottom=(xlabel,), left=(ylabel,))

        if self.curve is None:
            self.curve = self.line_plt.plot(xdata, ydata, **plot_args)
        else:
            self.curve.setData(x=xdata, y=ydata, **plot_args)

    def clear_plot(self):
        if self.curve is not None:
            self.line_plt.removeItem(self.curve)
            self.curve = None


class MultiplotItemWidget(Rank1ItemWidget):
    def add_plot_widget(self, **kwargs):
        Rank1ItemWidget.add_plot_widget(self, **kwargs)
        self.curves = {}

    def update_path(self, path, data, attrs=None):
        if path not in self.curves:
            self.curves[path] = self.line_plt.plot([], pen=tuple(random_color()), name='/'.join(path))
        self.curve = self.curves[path] # This is kind of a hack isn't it. How do you OOP again?
        Rank1ItemWidget.update_plot(self, data, attrs)


class ParametricItemWidget(Rank1ItemWidget):
    def __init__(self, item, **kwargs):
        Rank1ItemWidget.__init__(self, item, **kwargs)
        self.path1, self.path2 = [i.path for i in item.sources]
        self.datas = {self.path1: [], self.path2: []}
        self.transpose_toggle = Qt.QCheckBox('Transpose')
        self.transpose_toggle.stateChanged.connect(lambda s: self.refresh_plot())
        self.buttons_widget.layout().addWidget(self.transpose_toggle)

    def update_path(self, path, data, attrs=None):
        self.datas[path] = data
        self.refresh_plot(attrs)

    def refresh_plot(self, attrs=None):
        data = np.array(zip(self.datas[self.path1],  self.datas[self.path2]))
        if attrs is None:
            attrs = {}
        attrs = attrs.copy()
        attrs['parametric'] = True
        attrs['xlabel'] = '/'.join(self.path1)
        attrs['ylabel'] = '/'.join(self.path2)
        if self.transpose_toggle.isChecked():
            data = np.transpose(np.array([data[:, 1], data[:, 0]]))
            attrs['xlabel'], attrs['ylabel'] = attrs['ylabel'], attrs['xlabel']
        self.update_plot(data, attrs)


class Rank2ItemWidget(Rank1ItemWidget):
    rank = 2
    plot_attrs = ["x0", "xscale",
                  "y0", "yscale",
                  "xlabel", "ylabel", "zlabel",
                  "parametric", "plot_args"]

    def __init__(self, item, **kwargs):
        Rank1ItemWidget.__init__(self, item, **kwargs)

        self.histogram_check = Qt.QCheckBox('Histogram')
        self.histogram_check.stateChanged.connect(self.img_view.set_histogram)
        self.autolevels_check = Qt.QCheckBox('Autolevels')
        self.autolevels_check.setChecked(True)
        self.autolevels_check.stateChanged.connect(lambda s: self.update_plot(self.cur_data, self.cur_attrs))
        self.img_widgets = [self.histogram_check, self.autolevels_check]
        self.most_recent_check = Qt.QCheckBox('Most Recent')
        self.most_recent_check.setChecked(True)
        self.line_scrubber = Qt.QSlider(Qt.Qt.Horizontal)
        self.line_scrubber.valueChanged.connect(self.set_line)
        self.line_widgets = [self.most_recent_check, self.line_scrubber]

        img_radio = Qt.QRadioButton("Image")
        img_radio.clicked.connect(self.show_img_plot)
        img_radio.setChecked(True)
        gl_radio = Qt.QRadioButton("Surface")
        gl_radio.clicked.connect(self.show_gl_plot)
        line_radio = Qt.QRadioButton("Last Line")
        line_radio.clicked.connect(self.show_line_plot)

        for widget in self.img_widgets + self.line_widgets:
            self.buttons_widget.layout().addWidget(widget)

        for widget in self.line_widgets:
            widget.hide()

        self.buttons_widget.layout().addWidget(img_radio)
        self.buttons_widget.layout().addWidget(gl_radio)
        self.buttons_widget.layout().addWidget(line_radio)

        self.cur_data = None
        self.cur_attrs = {}

    def set_line(self, value):
        print 'set line', value
        if self.cur_data is not None:
            Rank1ItemWidget.update_plot(self, self.cur_data[value, :], self.cur_attrs)

    def show_img_plot(self):
        self.img_view.show()
        self.line_plt.hide()
        if self.gl_view is not None:
            self.gl_view.hide()

        for widget in self.img_widgets:
            widget.show()
        for widget in self.line_widgets:
            widget.hide()

    def show_gl_plot(self):
        self.line_plt.hide()
        self.img_view.hide()
        for widget in self.img_widgets + self.line_widgets:
            widget.hide()

        if self.gl_view is None:
            self.gl_view = gl.GLViewWidget()
            self.gl_view.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
            self.plots_widget.layout().addWidget(self.gl_view)
            if self.img_view.image is not None:
                self.update_plot(self.img_view.image)
        self.gl_view.show()

    def show_line_plot(self):
        self.img_view.hide()
        if self.gl_view is not None:
            self.gl_view.hide()
        self.line_plt.show()

        for widget in self.line_widgets:
            widget.show()
        for widget in self.img_widgets:
            widget.hide()

    def add_plot_widget(self, **kwargs):
        Rank1ItemWidget.add_plot_widget(self)
        self.line_plt.hide()
        self.curve = None

        self.img_view = CrossSectionWidget()
        self.plots_widget.layout().addWidget(self.img_view)
        #self.addWidget(self.line_plt)

        self.gl_view = None
        self.surface = None

    def update_plot(self, data, attrs=None):
        if attrs is None:
            attrs = {}

        x0 = attrs.get("x0", 0)
        y0 = attrs.get("y0", 0)
        xscale = attrs.get("xscale", 1)
        yscale = attrs.get("yscale", 1)
        xlabel = attrs.get("xlabel", "X")
        ylabel = attrs.get("ylabel", "Y")
        zlabel = attrs.get("zlabel", "Z")
        plot_args = attrs.get("plot_args", {})

        self.cur_data = data
        self.cur_attrs = attrs

        if data is None:
            self.clear_plot()
            return

        if self.update_toggle.isChecked():

            self.line_scrubber.setMaximum(len(data)-1)

            self.img_view.setLabels(xlabel, ylabel, zlabel)
            if self.most_recent_check.isChecked():
                self.line_scrubber.setValue(len(data)-1) # This updates the line plot

            # Well, this is a hack. I'm not sure why autorange is disabled after setImage
            autorange = self.img_view.getView().vb.autoRangeEnabled()[0]
            autolevels = self.autolevels_check.isChecked()
            self.img_view.setImage(data, autoRange=autorange, autoLevels=autolevels, pos=[x0, y0], scale=[xscale, yscale])
            self.img_view.getView().vb.enableAutoRange(enable=autorange)

            if self.gl_view is not None:
                if self.surface is None or data.shape != self.surface._z.shape:
                    x1 = x0 + data.shape[0]*xscale
                    y1 = y0 + data.shape[1]*yscale
                    xs = np.arange(x0, x1, xscale)
                    ys = np.arange(y0, y1, yscale)
                    #grid = gl.GLGridItem()
                    #self.gl_view.addItem(grid)
                    if self.surface is not None:
                        self.gl_view.removeItem(self.surface)
                    self.surface = gl.GLSurfacePlotItem(x=xs, y=ys, shader='shaded')
                    self.gl_view.addItem(self.surface)
                self.surface.setData(z=data)

    def clear_plot(self):
        Rank1ItemWidget.clear_plot(self)
        #Rank1ItemWidget.update_plot(self, None)
        #self.img_view.setImage(np.array([[]]))
        self.img_view.imageItem.hide()

    def show_recent(self):
        self.img_view.hide()
        self.line_plt.show()
        self.recent_button.hide()
        self.accum_button.show()

    def show_accumulated(self):
        self.img_view.show()
        self.line_plt.hide()
        self.recent_button.show()
        self.accum_button.hide()

class Rank2ParametricWidget(ItemWidget):
    def add_plot_widget(self):
        self.gl_view = gl.GLViewWidget()
        self.gl_view.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        self.plots_widget.layout().addWidget(self.gl_view)
        self.scatter = gl.GLScatterPlotItem(color=(1,1,1,.3), size=.1, pxMode=False)
        self.gl_view.addItem(self.scatter)

    def update_plot(self, data, attrs=None):
        self.scatter.setData(pos=data)


class CrosshairPlotWidget(pg.PlotWidget):
    def __init__(self, parametric=False, *args, **kwargs):
        super(CrosshairPlotWidget, self).__init__(*args, **kwargs)
        self.scene().sigMouseClicked.connect(self.toggle_search)
        self.scene().sigMouseMoved.connect(self.handle_mouse_move)
        self.cross_section_enabled = False
        self.parametric = parametric
        self.search_mode = True
        self.label = None

    def toggle_search(self, mouse_event):
        if mouse_event.double():
            if self.cross_section_enabled:
                self.hide_cross_hair()
            else:
                self.add_cross_hair()
        elif self.cross_section_enabled:
            self.search_mode = not self.search_mode
            if self.search_mode:
                self.handle_mouse_move(mouse_event.scenePos())

    def handle_mouse_move(self, mouse_event):
        if self.cross_section_enabled and self.search_mode:
            item = self.getPlotItem()
            vb = item.getViewBox()
            view_coords = vb.mapSceneToView(mouse_event)
            view_x, view_y = view_coords.x(), view_coords.y()

            best_guesses = []
            for data_item in item.items:
                if isinstance(data_item, pg.PlotDataItem):
                    xdata, ydata = data_item.xData, data_item.yData
                    index_distance = lambda i: (xdata[i]-view_x)**2 + (ydata[i] - view_y)**2
                    if self.parametric:
                        index = min(range(len(xdata)), key=index_distance)
                    else:
                        index = min(np.searchsorted(xdata, view_x), len(xdata)-1)
                        if index and xdata[index] - view_x > view_x - xdata[index - 1]:
                            index -= 1
                    pt_x, pt_y = xdata[index], ydata[index]
                    best_guesses.append(((pt_x, pt_y), index_distance(index)))

            if not best_guesses:
                return

            (pt_x, pt_y), _ = min(best_guesses, key=lambda x: x[1])
            self.v_line.setPos(pt_x)
            self.h_line.setPos(pt_y)
            self.label.setText("x=%.2e, y=%.2e" % (pt_x, pt_y))

    def add_cross_hair(self):
        self.h_line = pg.InfiniteLine(angle=0, movable=False)
        self.v_line = pg.InfiniteLine(angle=90, movable=False)
        self.addItem(self.h_line, ignoreBounds=False)
        self.addItem(self.v_line, ignoreBounds=False)
        if self.label is None:
            self.label = pg.LabelItem(justify="right")
            self.getPlotItem().layout.addItem(self.label, 4, 1)
        self.x_cross_index = 0
        self.y_cross_index = 0
        self.cross_section_enabled = True

    def hide_cross_hair(self):
        self.removeItem(self.h_line)
        self.removeItem(self.v_line)
        self.cross_section_enabled = False

class CrossSectionWidget(pg.ImageView):
    def __init__(self, trace_size=80, **kwargs):
        view = pg.PlotItem(labels=kwargs.pop('labels', None))
        pg.ImageView.__init__(self, view=view, **kwargs)
        view.setAspectLocked(lock=False)
        self.cross_section_enabled = False
        self.search_mode = False
        self.signals_connected = False
        self.set_histogram(False)
        self.ui.histogram.gradient.loadPreset('thermal')
        try:
            self.connect_signal()
        except RuntimeError:
            warnings.warn('Scene not set up, cross section signals not connected')


        self.y_cross_index = 0
        self.h_cross_dock = pyqtgraph.dockarea.Dock('x trace')
        self.h_cross_section_widget = CrosshairPlotWidget()
        self.h_cross_section_widget.add_cross_hair()
        self.h_cross_section_widget.search_mode = False
        self.h_cross_section_widget_data = self.h_cross_section_widget.plot([0,0])
        self.h_cross_dock.addWidget(self.h_cross_section_widget)

        self.x_cross_index = 0
        self.v_cross_dock = pyqtgraph.dockarea.Dock('y trace')
        self.v_cross_section_widget = CrosshairPlotWidget()
        self.v_cross_section_widget.add_cross_hair()
        self.v_cross_section_widget.search_mode = False
        self.v_cross_section_widget_data = self.v_cross_section_widget.plot([0,0])
        self.v_cross_dock.addWidget(self.v_cross_section_widget)

    def setLabels(self, xlabel="X", ylabel="Y", zlabel="Z"):
        self.view.setLabels(bottom=(xlabel,), left=(ylabel,))
        self.h_cross_section_widget.plotItem.setLabels(bottom=xlabel, left=zlabel)
        self.v_cross_section_widget.setLabels(bottom=ylabel, left=zlabel)
        #self.setLabels(xlabel, ylabel)
        self.ui.histogram.item.axis.setLabel(text=zlabel)

    def setImage(self, *args, **kwargs):
        if 'pos' in kwargs:
            self._x0, self._y0 = kwargs['pos']
        if 'scale' in kwargs:
            self._xscale, self._yscale = kwargs['scale']

        pg.ImageView.setImage(self, *args, **kwargs)
        self.update_cross_section()

    def toggle_cross_section(self):
        if self.cross_section_enabled:
            self.hide_cross_section()
        else:
            self.add_cross_section()

    def set_histogram(self, visible):
        self.ui.histogram.setVisible(visible)
        self.ui.roiBtn.setVisible(visible)
        self.ui.normBtn.setVisible(visible)

    def add_cross_section(self):
        if self.imageItem.image is not None:
            (min_x, max_x), (min_y, max_y) = self.imageItem.getViewBox().viewRange()
            mid_x, mid_y = (max_x + min_x)/2., (max_y + min_y)/2.
        else:
            mid_x, mid_y = 0, 0
        self.h_line = pg.InfiniteLine(pos=mid_y, angle=0, movable=False)
        self.v_line = pg.InfiniteLine(pos=mid_x, angle=90, movable=False)
        self.view.addItem(self.h_line, ignoreBounds=False)
        self.view.addItem(self.v_line, ignoreBounds=False)
        self.x_cross_index = 0
        self.y_cross_index = 0
        self.cross_section_enabled = True
        self.label = pg.LabelItem(justify="right")
        #self.cs_layout.addItem(self.label, 2, 1) #TODO: Find a way of displaying this label
        self.search_mode = True

        ItemWidget.dock_area.addDock(self.h_cross_dock)
        ItemWidget.dock_area.addDock(self.v_cross_dock, position='right', relativeTo=self.h_cross_dock)


    def hide_cross_section(self):
        self.view.removeItem(self.h_line)
        self.view.removeItem(self.v_line)
        self.cross_section_enabled = False

        ItemWidget.dock_area.remove_dock(self.h_cross_dock)
        ItemWidget.dock_area.remove_dock(self.v_cross_dock)

    def connect_signal(self):
        """This can only be run after the item has been embedded in a scene"""
        if self.signals_connected:
            warnings.warn("")
        if self.imageItem.scene() is None:
            raise RuntimeError('Signal can only be connected after it has been embedded in a scene.')
        self.imageItem.scene().sigMouseClicked.connect(self.toggle_search)
        self.imageItem.scene().sigMouseMoved.connect(self.handle_mouse_move)
        self.timeLine.sigPositionChanged.connect(self.update_cross_section)
        self.signals_connected = True

    def toggle_search(self, mouse_event):
        if mouse_event.double():
            self.toggle_cross_section()
        elif self.cross_section_enabled:
            self.search_mode = not self.search_mode
            if self.search_mode:
                self.handle_mouse_move(mouse_event.scenePos())

    def handle_mouse_move(self, mouse_event):
        if self.cross_section_enabled and self.search_mode:
            view_coords = self.imageItem.getViewBox().mapSceneToView(mouse_event)
            view_x, view_y = view_coords.x(), view_coords.y()
            item_coords = self.imageItem.mapFromScene(mouse_event)
            item_x, item_y = item_coords.x(), item_coords.y()
            max_x, max_y = self.imageItem.image.shape
            if item_x < 0 or item_x > max_x or item_y < 0 or item_y > max_y:
                return
            self.v_line.setPos(view_x)
            self.h_line.setPos(view_y)
            #(min_view_x, max_view_x), (min_view_y, max_view_y) = self.imageItem.getViewBox().viewRange()
            self.x_cross_index = max(min(int(item_x), max_x-1), 0)
            self.y_cross_index = max(min(int(item_y), max_y-1), 0)
            self.update_cross_section()
            self.label.setText("x=%.2e, y=%.2e" % (view_x, view_y))

    def update_cross_section(self):
        nx, ny = self.imageItem.image.shape
        x0, y0, xscale, yscale = self._x0, self._y0, self._xscale, self._yscale
        xdata = np.linspace(x0, x0+(xscale*(nx-1)), nx)
        ydata = np.linspace(y0, y0+(yscale*(ny-1)), ny)
        zval = self.imageItem.image[self.x_cross_index, self.y_cross_index]
        self.h_cross_section_widget_data.setData(xdata, self.imageItem.image[:, self.y_cross_index])
        self.h_cross_section_widget.v_line.setPos(xdata[self.x_cross_index])
        self.h_cross_section_widget.h_line.setPos(zval)
        self.v_cross_section_widget_data.setData(ydata, self.imageItem.image[self.x_cross_index, :])
        self.v_cross_section_widget.v_line.setPos(ydata[self.y_cross_index])
        self.v_cross_section_widget.h_line.setPos(zval)

def random_color(base=50):
    'A whitish random color. Adjust whiteness up by increasing base'
    return np.random.randint(base, 255, 3)