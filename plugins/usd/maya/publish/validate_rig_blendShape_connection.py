import pyblish.api
from reveries import plugins


class SelectBlendShape(plugins.MayaSelectInvalidInstanceAction):

    label = "Select Invalid BlendShape"
    symptom = "blendShape"
    on = "processed"


class SelectMesh(plugins.MayaSelectInvalidInstanceAction):

    label = "Select Mesh"
    symptom = "mesh"
    on = "processed"


class ValidateRigBlendShapeConnection(pyblish.api.InstancePlugin):
    """Check blendShape's attribute "envelope" wasn't connected.
    If get error on this validation, please check your connection on blendShape,
    the connection should be on "weight" attribute not "envelope"
    """

    label = "Validate BlendShape Connection"
    order = pyblish.api.ValidatorOrder + 0.133
    hosts = ["maya"]

    families = ["reveries.rig.skeleton"]

    actions = [
        pyblish.api.Category("選取"),
        SelectBlendShape,
        SelectMesh,
    ]

    def process(self, instance):

        invalid = self.get_invalid_blendShape(instance)
        if invalid:
            self.log.error(
                "Few blendShape's \"envelope\" attribute was connected.")

            raise Exception(
                "%s BlendShape Connection Validation Failed." % instance)

    @classmethod
    def get_invalid_blendShape(cls, instance):
        import maya.cmds as cmds

        invalid = []

        blend_shapes = cmds.ls(type="blendShape")
        for _blendshape in blend_shapes:
            if cmds.connectionInfo(
                    "{}.envelope".format(_blendshape), isDestination=True):
                invalid.append(_blendshape)

        # cls.log.info("invalid blendShape: {}".format(invalid))
        return invalid

    @classmethod
    def get_invalid_mesh(cls, instance):
        import maya.cmds as cmds

        invalid = []

        for _blendshape in cls.get_invalid_blendShape(instance):
            meshs = cmds.listConnections(
                _blendshape, d=True, s=False, type="mesh")
            if meshs:
                invalid += meshs

        return invalid
