
import os
from .pipeline import env_embedded_path
from .. import plugins


class HoudiniBaseLoader(plugins.PackageLoader):

    def file_path(self, representation):
        file_name = representation["data"]["entryFileName"]
        entry_path = os.path.join(self.package_path, file_name)

        if not os.path.isfile(entry_path):
            raise IOError("File Not Found: {!r}".format(entry_path))

        return env_embedded_path(entry_path)


class HoudiniSelectInvalidInstanceAction(plugins.SelectInvalidInstanceAction):

    def select(self, invalid):
        self.deselect()
        for node in invalid:
            node.setSelected(True)

    def deselect(self):
        import hou
        hou.clearAllSelected()


class HoudiniSelectInvalidContextAction(plugins.SelectInvalidContextAction):
    """ Select invalid nodes in context"""

    def select(self, invalid):
        self.deselect()
        for node in invalid:
            node.setSelected(True)

    def deselect(self):
        import hou
        hou.clearAllSelected()
