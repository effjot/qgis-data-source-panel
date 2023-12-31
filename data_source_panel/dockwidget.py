# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DataSourceDockWidget
                                 A QGIS plugin
 Panel with overview of layer data sources
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2023-12-23
        git sha              : $Format:%H$
        copyright            : (C) 2023 by Florian Jenn
        email                : devel@effjot.net
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsIconUtils,
    QgsMessageLog,
    QgsProject,
    QgsProviderRegistry
)
from qgis.PyQt import QtCore, QtGui, QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal, Qt
from qgis.PyQt.QtWidgets import QAction

from .layer_sources import LayerSources, nice_provider_name, locations_common_part


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'dockwidget.ui'))


class SourcesTableModel(QtCore.QAbstractTableModel):
    def __init__(self, data: LayerSources):
        super().__init__()
        self._data = data
        self.get_icons()
        self._header = ['Layer', 'Provider', 'Storage Location']

    def get_icons(self):
        self._icons = [QgsIconUtils.iconForLayer(
                           QgsProject.instance().mapLayer(src.layerid))
                       for src in self._data]

    def data(self, index, role):
        if role == Qt.DisplayRole:
            src = self._data.by_index(index.row())
            item = src.by_index(index.column() + 1)  # skip layerid field
            if index.column() == 1:
                return nice_provider_name(item)
            return str(item)
        if role == Qt.DecorationRole:
            if index.column() == 0:
                return self._icons[index.row()]

    def rowCount(self, index):
        return self._data.num_layers()

    def columnCount(self, index):
        return self._data.num_fields() - 1  # skip layerid field

    def headerData(self, index, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._header[index]

    def update(self):
        # QgsMessageLog.logMessage(f'update() before: {self.rowCount(0)=}', 'DSP', Qgis.Info)
        self.get_icons()
        # QgsMessageLog.logMessage(f'  after: {self.rowCount(0)=}', 'DSP', Qgis.Info)
        self.layoutChanged.emit()
        # QgsMessageLog.logMessage('  signal emitted', 'DSP', Qgis.Info)


class TreeItem():
    """Item in simple tree data structure from https://doc.qt.io/qtforpython-5/overviews/qtwidgets-itemviews-simpletreemodel-example.html#simple-tree-model-example"""
    def __init__(self, data, data_type=None, parent=None):
        self.parent_item = parent
        self.children = []
        self._data = data
        self._icon = None
        if data_type == 'provider':
            self._icon = QgsProviderRegistry.instance().providerMetadata(
                data).icon()
            self._data = nice_provider_name(data)
        elif data_type == 'location':
            self._icon = None
        elif data_type == 'source':
            self._data = data.name
            self._icon = QgsIconUtils.iconForLayer(
                QgsProject.instance().mapLayer(data.layerid))
        self.data_type = data_type

    def append_child(self, item):
        self.children.append(item)

    def insert_in_tree(self, item, where=None):
        if not where:
            item.parent_item = self
            self.append_child(item)
            return
        insert_at = where[0]
        if insert_at not in [c.data() for c in self.children]:
            new_child = TreeItem(insert_at, item.data_type, parent=self)
            self.append_child(new_child)
        row = [c.data() for c in self.children].index(insert_at)
        self.child(row).insert_in_tree(item, where[1:])

    def remove_children(self):
        if not self.children:
            return None
        for child in self.children:
            child.remove_children()
        self.children = []

    def child(self, row):
        return self.children[row]

    def child_count(self):
        return len(self.children)

    def column_count(self):  # at the moment no columns used
        return 1

    def data(self, column=None):  # at the moment no columns used
        return self._data

    def parent(self):
        return self.parent_item

    def row(self):
        """Row number of item for non-toplevel items; 0 for toplevel items"""
        if self.parent_item:
            return self.parent_item.children.index(self)
        return 0

    def icon(self):
        return self._icon


class SourcesTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, data: LayerSources):
        super().__init__()
        self._data = data  # original / “flat” data
        self.root_item = TreeItem('Data Sources', parent=None)
        self.setup_model_tree(data)

    def clear(self):
        self.root_item.remove_children()

    def data(self, index, role):
        if not index.isValid():
            return None
        item = index.internalPointer()
        if role == Qt.DisplayRole:
            return item.data()  # at the moment no columns used
        if role == Qt.DecorationRole:
            return item.icon()
        return None

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QtCore.QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()
        child_item = index.internalPointer()
        parent_item = child_item.parent()
        if parent_item == self.root_item:
            return QtCore.QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()
        return parent_item.child_count()

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().column_count()
        else:
            return self.root_item.column_count()

    def setup_model_tree(self, data):
        self.clear()
        providers = data.providers()
        for prov in providers:
            prov_item = TreeItem(prov, 'provider', self.root_item)
            self.root_item.append_child(prov_item)
            prov_sources = data.by_provider(prov)
            locations = prov_sources.locations()
            loc_common = locations_common_part(locations)
            for loc in locations:
                if loc.is_empty():
                    loc_item = prov_item
                elif loc.is_deep():
                    loc_item = TreeItem(str(loc.hierarchical[-1]),
                                        'location', parent=None)
                    if loc_common and prov in ('ogr', 'gdal'):
                        common_part = str(
                            Path().joinpath(*loc.hierarchical[:loc_common]))
                        remainder = loc.hierarchical[loc_common:-1]
                        where = (common_part,) + remainder
                    else:
                        where = loc.hierarchical[:-1]
                    prov_item.insert_in_tree(loc_item, where)
                else:
                    loc_item = TreeItem(str(loc), 'location', prov_item)
                    prov_item.append_child(loc_item)
                sources = prov_sources.by_location(loc)
                for src in sources:
                    src_item = TreeItem(src, 'source', loc_item)
                    loc_item.append_child(src_item)

    def update(self):
        # QgsMessageLog.logMessage(f'update() before: {self._data.num_layers()=}', 'DSP', Qgis.Info)
        self.beginResetModel()
        self.setup_model_tree(self._data)
        # QgsMessageLog.logMessage(f'  after: {self._data.num_layers()=}', 'DSP', Qgis.Info)
        self.endResetModel()


class DataSourceDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    closingPlugin = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super().__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://doc.qt.io/qt-5/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        # Layout like QGIS/src/gui/qgsbrowserwidget.cpp and QGIS/src/ui/qgsbrowserwidgetbase.u
        self.vertical_layout.setContentsMargins(0, 0, 0, 0)
        self.vertical_layout.setSpacing(0)

        # Toolbar
        self.act_tableview = QAction(
            QgsApplication.getThemeIcon("/mActionOpenTable.svg"),
            '&Table View', self)
        self.act_treeview = QAction(
            QgsApplication.getThemeIcon("/mIconTreeView.svg"),
            'T&ree View', self)
        self.act_tableview.setCheckable(True)
        self.act_treeview.setCheckable(True)
        self.act_tableview.setChecked(True)
        self.act_tableview.triggered.connect(self.show_table)
        self.act_treeview.triggered.connect(self.show_tree)
        self.toolbar.addAction(self.act_tableview)
        self.toolbar.addAction(self.act_treeview)

        self.sources = LayerSources()
        self.table_model = SourcesTableModel(self.sources)
        self.proxy_model = QtCore.QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.v_sources_table.setSortingEnabled(True)
        self.v_sources_table.setModel(self.proxy_model)
        self.tree_model = SourcesTreeModel(self.sources)
        self.v_sources_tree.setHeaderHidden(True)
        self.v_sources_tree.setModel(self.tree_model)

        self.proj = QgsProject.instance()
        self.proj.layersAdded.connect(self.update_models)
        self.proj.layersRemoved.connect(self.update_models)

    def show_table(self):
        self.act_tableview.setChecked(True)
        self.act_treeview.setChecked(False)
        self.stk_sourcesview.setCurrentIndex(0)

    def show_tree(self):
        self.act_tableview.setChecked(False)
        self.act_treeview.setChecked(True)
        self.stk_sourcesview.setCurrentIndex(1)

    def update_models(self):
        self.sources.update()
        self.table_model.update()
        self.tree_model.update()

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()
