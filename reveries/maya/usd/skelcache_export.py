import os
import json

from avalon import io

from pxr import Usd, UsdGeom, Sdf

SKELCACHE_SOURCE_NAME = r'skelcache_source.usd'
SKELCACHE_NAME = r'skelecache_data.usd'
SKELCACHEPRIM_NAME = r'skelecache_prim.usda'
OVERRIDE_MESHES_NAME = r'skelecache_override_meshes.usd'


class SkeleCacheSourceExporter(object):
    def __init__(self, out_dir, root_node, frame_range=[], shape_merge=True,
                 root_usd_path=None):
        self.frame_range = frame_range
        self.out_dir = out_dir
        self.shape_merge = shape_merge
        self.root_node = root_node
        self.root_usd_path = root_usd_path
        self.geometry_path = ""
        self.override_mesh = []

        self.source_path = os.path.join(self.out_dir, SKELCACHE_SOURCE_NAME)

        self._load_plugin()
        self._export_source()

    def _load_plugin(self):
        """
        Load usd plugin in current session
        """
        import maya.cmds as cmds
        plugins = ["pxrUsd", "pxrUsdPreviewSurface", "mayaUsdPlugin"]

        for plugin_name in plugins:
            cmds.loadPlugin(plugin_name, quiet=True)

    def _export_source(self):
        import maya.cmds as cmds

        # geo = r'Geometry'
        # skel = r'DeformationSystem'

        # SkelRoot = "Group"
        # check = cmds.attributeQuery('USD_typeName', node=SkelRoot, ex=True)
        # if not check:
        #     cmds.addAttr(SkelRoot, longName='USD_typeName', dt='string')
        # cmds.setAttr(SkelRoot + '.USD_typeName', 'SkelRoot', type='string')

        children = cmds.listRelatives(
            self.root_node,
            allDescendents=True, type="transform", fullPath=True
        )
        skel = []

        for child_name in children:
            if child_name.endswith("Geometry"):
                self.geometry_path = child_name
            if child_name.endswith("DeformationSystem"):
                skel.append(child_name)

            if cmds.attributeQuery('override_mesh', node=child_name, ex=True):
                if cmds.getAttr("{}.override_mesh".format(child_name)):
                    # usd_path = "/".join(
                    #     [s.split(":")[-1] for s in child_name.split("|")]).\
                    #     replace(self.root_usd_path, "/ROOT")
                    self.override_mesh.append(child_name)

        # skel = ["GamerA_rig_01_:DeformationSystem"]
        print("DeformationSystem: ", skel)
        cmds.select(self.geometry_path, r=True)
        cmds.select(skel, add=True)

        cmds.mayaUSDExport(
            selection=True,
            frameRange=self.frame_range,
            file=self.source_path,
            stripNamespaces=1,
            exportBlendShapes=True,
            exportSkels="explicit",
            exportSkin="explicit",
            filterTypes=[
                # 'nurbsCurve',
                'parentConstraint', 'scaleConstraint', 'pointConstraint',
                'orientConstraint', 'aimConstraint'
            ],
            exportVisibility=1, eulerFilter=1,
            mergeTransformAndShape=self.shape_merge,
            exportDisplayColor=0, ign=1
        )
        cmds.select(cl=True)


class SkelDataExtractor(object):
    """
    Export point cache only.
    """
    def __init__(self, source_path=None, root_usd_path=None, rig_subset_id=None):
        self.rig_subset_id = rig_subset_id
        self.root_usd_path = root_usd_path  # '/rigDefault/ROOT'
        self.source_path = source_path
        self.save_path = os.path.join(
            os.path.dirname(source_path), SKELCACHE_NAME
        )
        # self.override_mesh = override_mesh

        self.del_attrs = [
            'extent', 'material:binding',
            'primvars:map1:indices', 'primvars:map1',
            'faceVertexCounts', 'faceVertexIndices', 'doubleSided',
            'normals', 'points',
            'skel:joints', 'skel:blendShapes', 'skel:blendShapeTargets',
            'skel:skeleton', 'subdivisionScheme',
            #
            'restTransforms',
            'blendShapes',
            #
            'primvars:UVChannel_1:indices', 'primvars:UVChannel_1',
            'primvars:SculptMaskColorTemp:indices', 'primvars:SculptMaskColorTemp',
            'primvars:SculptFreezeColorTemp:indices', 'primvars:SculptFreezeColorTemp'
        ]

        self.del_prims = [
            'Material', 'BlendShape', 'GeomSubset'
        ]

        # self._export_override()
        self._export_del_attr()

    def __get_rig_pub_data(self):
        from reveries.common import get_publish_files

        # Get data from skeleton publish folder
        rig_data = io.find_one({"_id": io.ObjectId(self.rig_subset_id)})

        _filter = {
            "name": "{}Skeleton".format(rig_data["name"]),
            "parent": rig_data["parent"]
        }
        rig_prim_data = io.find_one(_filter)

        model_subset_json = get_publish_files.get_files(
            rig_prim_data["_id"], key='modelDataFileName').get("USD", "")

        with open(model_subset_json, "r") as file:
            _pub_data = json.load(file)

        return _pub_data.get("invalid_group", [])

    def _export_del_attr(self):
        from reveries.common import get_fps
        from reveries.common.usd.utils import get_UpAxis

        invalid_group = self.__get_rig_pub_data()

        stage = Usd.Stage.Open(self.source_path)
        layer = stage.GetRootLayer()

        # Remove rigDefault primitive
        if stage.GetDefaultPrim().GetName() != "ROOT":
            # root_usd_path = '/rigDefault/ROOT'
            destination_path = '/ROOT'

            temp_layer = Sdf.Layer.CreateAnonymous()
            Sdf.CopySpec(layer, self.root_usd_path, temp_layer, '/temp')
            stage.RemovePrim(self.root_usd_path)
            UsdGeom.Xform.Define(stage, destination_path)
            Sdf.CopySpec(temp_layer, '/temp', layer, destination_path)
            temp_layer.Clear()

            try:
                del_prim = "/{}".format(self.root_usd_path.split("/")[1])
                stage.RemovePrim(del_prim)
            except Exception as e:
                print(e)

        # Remove unnecessary primitive and attribute
        delete_prims = []
        for prim in stage.TraverseAll():
            if prim.GetTypeName() in self.del_prims:
                delete_prims.append(prim.GetPath())

            if str(prim.GetPath()).replace("/", "|") in invalid_group:
                delete_prims.append(prim.GetPath())

            if prim.GetName() == "DeformationSystem":
                xform = UsdGeom.Xform(prim)
                over_vis = xform.CreateVisibilityAttr()
                over_vis.Set("invisible")

            for attr in self.del_attrs:
                # if str(prim.GetPath()) in self.override_mesh and attr in ["points"]:
                #     print("....skip remove point: ", str(prim.GetPath()))
                #     continue
                prim.RemoveProperty(attr)
            #
            # if str(prim.GetPath()) in self.override_mesh:
            #     print("....override mesh: ", str(prim.GetPath()))
            #     # uniform token[] skel:joints = []
            #     attr = prim.CreateAttribute("skel:joints", Sdf.ValueTypeNames.TokenArray)
            #     attr.Set([])

        if delete_prims:
            for _prim in delete_prims:
                stage.RemovePrim(_prim)

        # Stage setting
        root_prim = stage.GetPrimAtPath('/ROOT')
        stage.SetDefaultPrim(root_prim)

        stage.SetFramesPerSecond(get_fps())
        stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(stage, get_UpAxis(host="Maya"))

        stage.Export(self.save_path)

    def _export_override(self):
        from reveries.common import get_fps
        from reveries.common.usd.utils import get_UpAxis

        self.source_stage = Usd.Stage.Open(self.source_path)
        source_layer = self.source_stage.GetRootLayer()

        self.override_stage = Usd.Stage.CreateInMemory()
        over_layer = self.override_stage.GetRootLayer()

        # Remove rigDefault primitive
        if self.source_stage.GetDefaultPrim().GetName() != "ROOT":

            # root_usd_path = '/rigDefault/ROOT'
            destination_path = '/ROOT'

            temp_layer = Sdf.Layer.CreateAnonymous()
            Sdf.CopySpec(source_layer, self.root_usd_path, temp_layer, '/temp')
            self.source_stage.RemovePrim(self.root_usd_path)
            UsdGeom.Xform.Define(self.source_stage, destination_path)
            Sdf.CopySpec(temp_layer, '/temp', source_layer, destination_path)
            temp_layer.Clear()

        try:
            del_prim = "/{}".format(self.root_usd_path.split("/")[1])
            self.source_stage.RemovePrim(del_prim)
        except Exception as e:
            print(e)

        # Create override stage
        for prim in self.source_stage.Traverse():
            # print prim, prim.GetTypeName(), prim.IsActive()
            # print prim.GetPath()

            # if prim.GetTypeName() == 'Mesh' and prim.IsActive():
            #     # print prim
            #     mesh = UsdGeom.Mesh(prim)
            #     points = mesh.GetPointsAttr()
            #
            #     prim_path = self._check_prim_path(prim)
            #
            #     over_mesh_prim = self.override_stage.OverridePrim(prim_path)
            #     over_mesh = UsdGeom.Mesh(over_mesh_prim)
            #     over_points = over_mesh.CreatePointsAttr()
            #
            #     for time_sample in points.GetTimeSamples():
            #         over_points.Set(
            #             points.Get(time_sample),
            #             time=Usd.TimeCode(time_sample)
            #         )
            #
            #     self._set_vis_value(mesh, over_mesh)
            prim_path = str(prim.GetPath())
            if "/Geometry" not in prim_path:
                continue

            if prim.GetTypeName() == 'Xform' and prim.IsActive():
                xform = UsdGeom.Xform(prim)
                # prim_path = self._check_prim_path(prim)
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
                                print('Note: skip {}, type is {}, in {}.'.
                                      format(op_name, op_type, prim_path))

                    over_xform_order = over_xform.GetXformOpOrderAttr()
                    over_xform_order.Clear()
                    over_xform_order.Set(xform_order.Get())

                self._set_vis_value(xform, over_xform)

            if prim.GetTypeName() == 'Skeleton' and prim.IsActive():

                self.copy_layer(
                    self.override_stage, over_layer, source_layer, prim_path, prim_type="override")

                over_prim = self.override_stage.GetPrimAtPath('{}/Animation'.format(prim_path))
                print("over_prim: ", over_prim)
                for attr in self.del_attrs:
                    over_prim.RemoveProperty(attr)

        # Delete unnecessary prim
        # try:
        #     del_prim = "/{}".format(self.root_usd_path.split("/")[1])
        #     self.override_stage.RemovePrim(del_prim)
        # except Exception as e:
        #     print(e)

        #
        root_usd_path = '/ROOT/Group/Main'

        temp_layer = Sdf.Layer.CreateAnonymous()
        Sdf.CopySpec(source_layer, root_usd_path, temp_layer, '/temp')

        # stage.RemovePrim(root_usd_path)
        UsdGeom.Xform.Define(self.override_stage, root_usd_path)

        Sdf.CopySpec(temp_layer, '/temp', over_layer, root_usd_path)

        temp_layer.Clear()

        #
        self.override_stage.SetFramesPerSecond(get_fps())
        self.override_stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(self.override_stage, get_UpAxis(host="Maya"))

        self.override_stage.Export(self.save_path)

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

    def copy_layer(self, defr_stage, defr_layer, source_layer, prim_path, prim_type="default"):
        temp_layer = Sdf.Layer.CreateAnonymous()
        Sdf.CopySpec(source_layer, prim_path, temp_layer, '/temp')

        if prim_type == "default":
            UsdGeom.Xform.Define(defr_stage, prim_path)
        else:
            defr_stage.OverridePrim(prim_path)

        Sdf.CopySpec(temp_layer, '/temp', defr_layer, prim_path)
        temp_layer.Clear()


class OverrideMeshExporter(object):
    def __init__(self, source_path, frame_range, override_meshes=[],
                 root_usd_path='', shape_merge=True):
        self.shape_merge = shape_merge
        self.frame_range = frame_range
        self.root_usd_path = root_usd_path
        self.override_meshes = override_meshes

        self.tmp_path = os.path.join(
            source_path, r'tmp_{}'.format(OVERRIDE_MESHES_NAME))
        self.save_path = os.path.join(source_path, OVERRIDE_MESHES_NAME)

        self.del_attrs = [
            'extent', 'material:binding',
            'faceVertexCounts', 'faceVertexIndices', 'doubleSided',
            'normals',
            'xformOpOrder', 'xformOp:translate:pivot'
        ]

        if override_meshes:
            self._do_export()

    def _export_source(self):
        import maya.cmds as cmds

        # Export source
        cmds.select(self.override_meshes, add=True)
        cmds.mayaUSDExport(
            selection=True,
            frameRange=self.frame_range,
            file=self.tmp_path,
            stripNamespaces=1,
            filterTypes=[
                'parentConstraint', 'scaleConstraint', 'pointConstraint',
                'orientConstraint', 'aimConstraint'
            ],
            exportVisibility=1, eulerFilter=1,
            mergeTransformAndShape=self.shape_merge,
            exportDisplayColor=0, ign=1
        )
        cmds.select(cl=True)

    def _do_export(self):
        from reveries.common import get_fps
        from reveries.common.usd.utils import get_UpAxis

        # === Export Source ===
        self._export_source()

        # === Extractor Points Only ===
        stage = Usd.Stage.Open(self.tmp_path)
        layer = stage.GetRootLayer()

        override_stage = Usd.Stage.CreateInMemory()

        # Remove parent primitive
        if stage.GetDefaultPrim().GetName() != "ROOT":
            destination_path = '/ROOT'

            temp_layer = Sdf.Layer.CreateAnonymous()
            Sdf.CopySpec(layer, self.root_usd_path, temp_layer, '/temp')
            stage.RemovePrim(self.root_usd_path)
            UsdGeom.Xform.Define(stage, destination_path)
            Sdf.CopySpec(temp_layer, '/temp', layer, destination_path)
            temp_layer.Clear()

        try:
            del_prim = "/{}".format(self.root_usd_path.split("/")[1])
            stage.RemovePrim(del_prim)
        except Exception as e:
            print(e)

        # Extractor point attribute
        for prim in stage.TraverseAll():
            if prim.GetTypeName() == "Mesh":
                prim_path = str(prim.GetPath())
                over_mesh_prim = override_stage.OverridePrim(prim_path)
                # Add attribute to none
                joint_attr = over_mesh_prim.CreateAttribute(
                    "skel:joints", Sdf.ValueTypeNames.TokenArray)
                joint_attr.Set([])
                joint_attr.SetCustom(False)

                skel_attr = over_mesh_prim.CreateRelationship("skel:skeleton")
                skel_attr.AddTarget('/None')
                skel_attr.SetCustom(False)

                # Get point attribute
                mesh = UsdGeom.Mesh(prim)
                points = mesh.GetPointsAttr()
                over_mesh = UsdGeom.Mesh(over_mesh_prim)
                over_points = over_mesh.CreatePointsAttr()

                for time_sample in points.GetTimeSamples():
                    over_points.Set(
                        points.Get(time_sample),
                        time=Usd.TimeCode(time_sample)
                    )
            # for attr in self.del_attrs:
            #     prim.RemoveProperty(attr)

        # Stage setting
        root_prim = override_stage.GetPrimAtPath('/ROOT')
        override_stage.SetDefaultPrim(root_prim)

        override_stage.SetFramesPerSecond(get_fps())
        override_stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(override_stage, get_UpAxis(host="Maya"))

        override_stage.SetStartTimeCode(stage.GetStartTimeCode())
        override_stage.SetEndTimeCode(stage.GetEndTimeCode())

        override_stage.Export(self.save_path)


class SkelCachePrimExporter(object):
    def __init__(self, out_dir, frame_range, rig_subset_id=None):
        self.frame_range = frame_range
        self.out_dir = out_dir
        self.rig_subset_id = rig_subset_id  # "5faa5b7a92db631874696778"
        self.output_path = os.path.join(out_dir, SKELCACHEPRIM_NAME)
        self._export()

    def _get_rig_prim_file(self):
        from reveries.common import get_publish_files

        _filter = {"_id": io.ObjectId(self.rig_subset_id)}
        rig_data = io.find_one(_filter)

        _filter = {
            "name": "{}Prim".format(rig_data["name"]),
            "parent": rig_data["parent"]
        }
        rig_prim_data = io.find_one(_filter)

        return get_publish_files.get_files(
            rig_prim_data["_id"], key='entryFileName').get("USD", "")

    def _export(self):
        from reveries.common import get_fps
        from reveries.common.usd.utils import get_UpAxis

        rig_prim_file = self._get_rig_prim_file()

        stage = Usd.Stage.CreateInMemory()

        root_layer = stage.GetRootLayer()
        if os.path.exists(os.path.join(self.out_dir, OVERRIDE_MESHES_NAME)):
            root_layer.subLayerPaths.append(OVERRIDE_MESHES_NAME)
        root_layer.subLayerPaths.append(SKELCACHE_NAME)
        root_layer.subLayerPaths.append(rig_prim_file)

        UsdGeom.Xform.Define(stage, "/ROOT")
        root_prim = stage.GetPrimAtPath('/ROOT')
        stage.SetDefaultPrim(root_prim)
        stage.SetFramesPerSecond(get_fps())
        stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(stage, get_UpAxis(host="Maya"))

        stage.SetStartTimeCode(self.frame_range[0])
        stage.SetEndTimeCode(self.frame_range[1])

        # print(stage.GetRootLayer().ExportToString())
        stage.GetRootLayer().Export(self.output_path)


def export(out_dir, root_node, frame_range=[], rig_subset_id="", shape_merge=True):
    import maya.cmds as cmds

    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    root_node = cmds.ls(root_node, long=True)[0]
    root_usd_path = "/".join([s.split(":")[-1] for s in root_node.split("|")])
    print("root_usd_path: ", root_usd_path)  # r'/rigDefault/ROOT'

    # Export source
    exporter = SkeleCacheSourceExporter(
        out_dir, root_node, frame_range=frame_range, shape_merge=shape_merge,
        root_usd_path=root_usd_path
    )
    print("Source done.")

    # Export skeleton cache usd
    SkelDataExtractor(
        source_path=exporter.source_path,
        root_usd_path=root_usd_path,
        rig_subset_id=rig_subset_id,
        # override_mesh=exporter.override_mesh
    )
    print("skeleton data done.")

    # Export override mesh
    OverrideMeshExporter(
        out_dir, frame_range,
        override_meshes=exporter.override_mesh,
        root_usd_path=root_usd_path
    )

    # Export cache_prim.usd
    if rig_subset_id:
        SkelCachePrimExporter(out_dir, frame_range, rig_subset_id=rig_subset_id)
