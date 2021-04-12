
import pyblish.api
from reveries import plugins


class SelectInvalid(plugins.MayaSelectInvalidInstanceAction):

    label = "Select Invalid"


class ExportVertexColors(plugins.RepairInstanceAction):

    label = "Set Export Vertex Colors"


class ValidateVertexColorExport(pyblish.api.InstancePlugin):
    order = pyblish.api.ValidatorOrder + 0.45
    hosts = ["maya"]
    label = "Vertex Color"
    families = [
        "reveries.look",
    ]

    actions = [
        pyblish.api.Category("Select"),
        SelectInvalid,
        pyblish.api.Category("Fix It"),
        ExportVertexColors,
    ]

    @classmethod
    def get_invalid(cls, instance):
        from maya import cmds
        from reveries.maya import lib

        invalid = list()

        tension_requires = instance.data.get("requireTensionMap")
        if tension_requires:
            meshes = cmds.listRelatives(
                tension_requires,
                shapes=True,
                noIntermediate=True,
                path=True,
            ) or []

            for mesh in meshes:
                if lib.hasAttrExact(mesh, "aiExportColors"):
                    if not cmds.getAttr(mesh + ".aiExportColors"):
                        invalid.append(mesh)

        return invalid

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            self.log.error(
                '{!r} has mesh requires to enable "Export Vertex Colors":'
                ''.format(instance.name)
            )
            for node in invalid:
                self.log.error(node)

            raise ValueError("%s <Vertex Color> Failed." % instance.name)

    @classmethod
    def fix_invalid(cls, instance):
        from maya import cmds
        from reveries.maya import lib

        for mesh in cls.get_invalid(instance):
            if lib.hasAttrExact(mesh, "aiExportColors"):
                cmds.setAttr(mesh + ".aiExportColors", True)
