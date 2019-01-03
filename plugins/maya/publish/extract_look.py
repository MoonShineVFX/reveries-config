
import os
import json
import contextlib

import pyblish.api
import avalon.api

from avalon.maya.pipeline import parse_container
from avalon.pipeline import get_representation_context
from reveries.plugins import PackageExtractor
from reveries.utils import hash_file


class ExtractLook(PackageExtractor):
    """Export shaders for rendering

    Shaders are associated with an "mdID" attribute on each *transform* node.
    The extracted file is then given the name of the shader, and thereafter
    a relationship is created between a mesh and a file on disk.

    """

    label = "Extract Look"
    order = pyblish.api.ExtractorOrder
    hosts = ["maya"]
    families = ["reveries.look"]

    representations = [
        "LookDev"
    ]

    def extract_LookDev(self):

        from maya import cmds
        from avalon import maya
        from reveries.maya import lib, capsule

        entry_file = self.file_name("ma")
        package_path = self.create_package(entry_file)

        version_dir = self.data["version_dir"].replace(
            avalon.api.registered_root(), "$AVALON_PROJECTS"
        )
        self.log.debug("Version Dir: {!r}".format(version_dir))

        # Extract shaders
        #
        entry_path = os.path.join(package_path, entry_file)

        self.log.info("Extracting shaders..")

        with contextlib.nested(
            capsule.no_undo(),
            maya.maintained_selection(),
            capsule.no_refresh(),
        ):
            # Extract Textures
            #
            file_nodes = cmds.ls(self.member, type="file")
            file_hashes = self.data["look_textures"]

            # hash file to check which to copy and which to remain old link
            for node in file_nodes:
                attr_name = node + ".fileTextureName"

                img_path = cmds.getAttr(attr_name,
                                        expandEnvironmentVariables=True)

                hash_value = hash_file(img_path)
                try:
                    final_path = file_hashes[hash_value]
                except KeyError:
                    paths = [
                        version_dir,
                        "textures",
                    ]
                    paths += node.split(":")  # Namespace as fsys hierarchy
                    paths.append(os.path.basename(img_path))  # image name
                    #
                    # Include node name as part of the path should prevent
                    # file name collision which may introduce by two or
                    # more file nodes sourcing from different directory
                    # with same file name but different file content.
                    #
                    # For example:
                    #   File_A.fileTextureName = "asset/a/texture.png"
                    #   File_B.fileTextureName = "asset/b/texture.png"
                    #
                    final_path = os.path.join(*paths)

                    file_hashes[hash_value] = final_path
                    self.data["auxiliaries"].append((img_path, final_path))

                # Set texture file path to publish location
                cmds.setAttr(attr_name, final_path, type="string")
                self.log.debug("Texture Path: {!r}".format(final_path))

            # Select full shading network
            # If only select shadingGroups, and if there are any node
            # connected to Dag node (i.e. drivenKey), then the command
            # will not only export selected shadingGroups' shading network,
            # but also export other related DAG nodes (i.e. full hierarchy)
            cmds.select(self.member,
                        replace=True,
                        noExpand=True)

            cmds.file(entry_path,
                      options="v=0;",
                      type="mayaAscii",
                      force=True,
                      exportSelected=True,
                      preserveReferences=False,
                      constructionHistory=False)

        # Serialise shaders relationships
        #
        link_file = self.file_name("json")
        link_path = os.path.join(package_path, link_file)

        self.log.info("Serialising shaders..")

        shader_by_id = lib.serialise_shaders(self.data["dag_members"])

        # Animatable attrs
        # Custom attributes in assembly node which require to be animated.
        self.log.info("Serialising animatable attributes..")
        animatable = dict()
        root = cmds.ls(self.data["dag_members"], assemblies=True)
        if root:
            root = root[0]
            for attr in cmds.listAttr(root, userDefined=True) or list():
                animatable[attr] = cmds.listConnections(root + "." + attr,
                                                        destination=True,
                                                        source=False,
                                                        plugs=True)

        meshes = cmds.ls(self.data["dag_members"],
                         visible=True,
                         noIntermediate=True,
                         type="mesh")

        # CreaseSet
        crease_sets = dict()
        creases = list()

        for node in meshes:
            creases += cmds.ls(cmds.listSets(object=node), type="creaseSet")

        creases = list(set(creases))

        for cres in creases:
            level = cmds.getAttr("creaseLevel")
            if level not in crease_sets:
                crease_sets[level] = list()
            crease_sets[level] += cmds.sets(cres, query=True)

        # VRay Attributes
        vray_attrs = dict()

        try:
            from reveries.maya import vray
        except RuntimeError as e:
            self.log.debug(e)
        else:
            for node in meshes:
                # - shape
                values = vray.attributes_gather(node)
                if values:
                    vray_attrs[node] = values

                # - transfrom
                parent = cmds.listRelatives(node, parent=True)
                if parent:
                    values = vray.attributes_gather(parent[0])
                    if values:
                        vray_attrs[parent[0]] = values

        # Get model subset id
        container_name = self.data["paired_container"][0]
        model_container = parse_container(container_name)
        representation_id = model_container["representation"]
        context = get_representation_context(representation_id)
        target_subset = str(context["subset"]["_id"])

        relationships = {
            "shader_by_id": shader_by_id,
            "animatable": animatable,
            "crease_sets": crease_sets,
            "vray_attrs": vray_attrs,
        }

        self.log.info("Extracting serialisation..")
        with open(link_path, "w") as f:
            json.dump(relationships, f, indent=4)

        self.add_data({
            "link_fname": link_file,
            "textures": self.data["look_textures"],
            "target_subset": target_subset,
        })

        self.log.info("Extracted {name} to {path}".format(
            name=self.data["subset"],
            path=package_path)
        )
