
import avalon.api


class UnpackLoadedSubset(avalon.api.InventoryAction):
    """Unpack loaded subset into scene
    """

    label = "Unpack Subset"
    icon = "warning"
    color = "#ff6666"
    order = 200

    @staticmethod
    def is_compatible(container):
        from maya import cmds
        from avalon.maya.pipeline import AVALON_CONTAINERS

        if not container:
            return False

        if container["loader"] not in [
            "CameraLoader",
            "LightSetLoader",
            "LookLoader",
            "MayaShareLoader",
            "ModelLoader",
            "PointCacheReferenceLoader",
            "RigLoader",
            "SetDressLoader",
            "XGenInteractiveLoader",
        ]:
            return False

        containers = AVALON_CONTAINERS[1:]  # Remove root namespace
        parents = cmds.listSets(object=container["objectName"]) or []
        # Must be a root container
        if containers in parents:
            return True
        return False

    def consent(self):
        from reveries.plugins import message_box_warning

        title = "Unpack Subset"
        msg = ("Subset will not be able to update nor managed after "
               "this action.\nAre you sure ?")

        return message_box_warning(title, msg, optional=True)

    def process(self, containers):
        from maya import cmds
        from avalon.maya.pipeline import AVALON_CONTAINERS
        from avalon.tools import sceneinventory
        from reveries.maya import hierarchy, pipeline, lib, capsule
        from reveries.maya.vendor import sticker
        from reveries import REVERIES_ICONS

        if not self.consent():
            return

        dimmed_icon = REVERIES_ICONS + "/package-01-dimmed.png"

        # Copy Look's textures first
        try:
            with capsule.undo_chunk(undo_on_exit=False):
                for container in containers:
                    if container["loader"] == "LookLoader":
                        self.unpack_textures(container)
        except Exception as e:
            cmds.undo()
            raise e

        # Unpack
        for container in containers:
            if not self.is_compatible(container):
                continue

            node = container["objectName"]
            members = cmds.sets(node, query=True) or []

            reference_node = lib.get_highest_reference_node(members)
            if reference_node is not None:
                # Import Reference
                cmds.file(importReference=True, referenceNode=reference_node)

            namespace = container["namespace"]

            for child in hierarchy.get_sub_container_nodes(container):
                # Update sub-containers' namespace entry
                child_ns = cmds.getAttr(child + ".namespace")
                new_ns = child_ns[len(namespace):]
                cmds.setAttr(child + ".namespace", new_ns, type="string")
                # Add to root container
                cmds.sets(child, forceElement=AVALON_CONTAINERS)

            # Merge namespace to root
            cmds.namespace(removeNamespace=namespace,
                           mergeNamespaceWithRoot=True)

            # Update subset group icon
            group = pipeline.get_group_from_container(node)
            if group is not None:
                sticker.put(group, dimmed_icon)

            # Delete container
            cmds.delete(node)

        # Refresh GUI
        sceneinventory.app.window.refresh()

        # Update Icon
        sticker.reveal()

    def unpack_textures(self, container):
        import os
        import shutil
        from maya import cmds, mel
        from avalon import api, io

        project = io.find_one({"type": "project"},
                              projection={"name": True,
                                          "config.template.publish": True})
        asset = io.find_one({"_id": io.ObjectId(container["assetId"])},
                            projection={"name": True, "silo": True})
        subset = io.find_one({"_id": io.ObjectId(container["subsetId"])},
                             projection={"name": True})
        version = io.find_one({"_id": io.ObjectId(container["versionId"])},
                              projection={"name": True,
                                          "data.dependencies": True})
        # Find TexturePack
        id = next(iter(version["data"]["dependencies"]))
        dep_version = io.find_one({"_id": io.ObjectId(id)})
        dep_subset = io.find_one({"_id": dep_version["parent"]})
        dep_representation = io.find_one({"parent": dep_version["_id"],
                                          "name": "TexturePack"})

        if "fileInventory" not in dep_representation["data"]:
            self.copy_old_textures(container, asset, subset, version)
            return

        # List texture versions
        published = dict()
        template_publish = project["config"]["template"]["publish"]
        for data in dep_representation["data"]["fileInventory"]:
            path = template_publish.format(
                root=api.registered_root(),
                project=project["name"],
                silo=asset["silo"],
                asset=asset["name"],
                subset=dep_subset["name"],
                version=data["version"],
                representation="TexturePack",
            )
            published[data["version"]] = path

        # Collect path,
        # filter out textures that is being used in this look
        file_nodes = cmds.ls(cmds.sets(container["objectName"], query=True),
                             type="file")
        files = dict()
        for node in file_nodes:
            path = cmds.getAttr(node + ".fileTextureName",
                                expandEnvironmentVariables=True)
            if not os.path.isfile(path):
                continue

            for v, p in published.items():
                if path.startswith(p):
                    key = (v, p)
                    if key not in files:
                        files[key] = list()
                    files[key].append(node)
                    break

        # Copy textures and change path
        root = cmds.workspace(query=True, rootDirectory=True)
        root += mel.eval('workspace -query -fileRuleEntry "sourceImages"')
        root += "/_unpacked"

        pattern = "/{asset}/{subset}.v{version:0>3}/TexturePack.v{texture:0>3}"
        for (texture_version, src), nodes in files.items():
            dst = root + pattern.format(asset=asset["name"],
                                        subset=subset["name"],
                                        version=version["name"],
                                        texture=texture_version)
            for node in nodes:
                attr = node + ".fileTextureName"
                path = cmds.getAttr(attr, expandEnvironmentVariables=True)
                tail = path.split("TexturePack")[-1]
                cmds.setAttr(attr, dst + tail, type="string")

            if os.path.isdir(dst):
                continue

            shutil.copytree(src, dst)

    def copy_old_textures(self, container, asset, subset, version):
        import os
        import shutil
        from maya import cmds, mel
        from reveries.maya.utils import fix_texture_file_nodes

        files = dict()
        file_nodes = cmds.ls(cmds.sets(container["objectName"], query=True),
                             type="file")
        for node in file_nodes:
            path = cmds.getAttr(node + ".fileTextureName",
                                expandEnvironmentVariables=True)
            if not os.path.isfile(path):
                continue

            if path not in files:
                files[path] = list()
            files[path].append(node)

        # Copy textures and change path
        root = cmds.workspace(query=True, rootDirectory=True)
        root += mel.eval('workspace -query -fileRuleEntry "sourceImages"')
        root += "/_unpacked"

        pattern = "/{asset}/{subset}.v{version:0>3}"
        subdirs = pattern.format(asset=asset["name"],
                                 subset=subset["name"],
                                 version=version["name"])
        root += subdirs

        if not os.path.isdir(root):
            os.makedirs(root)

        copied = set()
        for path, nodes in files.items():
            src = path
            fname = os.path.basename(src)
            dst = os.path.join(root, fname)

            if fname in copied:
                # ignore same named file
                pass
            else:
                shutil.copy2(src, dst)
                copied.add(fname)

            fix_texture_file_nodes(nodes, file_path=dst)
