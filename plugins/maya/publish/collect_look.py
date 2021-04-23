
import pyblish.api


def create_texture_subset_from_look(instance, textures, use_txmaps):
    """
    """
    from reveries import plugins

    family = "reveries.texture"
    subset = instance.data["subset"]
    subset = "texture" + subset[0].upper() + subset[1:]
    data = {
        "useTxMaps": use_txmaps,
    }

    plugins.create_dependency_instance(instance,
                                       subset,
                                       family,
                                       textures,
                                       data=data)


class CollectLook(pyblish.api.InstancePlugin):
    """Collect mesh's shading network and objectSets
    """

    order = pyblish.api.CollectorOrder + 0.2
    hosts = ["maya"]
    label = "Collect Look"
    families = ["reveries.look"]

    def process(self, instance):
        from maya import cmds
        from reveries.maya import pipeline, utils

        surfaces = cmds.ls(instance,
                           noIntermediate=True,
                           type="surfaceShape")

        # Require TensionMap plugin
        tensioned_shadings = []
        data_nodes = {
            "aiUserDataVector": (".vectorAttrName", ".outValue"),
            "aiUserDataColor": (".colorAttrName", ".outColor"),
        }
        for node_type, (attr_in, attr_out) in data_nodes.items():
            tension_plugs = filter(
                lambda n: cmds.getAttr(n + attr_in) == "tensionCS",
                cmds.ls(type=node_type)
            )
            if tension_plugs:
                self.log.info("Tension colorSet request found.")
                tensioned_shadings += cmds.ls(
                    cmds.listHistory(
                        [p + attr_out for p in tension_plugs],
                        future=True,
                        pruneDagObjects=True,
                        breadthFirst=True
                    ),
                    type="shadingEngine"
                )
        if tensioned_shadings:
            self.log.info("Collecting tensionMap required meshes.")
            tensioned_meshes = cmds.ls(
                cmds.sets(tensioned_shadings, query=True, nodesOnly=True),
                visible=True,
                intermediateObjects=False,
            )
            instance.data["requireTensionMap"] = cmds.listRelatives(
                tensioned_meshes, parent=True, path=True) or []

        # Require Avalon UUID
        instance.data["requireAvalonUUID"] = cmds.listRelatives(surfaces,
                                                                parent=True,
                                                                fullPath=True)

        instance.data["dagMembers"] = instance[:]
        instance[:] = instance.data.pop("shadingNetwork", [])

        stray = pipeline.find_stray_textures(instance)
        if stray:
            is_arnold = utils.get_renderer_by_layer() == "arnold"
            create_texture_subset_from_look(instance, stray, is_arnold)
