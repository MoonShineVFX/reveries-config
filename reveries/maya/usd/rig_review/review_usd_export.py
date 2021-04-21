import os

USD_VERSION = '21.02'

RIG_REVIEWPRIM = 'rig_review_prim.usda'
REVIEW_CAMPRIM = 'review_cam_prim.usda'

RIG_NS = 'review_test'
MAIN_CTRL = 'Main'
RENDER_RANGE = [100, 120]


class ExportReviewUSD(object):
    def __init__(self, instance_data, stage_dir):
        self.rig_subset_id = None

        self.instance_data = instance_data
        self.stage_dir = stage_dir

        self.cam_name = instance_data.get('usdview_cam', 'usd_review_cam')  # 'usd_review_camShape'
        self._check_exists(self.cam_name)

        self.cam_usd_path = os.path.join(self.stage_dir, REVIEW_CAMPRIM)
        self.review_usd_file = os.path.join(self.stage_dir, RIG_REVIEWPRIM)

        self.do_export()

    def _check_exists(self, obj_name):
        import maya.cmds as cmds

        if not cmds.objExists(obj_name):
            raise RuntimeError(
                "Object {} not exists in your scene.".format(obj_name))

    # def _reference_rig(self):
    #     import maya.cmds as cmds
    #     import pymel.core as pm
    #
    #     from reveries.utils import get_representation_path_
    #
    #     # Check reference exists
    #     for ref in pm.listReferences():
    #         if str(ref.namespace) == RIG_NS:
    #             print('Remove old reference.')
    #             cmds.file(ref, removeReference=True)
    #
    #     subset_name = self.instance_data['subset']  # 'rigDefaultReview'
    #     asset_id = io.ObjectId(self.instance_data['assetDoc']['_id'])
    #
    #     rig_subset_name = subset_name.split('Review')[0]
    #
    #     # Get data from db
    #     rig_data = io.find_one({'parent': asset_id, 'name': rig_subset_name})
    #
    #     version_data = io.find_one(
    #         {'parent': rig_data['_id'], 'type': 'version'},
    #         sort=[("name", -1)])
    #
    #     representation = io.find_one(
    #         {'parent': version_data['_id'], 'type': 'representation'})
    #
    #     # Get rig file path
    #     parents = io.parenthood(representation)
    #     package_path = get_representation_path_(representation, parents)
    #
    #     file_name = representation["data"]["entryFileName"]
    #     rig_file = os.path.join(package_path, file_name).replace("\\", "/")
    #
    #     cmds.file(rig_file, reference=True, namespace=RIG_NS)
    #
    #     # Set animation
    #     self.__set_reference_animation()
    #
    #     return rig_data['_id']

    def __set_reference_animation(self):
        import maya.cmds as cmds

        cmds.setKeyframe(MAIN_CTRL, v=0, at='rotateY', t=RENDER_RANGE[0])
        cmds.setKeyframe(MAIN_CTRL, v=360, at='rotateY', t=RENDER_RANGE[1])

    def do_export(self):
        import maya.cmds as cmds

        from reveries.maya import utils
        from reveries.maya.usd import skelcache_export
        from reveries.maya.usd.maya_export import MayaUsdExporter

        # Export skeleton cache usd
        # self.rig_subset_id = self._reference_rig()
        root_node = 'ROOT'
        self.__set_reference_animation()
        self.rig_subset_id = utils.get_rig_subset_id(root_node)

        skelcache_export.export(
            self.stage_dir, root_node,
            frame_range=RENDER_RANGE,
            rig_subset_id=self.rig_subset_id
        )

        # Set controller to default value
        cmds.cutKey(
            MAIN_CTRL, time=(100, 120), attribute='rotateY', option='keys')
        cmds.setAttr('{}.rotateY'.format(MAIN_CTRL), 0)

        # Export camera usd
        cam_grp = '{}_grp'.format(self.cam_name)
        cmds.parent(cam_grp, 'ROOT')

        cmds.select(self.cam_name, r=True)
        exporter = MayaUsdExporter(
            export_path=self.cam_usd_path,
            export_selected=True)
        exporter.mergeTransformAndShape = True
        exporter.animation = False
        exporter.export()

        cmds.parent(cam_grp, world=True)
        cmds.select(cl=True)
        print('camera usd export done.')

        # Generate rig_review_prim usd
        self._export_review_prim()

    def _export_review_prim(self):
        from pxr import Usd, UsdGeom

        from reveries.common import get_fps
        from reveries.common.usd.utils import get_UpAxis
        from reveries.maya.usd import skelcache_export

        stage = Usd.Stage.CreateInMemory()

        # Create ROOT define
        UsdGeom.Xform.Define(stage, "/ROOT")
        root_prim = stage.GetPrimAtPath('/ROOT')
        stage.SetDefaultPrim(root_prim)

        # Create sublayer
        root_layer = stage.GetRootLayer()
        root_layer.subLayerPaths.append(skelcache_export.SKELCACHEPRIM_NAME)
        root_layer.subLayerPaths.append(REVIEW_CAMPRIM)

        # Default setting
        UsdGeom.Xform.Define(stage, "/ROOT")
        root_prim = stage.GetPrimAtPath('/ROOT')
        stage.SetDefaultPrim(root_prim)
        stage.SetFramesPerSecond(get_fps())
        stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(stage, get_UpAxis(host="Maya"))

        stage.SetStartTimeCode(RENDER_RANGE[0])
        stage.SetEndTimeCode(RENDER_RANGE[1])

        # print(stage.GetRootLayer().ExportToString())
        stage.GetRootLayer().Export(self.review_usd_file)


class RigReview(object):
    def __init__(self, instance_data):
        from reveries.common.utils import check_dir_exists

        self.renderer = None
        self.rig_subset_id = None

        self.instance_data = instance_data
        self.stage_dir = check_dir_exists(instance_data['repr.USD._stage'])

        self._do_export()

    def _do_export(self):
        # == Export USD == #
        usd_exporter = ExportReviewUSD(
            instance_data=self.instance_data,
            stage_dir=self.stage_dir
        )
        self.cam_name = usd_exporter.cam_name
        self.review_usd_file = usd_exporter.review_usd_file
        self.cam_usd_path = usd_exporter.cam_usd_path
        self.rig_subset_id = usd_exporter.rig_subset_id

    def get_publish_files(self):
        from reveries.maya.usd import skelcache_export

        reps_file = [
            os.path.basename(self.review_usd_file),
            os.path.basename(self.cam_usd_path),
            skelcache_export.SKELCACHE_SOURCE_NAME,
            skelcache_export.SKELCACHE_NAME,
            skelcache_export.SKELCACHEPRIM_NAME
        ]

        return reps_file
