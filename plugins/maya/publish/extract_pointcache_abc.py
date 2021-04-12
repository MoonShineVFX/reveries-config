
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
        root = instance.data["outCache"]

        if tension:
            instance.data["repr.Alembic._delayRun"] = {
                "func": self.export_alembic_with_tension,
                "args": [
                    tension,
                    [root, outpath, start, end],
                    {"eulerFilter": euler_filter, "writeColorSets": True}
                ],
            }
        else:
            instance.data["repr.Alembic._delayRun"] = {
                "func": self.export_alembic,
                "args": [root, tension, outpath, start, end],
                "kwargs": {"eulerFilter": euler_filter}
            }

    def export_alembic_with_tension(self, tension, args, kwargs):
        from maya import cmds
        from itertools import izip
        from contextlib import contextmanager

        cmds.loadPlugin("TensionMap", quiet=True)

        @contextmanager
        def tension_context(transforms):
            tensions = []
            originals = []
            deformeds = []
            deformers = []

            for node in transforms:
                # find deformed and orig shapes
                meshes = cmds.ls(
                    cmds.listHistory(node, future=False, breadthFirst=True),
                    type="mesh"
                )
                if not len(meshes) > 1:
                    continue

                deformed = meshes[0]
                original = meshes[-1]

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

            try:
                yield

            finally:
                # teardown
                group = izip(tensions, originals, deformeds, deformers)

                for tens_node, original, deformed, deformer_in in group:
                    cmds.connectAttr(deformer_in, deformed + ".inMesh",
                                     force=True)
                    cmds.delete(tens_node)
                    cmds.polyColorSet(original,
                                      delete=True,
                                      colorSet="tensionCS")

        with tension_context(tension):
            self.export_alembic(*args, **kwargs)

    def export_alembic(self, root, outpath, start, end, **kwargs):
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
