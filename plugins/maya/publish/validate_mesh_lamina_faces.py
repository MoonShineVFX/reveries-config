
import pyblish.api
from reveries import plugins


class ValidateMeshLaminaFaces(pyblish.api.InstancePlugin):
    """Validate meshes don't have lamina faces.

    Lamina faces share all of their edges.

    """

    order = pyblish.api.ValidatorOrder + 0.3
    label = "Mesh Lamina Faces"
    hosts = ["maya"]
    families = [
        "reveries.model",
    ]
    actions = [
        pyblish.api.Category("Select"),
        plugins.MayaSelectInvalidInstanceAction,
    ]

    optional = True

    @classmethod
    def get_invalid(cls, instance):
        from maya import cmds

        meshes = cmds.ls(instance, type="mesh", long=True, noIntermediate=True)
        invalid = [mesh for mesh in meshes if
                   cmds.polyInfo(mesh, laminaFaces=True)]

        return invalid

    def process(self, instance):
        """Process all the nodes in the instance 'objectSet'"""

        invalid = self.get_invalid(instance)

        if invalid:
            raise ValueError("Meshes found with lamina faces: "
                             "{0}".format(invalid))
