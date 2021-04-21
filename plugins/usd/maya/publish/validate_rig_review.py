import pyblish.api


class ValidateRigUSDReview(pyblish.api.InstancePlugin):
    """Export rig primitive usd file
    """

    order = pyblish.api.ValidatorOrder + 0.135
    hosts = ['maya']
    label = r'Validate USD Review'
    families = [
        r'reveries.rig.review'
    ]

    def process(self, instance):
        import maya.cmds as cmds
        import pymel.core as pm

        # Check control 'Main' exists
        if 'MainShape' not in cmds.ls(type='nurbsCurve'):
            _msg = 'Control Main not exists.'
            self.log.error(_msg)
            raise Exception(
                r'%s Rig Review Validation Failed.' % instance)

        # Check camera exists
        cam_name = 'usd_review_cam'

        if not cmds.objExists(cam_name):
            _cam_name, _ = cmds.camera(name=cam_name)
            cmds.rename(_cam_name, cam_name)
            cmds.group(cam_name, n='{}_grp'.format(cam_name))
            camShape_name = cmds.listRelatives(cam_name, shapes=True)[0]
        else:
            camShape_name = cmds.listRelatives(cam_name, shapes=True)[0]

        cmds.select('|ROOT|Group|Geometry', r=True)

        cmds.setAttr('{}.displayFilmGate'.format(camShape_name), 1)
        cmds.setAttr('{}.displayGateMask'.format(camShape_name), 1)
        cmds.setAttr('{}.overscan'.format(camShape_name), 1)
        pm.viewFit(camShape_name, all=False)  # , f=.7

        cmds.setAttr('Main.rotateY', 90)
        pm.viewFit(camShape_name, all=False)

        instance.data["usdview_cam"] = cam_name

        cmds.select(cl=True)
        cmds.setAttr("Main.rotateY", 0)
