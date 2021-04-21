import pyblish.api


class CollectSkeletonCacheOutputs(pyblish.api.InstancePlugin):
    """
    Get skeletoncache instance from set group.
    """

    order = pyblish.api.CollectorOrder - 0.2999
    label = "Collect SkeletonCache Outputs"
    hosts = ["maya"]
    families = [
        "reveries.skeletoncache",
    ]

    def process(self, instance):
        import maya.cmds as cmds
        from reveries.maya import lib, pipeline
        from reveries.common.task_check import task_check

        get = (lambda f: cmds.playbackOptions(query=True, **f))
        start_frame = get({"minTime": True})
        end_frame = get({"maxTime": True})

        created = False
        context = instance.context
        backup = instance

        # Get set member
        source_subset_name = backup.data["subset"]
        top_nodes = cmds.sets(source_subset_name, query=True)
        _post = backup.data["subset"][len("skeletoncache"):]  # Default

        for top_node in top_nodes:
            namespace = lib.get_ns(top_node)[1:]

            # Get rig root node
            root_node = "{}:ROOT".format(namespace)
            if not cmds.objExists(root_node):
                continue

            # Get rig container
            try:
                container = pipeline.get_container_from_namespace(namespace)
            except AssertionError:
                continue
            rig_subset_id = cmds.getAttr("{}.subsetId".format(container))

            # Create instance
            created = True
            _instance = context.create_instance(namespace + "." + _post)
            _instance.data.update(backup.data)

            _instance[:] = [root_node]
            _instance.data["subset"] = ".".join(["skeletoncache", namespace, _post])
            _instance.data["startFrame"] = start_frame
            _instance.data["endFrame"] = end_frame
            _instance.data["rig_subset_id"] = rig_subset_id
            _instance.data["root_node"] = root_node

            # Check task
            if task_check(task_name="animating"):
                _instance.data["subsetGroup"] = "Animation"

        if not created:
            self.log.warning("No skeletoncache instance created.")
        else:
            context.remove(backup)
