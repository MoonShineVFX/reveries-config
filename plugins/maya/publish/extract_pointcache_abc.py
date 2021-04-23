
import contextlib
import pyblish.api


class ExtractPointCacheABC(pyblish.api.InstancePlugin):
    """
    """

    order = pyblish.api.ExtractorOrder
    hosts = ["maya"]
    label = "Extract PointCache (abc)"
    families = [
        "reveries.pointcache.abc",
    ]

    def process(self, instance):
        from maya import cmds
        from reveries import utils

        staging_dir = utils.stage_dir(dir=instance.data["_sharedStage"])
        filename = "%s.abc" % instance.data["subset"]
        outpath = "%s/%s" % (staging_dir, filename)

        instance.data["repr.Alembic._stage"] = staging_dir
        instance.data["repr.Alembic._hardlinks"] = [filename]
        instance.data["repr.Alembic.entryFileName"] = filename

        if instance.data.get("staticCache"):
            start = cmds.currentTime(query=True)
            end = cmds.currentTime(query=True)
        else:
            context_data = instance.context.data
            start = context_data["startFrame"]
            end = context_data["endFrame"]

        instance.data["startFrame"] = start
        instance.data["endFrame"] = end

        euler_filter = instance.data.get("eulerFilter", False)
        tension = instance.data.get("requireTensionMap")
        rest_pos = instance.data.get("requireRestPos")
        root = instance.data["outCache"]

        if tension:
            instance.data["repr.Alembic._delayRun"] = {
                "func": self.export_alembic_with_tension,
                "args": [
                    tension,
                    [root, outpath, start, end, rest_pos],
                    {"eulerFilter": euler_filter, "writeColorSets": True}
                ],
            }
        else:
            instance.data["repr.Alembic._delayRun"] = {
                "func": self.export_alembic,
                "args": [root, outpath, start, end, rest_pos],
                "kwargs": {"eulerFilter": euler_filter}
            }

    def export_alembic_with_tension(self, tension, args, kwargs):
        from maya import cmds
        from itertools import izip
        from contextlib import contextmanager
        from reveries.maya import capsule

        cmds.loadPlugin("TensionMap", quiet=True)

        @contextmanager
        def tension_context(transforms):
            tensions = []
            originals = []
            deformeds = []
            deformers = []
            bool_attrs = []

            for node in transforms:
                # find deformed and orig shapes
                meshes = cmds.listRelatives(
                    node, shapes=True, path=True, type="mesh"
                )
                if not len(meshes) > 1:
                    continue

                deformed = meshes[-1]
                original = meshes[0]

                # find deformation source
                inputs = cmds.listConnections(deformed + ".inMesh",
                                              source=True,
                                              destination=False,
                                              plugs=True)
                if not inputs:
                    raise Exception("No mesh input, this should not happen.")

                deformer_in = inputs[0]

                # create colorSet "tensionCS" on original shape
                cmds.polyColorSet(original,
                                  create=True,
                                  clamped=False,
                                  representation="RGBA",
                                  colorSet="tensionCS")

                # create and connect "tensionMap"
                tens_node = cmds.createNode("tensionMap")
                cmds.connectAttr(original + ".worldMesh", tens_node + ".orig")
                cmds.connectAttr(deformer_in, tens_node + ".deform")
                cmds.connectAttr(tens_node + ".out", deformed + ".inMesh",
                                 force=True)

                # caching must set to True or it won't evaluate properly
                cmds.setAttr(original + ".caching", True)

                # save
                tensions.append(tens_node)
                originals.append(original)
                deformeds.append(deformed)
                deformers.append(deformer_in)

                # ensure color exported and suppressed
                display_color = deformed + ".displayColors"
                export_color_ai = deformed + ".aiExportColors"
                attrs = []
                if cmds.getAttr(display_color):
                    cmds.setAttr(display_color, False)
                    attrs.append((display_color, True))
                if not cmds.getAttr(export_color_ai):
                    cmds.setAttr(export_color_ai, True)
                    attrs.append((export_color_ai, False))
                bool_attrs.append(attrs)

            try:
                yield

            finally:
                # teardown
                group = izip(tensions, originals, deformeds, deformers,
                             bool_attrs)

                for tens_node, original, deformed, deformer_in, attrs in group:
                    cmds.connectAttr(deformer_in, deformed + ".inMesh",
                                     force=True)
                    cmds.delete(tens_node)
                    cmds.polyColorSet(original,
                                      delete=True,
                                      colorSet="tensionCS")
                    for attr, value in attrs:
                        cmds.setAttr(attr, value)

        with contextlib.nested(
            capsule.no_undo(),
            tension_context(tension),
        ):
            self.export_alembic(*args, **kwargs)

    def export_alembic(self, root, outpath, start, end, rest_pos, **kwargs):
        from contextlib import contextmanager
        from reveries.maya import capsule
        from maya import cmds

        transforms = root[:]

        @contextmanager
        def rest_pos_context():
            from itertools import izip
            import maya.api.OpenMaya as om2

            fn_colored = []
            vert_ids = []
            color_set = []
            bool_attrs = []

            for node in transforms:
                sel_list = om2.MSelectionList()

                # find deformed and orig shapes
                meshes = cmds.listRelatives(
                    node, shapes=True, path=True, type="mesh"
                )
                if len(meshes) > 1:
                    original = meshes[0]
                    deformed = meshes[-1]

                    sel_list.add(original)
                    sel_list.add(deformed)
                    mobj_origin = sel_list.getDagPath(0).node()
                    mobj_deform = sel_list.getDagPath(1).node()

                    meshFn_origin = om2.MFnMesh(mobj_origin)
                    meshFn_deform = om2.MFnMesh(mobj_deform)

                elif meshes:
                    original = meshes[0]
                    deformed = None

                    sel_list.add(original)
                    mobj_origin = sel_list.getDagPath(0).node()

                    meshFn_origin = om2.MFnMesh(mobj_origin)
                    meshFn_deform = None

                else:
                    # not likely to happen
                    continue

                # create colorSet "restPRef" on original shape
                cmds.polyColorSet(original,
                                  create=True,
                                  clamped=False,
                                  representation="RGBA",
                                  colorSet="restPRef")
                # get point position in object space (local)
                point_pos = []
                vertIter = om2.MItMeshVertex(mobj_origin)
                while not vertIter.isDone():
                    pos = vertIter.position(om2.MSpace.kObject)
                    point_pos.append(pos)
                    vertIter.next()
                # color array
                numVerts = meshFn_origin.numVertices
                vertColors = om2.MColorArray()
                vertColors.setLength(numVerts)
                for i in range(numVerts):
                    pos = point_pos[i]
                    color = om2.MColor()
                    color.setColor([pos.x, pos.y, pos.z, pos.w])
                    vertColors[i] = color
                # vertex id array
                vertIds = om2.MIntArray()
                vertIds.setLength(numVerts)
                for i in range(numVerts):
                    vertIds[i] = i
                # write color to renderable shape
                vert_ids.append(vertIds)
                if meshFn_deform is not None:
                    meshFn_deform.setVertexColors(vertColors, vertIds)
                    fn_colored.append(meshFn_deform)
                    color_set.append((original, deformed))
                else:
                    meshFn_origin.setVertexColors(vertColors, vertIds)
                    fn_colored.append(meshFn_origin)
                    color_set.append((original,))

                # ensure color exported and suppressed
                exp_node = deformed if deformed else original
                display_color = exp_node + ".displayColors"
                export_color_ai = exp_node + ".aiExportColors"
                attrs = []
                if cmds.getAttr(display_color):
                    cmds.setAttr(display_color, False)
                    attrs.append((display_color, True))
                if not cmds.getAttr(export_color_ai):
                    cmds.setAttr(export_color_ai, True)
                    attrs.append((export_color_ai, False))
                bool_attrs.append(attrs)

            try:
                yield

            finally:
                # teardown
                group = izip(fn_colored, vert_ids, color_set, bool_attrs)

                for meshFn, vertIds, nodes, attrs in group:
                    meshFn.removeVertexColors(vertIds)
                    for node in nodes:
                        try:
                            cmds.polyColorSet(node,
                                              delete=True,
                                              colorSet="restPRef")
                        except RuntimeError:
                            pass
                    for attr, value in attrs:
                        cmds.setAttr(attr, value)

        if rest_pos:
            with contextlib.nested(
                capsule.no_undo(),
                rest_pos_context(),
            ):
                kwargs["writeColorSets"] = True
                self._export_alembic(root, outpath, start, end, **kwargs)
        else:
            self._export_alembic(root, outpath, start, end, **kwargs)

    def _export_alembic(self, root, outpath, start, end, **kwargs):
        from reveries.maya import io, lib, capsule
        from maya import cmds

        with contextlib.nested(
            capsule.no_undo(),
            capsule.no_refresh(),
            capsule.evaluation("off"),
            capsule.maintained_selection(),
        ):
            # (monument): We once needed to cleanup leaf name duplicated
            #   nodes with `lib.ls_duplicated_name`, and somehow now we
            #   don't. Just putting notes here in case we bump into
            #   alembic export runtime error again.

            for node in set(root):
                # (NOTE) If a descendent is instanced, it will appear only
                #        once on the list returned.
                root += cmds.listRelatives(node,
                                           allDescendents=True,
                                           fullPath=True,
                                           noIntermediate=True) or []
            root = list(set(root))
            cmds.select(root, replace=True, noExpand=True)

            def _export_alembic():
                io.export_alembic(
                    outpath,
                    start,
                    end,
                    selection=True,
                    renderableOnly=True,
                    writeVisibility=True,
                    writeCreases=True,
                    worldSpace=True,
                    uvWrite=True,
                    writeUVSets=True,
                    attr=[
                        lib.AVALON_ID_ATTR_LONG,
                        "displayColors",
                    ],
                    attrPrefix=[
                        "ai",  # Write out Arnold attributes
                        "avnlook_",  # Write out lookDev controls
                    ],
                    **kwargs
                )

            auto_retry = 1
            while auto_retry:
                try:
                    _export_alembic()
                except RuntimeError as err:
                    if auto_retry:
                        # (NOTE) Auto re-try export
                        # For unknown reason, some artist may encounter
                        # runtime error when exporting but re-run the
                        # publish without any change will resolve.
                        auto_retry -= 1
                        self.log.warning(err)
                        self.log.warning("Retrying...")
                    else:
                        raise err
                else:
                    break
