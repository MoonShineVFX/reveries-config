import os

from pxr import Usd, UsdGeom, UsdSkel, Sdf

SKELDATA_SOURCE_NAME = r'skel_source.usd'
SKELDATA_NAME = r'skel_data.usd'


class RigPrimSourceExporter(object):
    def __init__(self, out_dir, shape_merge=False):
        self.out_dir = out_dir
        self.shape_merge = shape_merge

        self.source_path = os.path.join(self.out_dir, SKELDATA_SOURCE_NAME)

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

    def _get_frame_in(self):
        from avalon import io
        _filter = {"type": "project"}
        project_data = io.find_one(_filter)
        frame_in = project_data.get("data", {}).get("edit_in", 101)

        return frame_in

    def _export_source(self):
        import maya.cmds as cmds

        skel = []
        ctrl_node = r'|ROOT|Group|Geometry'
        skel_root = r'|ROOT|Group'

        # Check 'USD_typeName' attribute exists
        if not cmds.attributeQuery('USD_typeName', node=skel_root, ex=True):
            cmds.addAttr(skel_root, longName='USD_typeName', dt='string')
        cmds.setAttr(
            '{}.USD_typeName'.format(skel_root), 'SkelRoot', type='string')

        # Get deformation group
        children = cmds.listRelatives(
            skel_root,
            allDescendents=True, type="transform", fullPath=True
        )
        for child_name in children:
            if child_name.endswith("DeformationSystem"):
                skel.append(child_name)

        skel.append("MotionSystem")

        cmds.select(ctrl_node, r=True)
        cmds.select(skel, add=True)

        # Do export
        cmds.mayaUSDExport(
            selection=True, file=self.source_path,
            frameRange=[self._get_frame_in(), self._get_frame_in()],
            filterTypes=[
                # 'nurbsCurve',
                'parentConstraint', 'scaleConstraint', 'pointConstraint',
                'orientConstraint', 'aimConstraint'
            ],
            exportSkels='explicit',
            exportSkin='explicit',
            exportBlendShapes=True,
            mergeTransformAndShape=self.shape_merge,
            exportUVs=0, exportDisplayColor=0,
            stripNamespaces=1, exportVisibility=1, eulerFilter=1, ign=1
        )

        cmds.select(cl=True)


class SkelDataExtractor(object):
    """
    Export point cache only.
    """
    def __init__(self, source_path=None):
        self.source_path = source_path
        self.save_path = os.path.join(
            os.path.dirname(source_path), SKELDATA_NAME)

        self.del_attrs = [
            'extent', 'material:binding',
            'faceVertexCounts', 'faceVertexIndices', 'doubleSided',
            'normals', 'points',
            # 'skel:animationSource',  # commit it to fix joint size

            'indices', 'elementType', 'familyName',
            'primvars:SculptFreezeColorTemp', 'primvars:SculptFreezeColorTemp:indices',
            'primvars:SculptMaskColorTemp', 'primvars:SculptMaskColorTemp:indices',
            'blendShapeWeights'
        ]

        self.del_timeSamples = [
            'xformOp:translate', 'xformOp:rotateXYZ', 'xformOp:scale'
        ]

        self.del_prims = [
            'Material', 'GeomSubset', 'Scope', 'NurbsCurves'
        ]  # 'SkelAnimation'
        self.skip_prims = ['BlendShape']

        self._export()

        # self.process_add()

    def _export(self):
        from reveries.common import get_fps
        from reveries.common.usd.utils import get_UpAxis
        from reveries.maya.utils import get_model_reference_group

        _, invalid_group = get_model_reference_group()

        stage = Usd.Stage.Open(self.source_path)

        delete_prims = []
        for prim in stage.TraverseAll():
            if prim.GetTypeName() in self.skip_prims:
                continue

            if prim.GetTypeName() in self.del_prims:
                delete_prims.append(prim.GetPath())

            if str(prim.GetPath()).replace("/", "|") in invalid_group:
                delete_prims.append(prim.GetPath())

            if str(prim.GetName()).endswith("DeformationSystem"):
                xform = UsdGeom.Xform(prim)
                over_vis = xform.CreateVisibilityAttr()
                over_vis.Set("invisible")

            # self._check_time_samples(prim)

            for attr in self.del_attrs:
                prim.RemoveProperty(attr)
            
            self._check_blendshape(prim)

        if delete_prims:
            for _prim in delete_prims:
                stage.RemovePrim(_prim)

        # Set fps and axis
        stage.SetFramesPerSecond(get_fps())
        stage.SetTimeCodesPerSecond(get_fps())
        UsdGeom.SetStageUpAxis(stage, get_UpAxis(host="Maya"))

        # print("Export to: ", self.save_path)
        stage.Export(self.save_path)

    def _check_time_samples(self, prim):
        skip_delete = False
        prim_path = str(prim.GetPath())
        prim_path_item = prim_path.split("/")
        # if len(prim_path_item) > 4:
            # if prim_path.split("/")[-2] == "Geometry" or \
            #         prim_path.split("/")[-3] == "Geometry":

        for _attr in self.del_timeSamples:
            time_sample = prim.GetAttribute(_attr).GetTimeSamples()
            if time_sample:
                prim.RemoveProperty(_attr)
                prim.RemoveProperty("xformOpOrder")

        #         skip_delete = True
        #
        # return skip_delete
    
    def _check_blendshape(self, prim):
        attr_dict = {
            "skel:jointIndices": {
                "attr_type": Sdf.ValueTypeNames.IntArray
            },
            "skel:jointWeights": {
                "attr_type": Sdf.ValueTypeNames.FloatArray
            },
        }
        # Set jointIndices/jointWeights
        mesh = UsdGeom.Mesh(prim)
        has_skel_data = mesh.GetPrimvar("skel:jointWeights").HasValue()
        has_blendshape_data = prim.GetAttribute("skel:blendShapes").HasValue()

        if has_blendshape_data and not has_skel_data:
            for attr_name, attr_data in attr_dict.items():
                uv_indices = mesh.CreatePrimvar(
                    attr_name, attr_data["attr_type"]
                )
                uv_indices.Set([0])

    def _set_vis_value(self, mesh, new_mesh):
        vis = mesh.GetVisibilityAttr()

        if vis.GetTimeSamples():
            over_vis = new_mesh.CreateVisibilityAttr()

            for time_sample in vis.GetTimeSamples():
                over_vis.Set(
                    vis.Get(time_sample),
                    time=Usd.TimeCode(time_sample)
                )
        else:
            source_value = vis.Get()

            if source_value == "invisible":
                over_vis = new_mesh.CreateVisibilityAttr()
                over_vis.Set(source_value)

    def process_add(self):
        self.source_stage = Usd.Stage.Open(self.source_path)
        self.new_stage = Usd.Stage.CreateInMemory()

        for prim in self.source_stage.Traverse():
            has_skeleton_data = False
            # print(prim, prim.GetTypeName())
            print(prim.GetPath())
            # print("\n")

            if prim.GetTypeName() == 'Mesh' and prim.IsActive():
                mesh = UsdGeom.Mesh(prim)

                # Create primitive
                prim_path = str(prim.GetPath())
                UsdGeom.Mesh.Define(self.new_stage, prim_path)
                new_mesh_prim = self.new_stage.GetPrimAtPath(prim_path)
                new_mesh = UsdGeom.Mesh(new_mesh_prim)

                # Set AppliedSchemas
                api_schemas = prim.GetAppliedSchemas()
                for _api in api_schemas:
                    new_mesh_prim.AddAppliedSchema(_api)

                if mesh.HasPrimvar("skel:jointWeights"):
                    print("Has joint attribute")
                    has_skeleton_data = self._set_skel_data(
                        mesh, new_mesh, prim, new_mesh_prim)

                # Set blendshape attribute
                if prim.HasAttribute("skel:blendShapes"):
                    print("Has blendshape attribute.")
                    self._set_blendshape_data(mesh, new_mesh, prim, new_mesh_prim, has_skeleton_data)

                self._set_vis_value(mesh, new_mesh)

            if prim.GetTypeName() == 'Xform' and prim.IsActive():
                xform = UsdGeom.Xform(prim)

                prim_path = str(prim.GetPath())
                over_xform = UsdGeom.Xform.Define(self.new_stage, prim_path)
                over_xform_prim = self.new_stage.GetPrimAtPath(prim_path)

                prim_path_item = prim_path.split("/")
                if len(prim_path_item) > 4:
                    if prim_path.split("/")[-2] == "Geometry" or prim_path.split("/")[-3] == "Geometry":
                        print("Export ts:", prim_path)
                        set_result = False
                        xform_order = xform.GetXformOpOrderAttr()

                        attrs_name = [
                            "xformOp:translate",
                            "xformOp:rotateXYZ",
                            "xformOp:scale",
                            "xformOp:translate:pivot"
                        ]
                        for attr_name in attrs_name:
                            if prim.HasAttribute(attr_name):
                                value = prim.GetAttribute(attr_name).Get()

                                if value:
                                    attr = over_xform_prim.CreateAttribute(
                                        attr_name, Sdf.ValueTypeNames.Float3)
                                    attr.Set(value)
                                    attr.SetCustom(False)
                                    set_result = True

                        if set_result:
                            order_value = xform_order.Get()
                            if order_value:
                                over_xform_order = over_xform.GetXformOpOrderAttr()
                                over_xform_order.Clear()
                                over_xform_order.Set(xform_order.Get())

                self._set_vis_value(xform, over_xform)

            if prim.GetTypeName() == 'SkelRoot' and prim.IsActive():
                prim_path = str(prim.GetPath())
                UsdSkel.Root.Define(self.new_stage, prim_path)
                over_xform_prim = self.new_stage.GetPrimAtPath(prim_path)
                over_xform = UsdGeom.Xform(over_xform_prim)

            if prim.GetTypeName() == 'BlendShape' and prim.IsActive():
                prim_path = str(prim.GetPath())
                UsdSkel.BlendShape.Define(self.new_stage, prim_path)
                bs_prim = self.new_stage.GetPrimAtPath(prim_path)
                # xform = UsdGeom.Xform(bs_prim)

                attr_dict = {
                    "normalOffsets": {
                        "attr_type": Sdf.ValueTypeNames.Vector3fArray
                    },
                    "offsets": {
                        "attr_type": Sdf.ValueTypeNames.Vector3fArray
                    },
                    "pointIndices": {
                        "attr_type": Sdf.ValueTypeNames.IntArray
                    }
                }
                for attr_name, attr_data in attr_dict.items():
                    if prim.HasAttribute(attr_name):
                        value = prim.GetAttribute(attr_name).Get()
                        if value:
                            attr = bs_prim.CreateAttribute(
                                attr_name, attr_data["attr_type"])
                            attr.Set(value)

        print("Export to: {}".format(self.save_path))
        self.new_stage.Export(self.save_path)
        # self.new_stage.GetRootLayer().ExportToString()

    def _set_skel_data(self, mesh, new_mesh, prim, new_mesh_prim):
        has_skeleton_data = False
        attr_dict = {
            "skel:jointIndices": {
                "attr_type": Sdf.ValueTypeNames.IntArray
            },
            "skel:jointWeights": {
                "attr_type": Sdf.ValueTypeNames.FloatArray
            },
        }
        # Set jointIndices/jointWeights
        for attr_name, attr_data in attr_dict.items():
            primvar = mesh.GetPrimvar(attr_name)
            if primvar:
                value = primvar.Get()
                if value:
                    uv_indices = new_mesh.CreatePrimvar(
                        attr_name, attr_data["attr_type"],
                        elementSize=primvar.GetElementSize(),
                        interpolation=primvar.GetInterpolation()
                    )
                    uv_indices.Set(value)
                    has_skeleton_data = True
        #
        attr_name = "skel:geomBindTransform"
        if mesh.HasPrimvar(attr_name):
            value = mesh.GetPrimvar(attr_name).Get()
            if value:
                uv_indices = new_mesh.CreatePrimvar(
                    attr_name, Sdf.ValueTypeNames.Matrix4d
                )
                uv_indices.Set(value)
        #
        attr_name = "skel:joints"
        if prim.HasAttribute(attr_name):
            value = prim.GetAttribute(attr_name).Get()
            if value:
                attr = new_mesh_prim.CreateAttribute(
                    attr_name, Sdf.ValueTypeNames.TokenArray)
                attr.Set(value)

        # Add relationship
        attr_name = "skel:skeleton"
        rel_source = prim.GetRelationship(attr_name)
        if rel_source.HasAuthoredTargets():
            value_obj = rel_source.GetTargets()[0]
            value = value_obj.pathString
            rel_over = new_mesh_prim.CreateRelationship(attr_name)
            rel_over.AddTarget(value)

        return has_skeleton_data

    def _set_blendshape_data(self, mesh, new_mesh, prim, new_mesh_prim, has_skeleton_data):
        has_blendshape_data = False
        attr_name = "skel:blendShapes"
        if prim.HasAttribute(attr_name):
            value = prim.GetAttribute(attr_name).Get()
            if value:
                attr = new_mesh_prim.CreateAttribute(
                    attr_name, Sdf.ValueTypeNames.TokenArray)
                attr.Set(value)
                has_blendshape_data = True

        attr_name = "skel:blendShapeTargets"
        rel_source = prim.GetRelationship(attr_name)
        if rel_source.HasAuthoredTargets():
            rel_over = new_mesh_prim.CreateRelationship(attr_name)
            value_obj = rel_source.GetTargets()
            for _obj in value_obj:
                value = _obj.pathString
                rel_over.AddTarget(value)

        if not has_skeleton_data and has_blendshape_data:
            attr_dict = {
                "skel:jointIndices": {
                    "attr_type": Sdf.ValueTypeNames.IntArray
                },
                "skel:jointWeights": {
                    "attr_type": Sdf.ValueTypeNames.FloatArray
                },
            }
            for attr_name, attr_data in attr_dict.items():
                uv_indices = new_mesh.CreatePrimvar(
                    attr_name, attr_data["attr_type"]
                )
                uv_indices.Set([0])


def export(out_dir, shape_merge=True):
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # Export source
    exporter = RigPrimSourceExporter(out_dir=out_dir, shape_merge=shape_merge)

    # Export skeleton usd
    source_path = exporter.source_path
    SkelDataExtractor(source_path=source_path)
