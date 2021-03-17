# -*- coding: utf-8 -*-
import os

from avalon import io
from pxr import Usd, UsdGeom


class PointCacheExtractor(object):
    """
    Export point cache only.
    """
    def __init__(self, source_path=None, shot_time=None,
                 root_usd_path=None, has_proxy=None):
        self.source_path = source_path
        self.shot_time = shot_time

        self.source_stage = None
        self.override_stage = None
        self.root_usd_path = root_usd_path
        self.has_proxy = has_proxy

        self.process()

    def _open_stage(self):
        assert os.path.exists(self.source_path), \
            'file not exist: {}'.format(self.source_path)
        self.source_stage = Usd.Stage.Open(self.source_path)

    def _create_stage(self):
        self.override_stage = Usd.Stage.CreateInMemory()
        if self.shot_time:
            self.override_stage.SetStartTimeCode(self.shot_time[0])
            self.override_stage.SetEndTimeCode(self.shot_time[1])

    def _check_prim_path(self, prim):
        def _check_mod_exists(key):
            """
            Check MOD group exists or not.
            :param key: modelDefault/modelDefaultProxy
            :return:
            """
            # destination_path = '/ROOT/{}/MOD'.format(key)

            # === Just for transition === #
            _filter = {"type": "project"}
            project_data = io.find_one(_filter)
            if project_data["name"] in ["201912_ChimelongPreshow"]:
                destination_path = '/ROOT/{}/MOD'.format(key)
                for prim in self.source_stage.TraverseAll():
                    if '/ROOT/MOD/' in str(prim.GetPath()):
                        destination_path = '/ROOT/{}'.format(key)
                        break
                return destination_path
            # === Just for transition end === #

            destination_path = '/ROOT/MOD'
            for prim in self.source_stage.TraverseAll():
                if '/ROOT/MOD/' in str(prim.GetPath()):
                    # destination_path = '/ROOT/{}'.format(key)
                    destination_path = '/ROOT'
                    break
            return destination_path

        prim_path = str(prim.GetPath())
        if self.root_usd_path:
            # if self.has_proxy and "_proxy" in str(prim.GetPath()):
            #     prim_path = str(prim.GetPath()).replace(
            #         self.root_usd_path, _check_mod_exists("modelDefaultProxy"))
            # else:
            prim_path = str(prim.GetPath()).replace(
                self.root_usd_path, _check_mod_exists("modelDefault"))

        return prim_path

    def _set_vis_value(self, mesh, over_mesh):
        vis = mesh.GetVisibilityAttr()

        if vis.GetTimeSamples():
            over_vis = over_mesh.CreateVisibilityAttr()

            for time_sample in vis.GetTimeSamples():
                over_vis.Set(
                    vis.Get(time_sample),
                    time=Usd.TimeCode(time_sample)
                )
        else:
            source_value = vis.Get()

            if source_value == "invisible":
                over_vis = over_mesh.CreateVisibilityAttr()
                over_vis.Set(source_value)

    def process(self):
        from reveries.common import get_fps
        from reveries.common.usd.utils import get_UpAxis

        self._open_stage()
        self._create_stage()
        for prim in self.source_stage.Traverse():
            # print prim, prim.GetTypeName(), prim.IsActive()
            # print prim.GetPath()

            if prim.GetTypeName() == 'Mesh' and prim.IsActive():
                # print prim
                mesh = UsdGeom.Mesh(prim)
                points = mesh.GetPointsAttr()

                prim_path = self._check_prim_path(prim)

                over_mesh_prim = self.override_stage.OverridePrim(prim_path)
                over_mesh = UsdGeom.Mesh(over_mesh_prim)
                over_points = over_mesh.CreatePointsAttr()

                for time_sample in points.GetTimeSamples():
                    over_points.Set(
                        points.Get(time_sample),
                        time=Usd.TimeCode(time_sample)
                    )

                self._set_vis_value(mesh, over_mesh)

            if prim.GetTypeName() == 'Xform' and prim.IsActive():
                xform = UsdGeom.Xform(prim)
                prim_path = self._check_prim_path(prim)
                over_xform_prim = self.override_stage.OverridePrim(prim_path)
                over_xform = UsdGeom.Xform(over_xform_prim)

                if xform.GetTimeSamples():
                    xform_order = xform.GetXformOpOrderAttr()

                    # over_xform = UsdGeom.Xform(over_xform_prim)

                    xform_op_names = []
                    for op in xform.GetOrderedXformOps():
                        if op.GetTimeSamples():
                            op_type = op.GetOpType()
                            op_name = op.GetName()

                            if op_type not in xform_op_names:
                                over_op = over_xform.AddXformOp(op_type)
                                for time_sample in op.GetTimeSamples():
                                    over_op.Set(
                                        op.Get(time_sample),
                                        time=Usd.TimeCode(time_sample)
                                    )
                                xform_op_names.append(op_type)
                            else:
                                print('Note: skip {}, '
                                      'type is {}, in {}.'.format(
                                        op_name,
                                        op_type,
                                        over_xform_prim.GetPath())
                                )

                    over_xform_order = over_xform.GetXformOpOrderAttr()
                    over_xform_order.Clear()
                    over_xform_order.Set(xform_order.Get())

                self._set_vis_value(xform, over_xform)

        # Delete unnecessary prim
        try:
            del_prim = "/{}".format(self.root_usd_path.split("/")[1])
            self.override_stage.RemovePrim(del_prim)
        except Exception as e:
            print(e)

        self.override_stage.SetFramesPerSecond(get_fps())
        self.override_stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(self.override_stage, get_UpAxis(host="Maya"))

    def get_stage(self):
        return self.override_stage

    def export(self, save_path):
        self.override_stage.Export(save_path)
        # self.override_stage.GetRootLayer().Export(save_path)

    def clean(self):
        os.remove(self.source_path)


class PointCacheExporter(object):
    def __init__(self, output_dir=None, export_node=None, root_usd_path="",
                 frame_range=[], asset_name=None, out_cache=None,
                 file_info=None, look_variant=None):

        import maya.cmds as cmds
        from reveries.maya.usd import get_export_hierarchy

        self.files_info = file_info or {
            'authored_data': 'authored_data.usd',
            'source': 'source.usd',
            'main': 'pointcache_prim.usda'
        }

        if not frame_range:
            self.start_frame = cmds.playbackOptions(query=True, ast=True)
            self.end_frame = cmds.playbackOptions(query=True, aet=True)
        else:
            self.start_frame, self.end_frame = frame_range

        self.export_node = export_node
        self.staging_dir = output_dir
        self.asset_name = asset_name
        self.look_variant = look_variant

        if out_cache:
            self.out_cache = out_cache
        else:
            self.out_cache = cmds.listRelatives(
                export_node, allDescendents=True, fullPath=True, type='mesh')

        if root_usd_path:
            self.root_usd_path = root_usd_path
        else:
            _, self.root_usd_path = get_export_hierarchy(self.out_cache[0])

    def export_usd(self):
        from reveries.maya.usd import load_maya_plugin
        load_maya_plugin()

        print('start frame: %s\n'
              'end frame: %s' % (self.start_frame, self.end_frame))

        # === Export source.usd === #
        self.source_outpath = os.path.join(self.staging_dir,
                                           self.files_info['source'])
        self._export_source(self.source_outpath)

        if self.asset_name:
            # === Export authored_data.usda === #
            outpath = os.path.join(self.staging_dir,
                                   self.files_info['authored_data'])
            self._export_authored_data(outpath)
            print('authored_data.usd done')

            # === Export ani.usda === #
            outpath = os.path.join(self.staging_dir, self.files_info['main'])
            self._export_ani(outpath)
            print('Export pointcache_prim.usda done.')

        print("Pointcache USD export done.")

    def _export_source(self, outpath):
        import maya.cmds as cmds
        from reveries.maya.usd.maya_export import MayaUsdExporter

        # r'HanMaleA_rig_02:HanMaleA_model_01_:Geometry'
        cmds.select(self.export_node)

        frame_range = [self.start_frame, self.end_frame]
        exporter = MayaUsdExporter(export_path=outpath,
                                   frame_range=frame_range,
                                   export_selected=True)
        exporter.mergeTransformAndShape = True
        exporter.animation = True
        exporter.export()

        cmds.select(cl=True)

        # TODO: Get shape_merge value from rig publish data

    def _export_authored_data(self, outpath):
        # Check has proxy group
        has_proxy = self._check_has_proxy()

        pe = PointCacheExtractor(
            self.source_outpath,
            root_usd_path=self.root_usd_path,
            has_proxy=has_proxy
        )
        pe.export(outpath)

    def _export_ani(self, outpath):
        from pxr import Usd, UsdGeom
        from reveries.common import get_publish_files, get_fps
        from reveries.common.usd.utils import get_UpAxis

        # Get asset id
        _filter = {"type": "asset", "name": self.asset_name}
        asset_data = io.find_one(_filter)
        asset_id = asset_data['_id']

        # Get asset prim usd file
        _filter = {
            "type": "subset",
            "name": "assetPrim",
            "parent": asset_id
        }
        assetprim_data = io.find_one(_filter)
        publish_files = get_publish_files.get_files(assetprim_data['_id'])
        asset_prim_usd_files = publish_files.get('USD', [])

        if asset_prim_usd_files:
            asset_prim_usd = asset_prim_usd_files[0]
        else:
            asset_prim_usd = ''
            print('No asset prim publish file found.')

        # Generate usd file
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/ROOT")
        root_prim = stage.GetPrimAtPath('/ROOT')

        root_layer = stage.GetRootLayer()
        root_layer.subLayerPaths.append(self.files_info['authored_data'])
        root_layer.subLayerPaths.append(asset_prim_usd)

        # Check lookdev dependency
        if self.look_variant:
            try:
                vs = root_prim.GetVariantSet("appearance")
                vs.SetVariantSelection(self.look_variant)
            except Exception as e:
                raise RuntimeError(
                    "Set lookdev to {} failed. Error: {}".format(
                        self.look_variant, e))

        # Set metadata
        stage.SetDefaultPrim(root_prim)
        stage.SetStartTimeCode(self.start_frame)
        stage.SetEndTimeCode(self.end_frame)
        stage.SetFramesPerSecond(get_fps())
        stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(stage, get_UpAxis(host="Maya"))

        stage.GetRootLayer().Export(outpath)

    def _check_has_proxy(self):
        import maya.cmds as cmds

        ts_children = cmds.listRelatives(
            self.export_node,
            allDescendents=True,
            fullPath=True,
            type='transform'
        )

        if not ts_children or not self.out_cache:
            return False

        for _cache in self.out_cache + ts_children:
            if '_proxy' in _cache:
                return True

        return False
