import pyblish.api
from reveries import plugins


class SelectInvalidBindPose(plugins.MayaSelectInvalidInstanceAction):

    label = r'Select Invalid BindPose'
    symptom = 'bindpose'
    on = 'processed'


class RepairInvalidBindPose(plugins.RepairInstanceAction):

    label = r'Remove Invalid BindPose'
    symptom = 'bindpose'
    on = 'processed'


class ValidateRigBindPose(pyblish.api.InstancePlugin):
    """Export rig primitive usd file
    """

    order = pyblish.api.ValidatorOrder + 0.134
    hosts = ['maya']
    label = r'Validate Rig BindPose'

    families = [
        r'reveries.rig.skeleton'
    ]

    actions = [
        pyblish.api.Category('Select'),
        SelectInvalidBindPose,
        pyblish.api.Category('Remove'),
        RepairInvalidBindPose,
    ]

    def process(self, instance):
        invalid = self.get_invalid_bindpose(instance)

        if invalid:
            _msg = r'Invalid bindpose: {}'.format(invalid)

            self.log.info(_msg)
            self.log.error(
                r'Has invalid bindpose history, please remove it.<br>'
                r'{}'.format(_msg))

            raise Exception(
                r'%s BindPose Validation Failed.' % instance)

    @classmethod
    def get_invalid_bindpose(cls, instance):
        import maya.cmds as cmds

        mesh_skins = []
        geometries = set()

        # === Get skinClusters === #
        for out_set in instance.data['outSets']:
            nodes = cmds.sets(out_set, query=True)
            if not nodes:
                continue
            geometries.update(nodes)
        geometries = list(geometries)

        for _item in geometries:
            shapes = cmds.listRelatives(_item, shapes=True, fullPath=True)
            for _shape in shapes:
                skins = cmds.listConnections(_shape, type='skinCluster')
                if skins:
                    mesh_skins += skins

        mesh_skins = list(set(mesh_skins))

        # === Get Invalid BindPose === #
        cmds.select(geometries, r=True)
        bindpose = cmds.dagPose(q=True, bindPose=True) or []
        cmds.select(cl=True)

        invalid_bindpose = []
        for _item in bindpose:
            skins = cmds.listConnections(_item, type='skinCluster')

            if not skins:
                invalid_bindpose.append(_item)
                continue

            for skin in skins:
                if skin not in mesh_skins:
                    invalid_bindpose.append(_item)

        invalid_bindpose = list(set(invalid_bindpose))

        return invalid_bindpose

    @classmethod
    def fix_invalid_bindpose(cls, instance):
        import maya.cmds as cmds

        invalid = cls.get_invalid_bindpose(instance)
        if invalid:
            cmds.delete(invalid)
