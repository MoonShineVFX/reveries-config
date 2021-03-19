import os

import pyblish.api


class ExtractSkeletonCacheExport(pyblish.api.InstancePlugin):
    """Publish parent pointcache usd file.
    """

    order = pyblish.api.ExtractorOrder + 0.4811
    hosts = ["maya"]
    label = "Extract SkeletonCache"
    families = [
        "reveries.skeletoncache",
    ]

    def process(self, instance):
        from reveries import utils

        from reveries.common import get_frame_range
        from reveries.common.build_delay_run import DelayRunBuilder
        from reveries.maya.usd import skelcache_export

        if instance.data.get("isDummy"):
            return

        # Get frame range
        start_frame = instance.data.get("startFrame")
        end_frame = instance.data.get("endFrame")

        if not start_frame or not end_frame:
            shot_name = instance.data["asset"]
            start_frame, end_frame = get_frame_range.get(shot_name)
            instance.data["startFrame"] = start_frame
            instance.data["endFrame"] = end_frame

        staging_dir = utils.stage_dir(dir=instance.data["_sharedStage"])

        # Update information in instance data
        instance.data["repr.USD._stage"] = staging_dir
        instance.data["repr.USD._files"] = [
            skelcache_export.SKELCACHE_SOURCE_NAME,  # r'skelcache_source.usd'
            skelcache_export.SKELCACHE_NAME,         # 'skelecache_data.usd'
            skelcache_export.SKELCACHEPRIM_NAME      # 'skelecache_prim.usda'
        ]
        if self._has_override_mesh(instance):
            instance.data["repr.USD._files"].append(skelcache_export.OVERRIDE_MESHES_NAME)

        instance.data["repr.USD.entryFileName"] = skelcache_export.SKELCACHEPRIM_NAME
        instance.data["_preflighted"] = True

        # Create delay running
        delay_builder = DelayRunBuilder(instance)

        instance.data["repr.USD._delayRun"] = {
            "func": self._export_usd,
            "args": [
                delay_builder.instance_data, delay_builder.context_data
            ],
            "order": 10
        }

    def _has_override_mesh(self, instance):
        import maya.cmds as cmds

        root_node = instance.data["root_node"]
        children = cmds.listRelatives(
            root_node,
            allDescendents=True, type="transform", fullPath=True
        )

        for child_name in children:
            if cmds.attributeQuery('override_mesh', node=child_name, ex=True):
                if cmds.getAttr("{}.override_mesh".format(child_name)):
                    return True
        return False

    def _export_usd(self, instance_data, context_data):
        from reveries.maya.usd import skelcache_export

        # === Export SkeletonCache USD === #
        skelcache_export.export(
            out_dir=instance_data.get("repr.USD._stage"),
            root_node=instance_data.get("root_node"),
            rig_subset_id=instance_data.get("rig_subset_id"),
            frame_range=[
                instance_data.get("startFrame"), instance_data.get("endFrame")],
            shape_merge=True
        )

        self._publish_instance(instance_data, context_data)

    def _publish_instance(self, instance_data, context_data):
        # === Publish instance === #
        from reveries.common.publish import publish_instance

        publish_instance.run(instance_data, context=context_data)
