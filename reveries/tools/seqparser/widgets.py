
import os
import re
from avalon.vendor.Qt import QtWidgets, QtCore, QtGui
from avalon.vendor import qtawesome
from avalon.tools import models
from . import delegates


ExtendedSelection = QtWidgets.QAbstractItemView.ExtendedSelection


class SequenceWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(SequenceWidget, self).__init__(parent=parent)

        data = {
            "model": SequenceModel(),
            "proxy": QtCore.QSortFilterProxyModel(),
            "view": QtWidgets.QTreeView(),
            "fpatternDel": None,
            "nameDel": None,
        }

        data["proxy"].setSourceModel(data["model"])
        data["view"].setModel(data["proxy"])
        data["fpatternDel"] = delegates.LineHTMLDelegate(data["view"])
        data["nameDel"] = delegates.NameEditDelegate()

        fpattern_delegate = data["fpatternDel"]
        column = data["model"].Columns.index("fpattern")
        data["view"].setItemDelegateForColumn(column, fpattern_delegate)

        name_delegate = data["nameDel"]
        column = data["model"].Columns.index("name")
        data["view"].setItemDelegateForColumn(column, name_delegate)

        data["proxy"].setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)
        data["view"].setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        data["view"].setSelectionMode(ExtendedSelection)
        data["view"].setSortingEnabled(True)
        data["view"].sortByColumn(0, QtCore.Qt.AscendingOrder)
        data["view"].setAlternatingRowColors(True)
        data["view"].setAllColumnsShowFocus(True)
        data["view"].setIndentation(6)
        data["view"].setStyleSheet("""
            QTreeView::item{
                padding: 8px 1px;
                border: 0px;
            }
        """)

        data["view"].setColumnWidth(0, 360)  # fpattern
        data["view"].setColumnWidth(1, 100)  # name
        data["view"].setColumnWidth(2, 80)  # frames

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(data["view"])
        layout.setContentsMargins(0, 0, 0, 0)

        data["view"].customContextMenuRequested.connect(self.on_context_menu)

        self.data = data

    def on_context_menu(self, point):
        view = self.data["view"]

        point_index = view.indexAt(point)
        if not point_index.isValid():
            return

        menu = QtWidgets.QMenu(view)
        icon_dir = qtawesome.icon("fa.folder-open", color="gray")

        dir_act = QtWidgets.QAction(menu, icon=icon_dir, text="Open Dir")
        dir_act.triggered.connect(self.action_open_dir)

        menu.addAction(dir_act)

        globalpos = view.mapToGlobal(point)
        menu.exec_(globalpos)

    def action_open_dir(self):
        view = self.data["view"]
        proxy = view.model()
        to_open = set()

        for index in view.selectionModel().selectedRows(0):
            index = proxy.mapToSource(index)
            item = index.internalPointer()
            dir_path = os.path.dirname(item["root"] + "/" + item["fpattern"])
            to_open.add(dir_path)

        for path in to_open:
            os.startfile(path)

    def set_stereo(self, value):
        self.data["model"].set_stereo(value)
        self.data["view"].viewport().update()

    def search_channel_name(self, head, tail):
        self.data["model"].search_channel_name(head, tail)

    def add_sequences(self, sequences):
        model = self.data["model"]
        model.clear()
        for sequence in sequences:
            model.add_sequence(sequence)

    def collected(self, with_keys=None):
        model = self.data["model"]
        with_keys = with_keys or list()
        sequences = dict()
        root_index = QtCore.QModelIndex()
        for row in range(model.rowCount(root_index)):
            index = model.index(row, column=0, parent=root_index)
            item = index.internalPointer()
            if all(item.get(k) for k in with_keys):
                if model._stereo:
                    item["fpattern"] = item["stereoPattern"]

                if item["name"] not in sequences:
                    sequences[item["name"]] = item

        return sequences


class SequenceModel(models.TreeModel):

    Columns = [
        "fpattern",
        "name",
        "frames",
    ]

    HTMLTextRole = QtCore.Qt.UserRole + 10

    def __init__(self, parent=None):
        super(SequenceModel, self).__init__(parent)
        self._stereo = False
        self._stereo_icons = {
            "Left": qtawesome.icon("fa.bullseye", color="#FC3731"),
            "Right": qtawesome.icon("fa.bullseye", color="#53D8DF"),
            None: qtawesome.icon("fa.circle", color="#656565"),
        }

    def set_stereo(self, value):
        self._stereo = value

    def search_channel_name(self, head, tail):
        if not head and not tail:
            return

        pattern = re.compile(".*?%s([0-9a-zA-Z_]*)%s.*" % (head, tail))

        root_index = QtCore.QModelIndex()
        last = self.rowCount(root_index)
        column = self.Columns.index("name")

        for row in range(last):
            index = self.index(row, column=column, parent=root_index)
            item = index.internalPointer()
            result = pattern.search(item["fpattern"])
            if result and result.groups():
                name = pattern.search(item["fpattern"]).group(1)

                # Arnold light groups
                if "_lgroups" in item.get("head", ""):
                    name += "_lgroups"

                self.setData(index, name)

    def add_sequence(self, sequence):
        root_index = QtCore.QModelIndex()
        last = self.rowCount(root_index)

        self.beginInsertRows(root_index, last, last)

        item = models.Item()
        item.update(sequence)

        # Must have
        item["root"] = sequence["root"]
        item["fpattern"] = sequence["fpattern"]
        item["paddingStr"] = sequence["paddingStr"]
        item["frames"] = "%d-%d" % (sequence["start"], sequence["end"])
        # Optional
        item["name"] = sequence.get("name", "")

        # Collect stereo data even user did not specify
        def take_side(fpattern):
            if "Left" in fpattern:
                return "Left", fpattern.replace("Left", "{stereo}")
            elif "Right" in fpattern:
                return "Right", fpattern.replace("Right", "{stereo}")
            else:
                return None, fpattern

        this_side, this_side_p = take_side(item["fpattern"])

        if this_side is not None:
            for row in reversed(range(last)):
                index = self.index(row, column=0, parent=root_index)
                other = index.internalPointer()
                if other.get("stereoSide"):
                    # Paired
                    continue

                other_side, other_side_p = take_side(other["fpattern"])
                if other_side is None:
                    continue

                if this_side != other_side and this_side_p == other_side_p:
                    item["stereoSide"] = this_side
                    item["stereoPattern"] = this_side_p
                    other["stereoSide"] = other_side
                    other["stereoPattern"] = other_side_p
                    break

        html_fpattern = "{dir}{head}{padding}{tail}"

        dir, fname = os.path.split(item["fpattern"])
        head, tail = fname.split(item["paddingStr"], 1)
        padding = item["paddingStr"]

        dir = "<span style=\"color:#666666\">%s/ </span>" % dir
        head = "<span style=\"color:#EEEEEE\">%s</span>" % head
        padding = "<span style=\"color:#666666\">%s</span>" % padding
        tail = "<span style=\"color:#999999\">%s</span>" % tail

        item["fpatternHTML"] = html_fpattern.format(dir=dir,
                                                    head=head,
                                                    padding=padding,
                                                    tail=tail)
        self.add_child(item)

        self.endInsertRows()

    def data(self, index, role):
        if not index.isValid():
            return

        if role == QtCore.Qt.FontRole:
            font = QtGui.QFont("Monospace")
            font.setStyleHint(QtGui.QFont.TypeWriter)
            return font

        if role == self.HTMLTextRole:
            node = index.internalPointer()
            return node["fpatternHTML"]

        if role == QtCore.Qt.DecorationRole:
            if index.column() == self.Columns.index("name"):
                if self._stereo:
                    node = index.internalPointer()
                    side = node.get("stereoSide")
                    return self._stereo_icons[side]

        return super(SequenceModel, self).data(index, role)

    def flags(self, index):
        flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

        # Make the version column editable
        if index.column() in [self.Columns.index("fpattern"),
                              self.Columns.index("name"), ]:
            flags |= QtCore.Qt.ItemIsEditable

        return flags
