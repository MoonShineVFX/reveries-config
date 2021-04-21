
import json
import contextlib
import pyblish.api


def read(attr_path):
    from maya import cmds
    try:
        return cmds.getAttr(attr_path)
    except (RuntimeError, ValueError):
        pass


class ExtractLook(pyblish.api.InstancePlugin):
    """Export shaders for rendering

    Shaders are associated with an "mdID" attribute on each *transform* node.
    The extracted file is then given the name of the shader, and thereafter
    a relationship is created between a mesh and a file on disk.

    """

    label = "Extract Look"
    order = pyblish.api.ExtractorOrder
    hosts = ["maya"]
    families = ["reveries.look"]

    def process(self, instance):
        from maya import cmds
        from avalon import maya
        from reveries import utils
        from reveries.maya import lib, capsule, utils as maya_utils

        staging_dir = utils.stage_dir()

        filename = "%s.ma" % instance.data["subset"]
        outpath = "%s/%s" % (staging_dir, filename)

        linkfile = "%s.json" % instance.data["subset"]
        linkpath = "%s/%s" % (staging_dir, linkfile)

        instance.data["repr.LookDev._stage"] = staging_dir
        instance.data["repr.LookDev._files"] = [filename, linkfile]
        instance.data["repr.LookDev.entryFileName"] = filename
        instance.data["repr.LookDev.linkFname"] = linkfile

        by_name = instance.data.get("byNodeName", False)
        _get_id = (maya_utils.get_wildcard_path if by_name
                   else maya_utils.get_id)

        # Serialise shaders relationships
        #
        self.log.info("Serialising shaders.."
                      + ("(by name)" if by_name else ""))

        shader_by_id = lib.serialise_shaders(instance.data["dagMembers"],
                                             by_name=by_name)
        assert shader_by_id, "The map of shader relationship is empty."

        # Extract shaders
        #
        self.log.info("Extracting shaders..")

        child_instances = instance.data.get("childInstances", [])
        try:
            texture = next(chd for chd in child_instances
                           if chd.data["family"] == "reveries.texture")
        except StopIteration:
            file_node_attrs = dict()
        else:
            file_node_attrs = texture.data.get("fileNodeAttrs", dict())

        with contextlib.nested(
            maya.maintained_selection(),
            capsule.ref_edit_unlock(),
            # (NOTE) Ensure attribute unlock
            capsule.attribute_states(file_node_attrs.keys(), lock=False),
            # Change to published path
            capsule.attribute_values(file_node_attrs),
            capsule.no_refresh(),
        ):
            # Select full shading network
            # If only select shadingGroups, and if there are any node
            # connected to Dag node (i.e. drivenKey), then the command
            # will not only export selected shadingGroups' shading network,
            # but also export other related DAG nodes (i.e. full hierarchy)
            cmds.select(instance,
                        replace=True,
                        noExpand=True)

            cmds.file(outpath,
                      options="v=0;",
                      type="mayaAscii",
                      force=True,
                      exportSelected=True,
                      preserveReferences=False,
                      constructionHistory=False,
                      channels=True,  # allow animation
                      constraints=False,
                      shader=True,
                      expressions=True)

        # Animatable attrs
        # Custom attributes in assembly node which require to be animated.
        self.log.info("Serialising 'avnlook_' prefixed attributes..")
        avnlook_anim = dict()
        for node in cmds.ls(instance.data["dagMembers"], type="transform"):
            id = _get_id(node)
            user_attrs = cmds.listAttr(node, userDefined=True) or []
            for attr in user_attrs:
                if not attr.startswith("avnlook_"):
                    continue
                connected = cmds.listConnections(node + "." + attr,
                                                 source=False,
                                                 destination=True,
                                                 plugs=True)
                if connected:
                    avnlook_anim[id + "." + attr] = connected

        surfaces = cmds.ls(instance.data["dagMembers"],
                           noIntermediate=True,
                           type="surfaceShape")

        # UV Chooser
        uv_chooser = dict()
        for chooser in cmds.ls(instance, type="uvChooser"):
            # shading nodes must have id
            chooser_id = maya_utils.get_id(chooser)

            for src in cmds.listConnections(chooser + ".uvSets",
                                            source=True,
                                            destination=False,
                                            plugs=True) or []:
                geo, attr = src.split(".", 1)
                geo = cmds.listRelatives(geo, parent=True, path=True)[0]
                geo_attr = _get_id(geo) + "." + attr

                if chooser_id not in uv_chooser:
                    uv_chooser[chooser_id] = list()
                if geo_attr not in uv_chooser[chooser_id]:
                    uv_chooser[chooser_id].append(geo_attr)

        # CreaseSet
        crease_sets = dict()
        creases = list()

        for node in surfaces:
            creases += cmds.ls(cmds.listSets(object=node), type="creaseSet")

        creases = list(set(creases))

        for cres in creases:
            # Grouping crease set members with crease level value.
            level = cmds.getAttr(cres + ".creaseLevel")
            if level not in crease_sets:
                crease_sets[level] = list()

            for member in cmds.ls(cmds.sets(cres, query=True), long=True):
                node, edges = member.split(".")
                if node not in instance.data["dagMembers"]:
                    continue
                id = _get_id(node)
                crease_sets[level].append(id + "." + edges)

        # Arnold attributes
        arnold_attrs = dict()

        try:
            # (TODO) This should be improved. see issue #65
            from reveries.maya import arnold
        except RuntimeError as e:
            # self.log.debug(e)
            # TODO: error message may cause unicode decode error
            pass
        else:
            ai_sets = dict()
            for objset in cmds.ls(type="objectSet"):
                if not lib.hasAttr(objset, "aiOverride"):
                    continue
                if not cmds.getAttr(objset + ".aiOverride"):
                    continue
                # Ignore pyblish family instance
                if (lib.hasAttr(objset, "id") and
                        read(objset + ".id") == "pyblish.avalon.instance"):
                    continue

                ai_sets[objset] = cmds.ls(cmds.sets(objset, query=True),
                                          long=True)

            # (TODO) Validate only transform nodes in ai set
            transforms = cmds.ls(
                cmds.listRelatives(surfaces, parent=True, path=True),
                long=True,
            )

            for node in transforms:
                id = _get_id(node)

                attrs = dict()

                # Collect all `ai*` attributes from shape
                shape = cmds.listRelatives(node,
                                           shapes=True,
                                           noIntermediate=True,
                                           path=True) or [None]
                shape = shape[0]
                if shape is None:
                    continue

                for attr in cmds.listAttr(shape, fromPlugin=True) or []:
                    value = read(shape + "." + attr)
                    if value is not None:
                        attrs[attr] = value

                # Collect all override attributes from objectSet
                for ai_set, member in ai_sets.items():
                    if node not in member:
                        continue

                    for attr in cmds.listAttr(ai_set, userDefined=True) or []:
                        # Collect all user attributes from objecSet
                        # (NOTE) Some attribute like `castsShadows` does not
                        #        startswith "ai", but also affect rendering in
                        #        Arnold.
                        value = read(ai_set + "." + attr)
                        if value is not None:
                            attrs[attr] = value

                arnold_attrs[id] = attrs

        # VRay Attributes
        vray_attrs = dict()

        try:
            from reveries.maya import vray
        except RuntimeError as e:
            # self.log.debug(e)
            # TODO: error message may cause unicode decode error
            pass
        else:
            for node in surfaces:
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

        relationships = {
            "byNodeName": by_name,
            "shaderById": shader_by_id,
            "avnlookAttrs": avnlook_anim,
            "uvChooser": uv_chooser,
            "creaseSets": crease_sets,
            "arnoldAttrs": arnold_attrs,
            "vrayAttrs": vray_attrs,
        }

        self.log.info("Extracting serialisation..")

        with open(linkpath, "w") as f:
            json.dump(relationships, f)
