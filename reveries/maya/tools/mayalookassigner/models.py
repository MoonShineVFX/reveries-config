from collections import defaultdict
from avalon.tools import models

from avalon.vendor.Qt import QtCore
from avalon.vendor import qtawesome
from avalon.style import colors


UNDEFINED_SUBSET = "(Undefined)"


class AssetModel(models.TreeModel):

    Columns = ["label", "subset"]

    def add_items(self, items):
        """
        Add items to model with needed data
        Args:
            items(list): collection of item data

        Returns:
            None
        """

        self.beginResetModel()

        # Add the items sorted by label
        sorter = (lambda x: x["label"])

        for item in sorted(items, key=sorter):

            asset_item = models.Item()
            asset_item.update(item)
            asset_item["icon"] = "folder"

            # Add namespace children
            namespaces = item["namespaces"]
            for namespace in sorted(namespaces):
                child = models.Item()
                child.update(item)
                child.update({
                    "label": (namespace if namespace != ":"
                              else "(no namespace)"),
                    "subset": item["subsets"][namespace],
                    "namespace": namespace,
                    "looks": item["looks"],
                    "nodes": item["nodes"][namespace] or None,
                    "icon": "file-o"
                })
                asset_item.add_child(child)

            self.add_child(asset_item)

        self.endResetModel()

    def data(self, index, role):

        if not index.isValid():
            return

        if role == self.ItemRole:
            node = index.internalPointer()
            return node

        # Add icon
        if role == QtCore.Qt.DecorationRole:
            if index.column() == 0:
                node = index.internalPointer()
                icon = node.get("icon")
                if icon:
                    return qtawesome.icon("fa.{0}".format(icon),
                                          color=colors.default)
            if index.column() == 1:
                node = index.internalPointer()
                if "subset" in node:
                    if node["subset"] == UNDEFINED_SUBSET:
                        return qtawesome.icon("fa.question-circle",
                                              color="#DA4945")
                    else:
                        return qtawesome.icon("fa.bookmark", color="gray")

        return super(AssetModel, self).data(index, role)


class LookModel(models.TreeModel):
    """Model displaying a list of looks and matches for assets"""

    Columns = ["label", "version", "match"]

    def add_items(self, items):
        """Add items to model with needed data

        An item exists of:
            {
                "subset": 'name of subset',
                "asset": asset_document
            }

        Args:
            items(list): collection of item data

        Returns:
            None
        """

        self.beginResetModel()

        # Collect the assets per look name (from the items of the AssetModel)
        look_subsets = defaultdict(list)
        for asset_item in items:
            asset = asset_item["asset"]
            for look in asset_item["looks"]:
                key = (look["name"], look["version"])
                look_subsets[key].append(asset)

        for (subset, version), assets in sorted(look_subsets.iteritems()):

            # Define nice label without "look" prefix for readability
            label = subset if not subset.startswith("look") else subset[4:]

            item_node = models.Item()
            item_node["label"] = label
            item_node["subset"] = subset
            item_node["version"] = str(version)

            # Amount of matching assets for this look
            item_node["match"] = len(assets)

            # Store the assets that have this subset available
            item_node["assets"] = assets

            self.add_child(item_node)

        self.endResetModel()


class LoadedLookModel(models.TreeModel):
    """Model displaying a list of loaded looks and matches for assets"""

    Columns = ["label", "No.", "match"]

    def add_items(self, items):

        self.beginResetModel()

        # Collect the assets per look name (from the items of the AssetModel)
        look_subsets = defaultdict(list)
        for asset_item in items:
            asset = asset_item["asset"]
            for look in asset_item["loadedLooks"]:
                key = (look["name"], look["No."])
                look_subsets[key].append(asset)

        for (subset, num), assets in sorted(look_subsets.iteritems()):

            # Define nice label without "look" prefix for readability
            label = subset if not subset.startswith("look") else subset[4:]

            item_node = models.Item()
            item_node["label"] = label
            item_node["subset"] = subset
            item_node["No."] = num

            # Amount of matching assets for this look
            item_node["match"] = len(assets)

            # Store the assets that have this subset available
            item_node["assets"] = assets

            self.add_child(item_node)

        self.endResetModel()
