
import os
import uuid
import hashlib
import contextlib
import logging
from collections import OrderedDict

try:
    import bson
except ImportError:
    pass

from avalon import api, io
from avalon.maya.pipeline import AVALON_CONTAINERS

import avalon_sftpc

from maya import cmds, mel
from maya.api import OpenMaya as om

from .. import lib as reveries_lib
from ..vendor import six
from ..utils import _C4Hasher, get_representation_path_
from .pipeline import (
    find_stray_textures,
    env_embedded_path,
    get_container_from_namespace,
    AVALON_GROUP_ATTR,
)
from . import lib, capsule


log = logging.getLogger(__name__)


def texture_path_expand(nodes=lib._no_val):
    """Expand file nodes' file path that has environment variable embedded

    Args:
        nodes (list, optional): List of nodes, process all nodes if not
                                provided.

    """
    args = (nodes, ) if nodes is not lib._no_val else ()

    for node in cmds.ls(*args, type="file"):
        attr = node + ".fileTextureName"
        path = cmds.getAttr(attr, expandEnvironmentVariables=True)
        cmds.setAttr(attr, path, type="string")


def texture_path_embed(nodes=lib._no_val):
    """Embed environment variables into file nodes' file path

    Environment variables that will be embedded:
        * AVALON_PROJECTS
        * AVALON_PROJECT

    Args:
        nodes (list, optional): List of nodes, process all nodes if not
                                provided.

    """
    args = (nodes, ) if nodes is not lib._no_val else ()

    for node in cmds.ls(*args, type="file"):
        attr = node + ".fileTextureName"
        path = cmds.getAttr(attr, expandEnvironmentVariables=True)
        embedded_path = env_embedded_path(path)

        if not embedded_path == path:
            try:
                cmds.setAttr(attr, embedded_path, type="string")
            except RuntimeError:
                print(attr)
                print(path)
                print(embedded_path)


def remap_to_published_texture(nodes, representation_id, dry_run=False):
    """For fixing previous bad implementations on texture management

    This is for remapping texture file path from arbitrarily work path
    to previous published path in published looks.

    For some reason, some texture path may not changed to published path
    after extraction. This is a fixing helper for the issue.

    (NOTE) The issue should be resolved in following commits. :')

    """
    file_nodes = cmds.ls(nodes, type="file")
    count, file_data = lib.profiling_file_nodes(file_nodes)
    if not count:
        return

    node_by_fpattern = dict()

    for data in file_data:
        data["pathMap"] = {
            fn: data["dir"] + "/" + fn for fn in data["fnames"]
        }

        fpattern = data["fpattern"]
        if fpattern not in node_by_fpattern:
            node_by_fpattern[fpattern] = list()
        node_by_fpattern[fpattern].append(data)

    repr = io.find_one({"_id": io.ObjectId(representation_id)})
    file_inventory = repr["data"].get("fileInventory")
    if not file_inventory:
        return

    resolved_by_fpattern = lib.resolve_file_profile(repr, file_inventory)

    # MAPPING

    for fpattern, file_datas in node_by_fpattern.items():
        if fpattern not in resolved_by_fpattern:
            fpattern_ = fpattern.rsplit(".", 1)[0]
            for resolved_fpattern in resolved_by_fpattern:
                if fpattern_ == resolved_fpattern.rsplit(".", 1)[0]:
                    versioned_data = resolved_by_fpattern[resolved_fpattern]
                    break
            else:
                continue
        else:
            versioned_data = resolved_by_fpattern[fpattern]

        data = file_datas[0]
        file_nodes = [dat["node"] for dat in file_datas]
        versioned_data.sort(key=lambda elem: elem[0]["version"],
                            reverse=True)  # elem: (data, tmp_data)

        for ver_data, resolved in versioned_data:

            previous_files = resolved["pathMap"]

            for file, abs_path in data["pathMap"].items():
                if file not in previous_files:
                    file = file.rsplit(".", 1)[0]
                    for pre_file in previous_files:
                        if file == pre_file.rsplit(".", 1)[0]:
                            file = pre_file
                            abs_previous = previous_files[pre_file]
                            ext = pre_file.rsplit(".", 1)[1]
                            abs_path = abs_path.rsplit(".", 1)[0] + "." + ext
                            if not os.path.isfile(abs_path):
                                continue
                            else:
                                break
                    else:
                        # Possible different file pattern
                        break  # Try previous version
                else:
                    abs_previous = previous_files[file]

                if not os.path.isfile(abs_previous):
                    # Previous file not exists (should not happen)
                    break  # Try previous version

                # (NOTE) We don't need to check on file size and modification
                #        time here since we are trying to map file to latest
                #        version of published one.

            else:
                # Version matched, consider as same file
                head_file = sorted(previous_files)[0]
                resolved_path = abs_previous[:-len(file)] + head_file
                embedded_path = env_embedded_path(resolved_path)
                fix_texture_file_nodes(file_nodes, embedded_path, dry_run)

                # Proceed to next pattern
                break

        else:
            # Not match with any previous version, this should not happen
            log.warning("No version matched.")
            with open(dry_run, "a") as path_log:
                path_log.write("\n * " + data["dir"] + "/" + fpattern + "\n\n")


def fix_texture_file_nodes(nodes=lib._no_val, file_path=None, dry_run=False):
    """For fixing previous bad implementations on texture management
    """
    args = (nodes, ) if nodes is not lib._no_val else ()

    with capsule.ref_edit_unlock():
        # This context is for unlocking colorSpace
        for node in cmds.ls(*args, type="file"):
            if cmds.getAttr(node + ".colorSpace", lock=True):
                cmds.setAttr(node + ".colorSpace", lock=False)

            if not cmds.getAttr(node + ".ignoreColorSpaceFileRules"):
                cmds.setAttr(node + ".ignoreColorSpaceFileRules", True)

            # Resolve TX map update issues
            if (lib.hasAttr(node, "aiAutoTx") and
                    cmds.getAttr(node + ".aiAutoTx")):
                cmds.setAttr(node + ".aiAutoTx", False)

            if file_path:
                if dry_run:
                    origin = cmds.getAttr(node + ".fileTextureName")

                    if isinstance(dry_run, six.string_types):
                        with open(dry_run, "a") as path_log:
                            path_log.write(" : " + origin + "\n")
                            path_log.write(">: " + file_path + "\n\n")
                    else:
                        log.info(" : " + origin)
                        log.info(">: " + file_path)
                else:
                    cmds.setAttr(node + ".fileTextureName",
                                 file_path,
                                 type="string")
            else:
                # Fix env var embed texture path
                # For after solving Avalon Launcher root `realpath` *bug*
                bug = "$AVALON_PROJECTS$AVALON_PROJECT"
                fix = "$AVALON_PROJECTS/$AVALON_PROJECT"
                attr = node + ".fileTextureName"
                path = cmds.getAttr(attr)

                if path.startswith(bug):
                    path = path.replace(bug, fix)
                    has_bug = True
                else:
                    has_bug = False

                if lib.is_versioned_texture_path(path):
                    new_path = env_embedded_path(path)
                else:
                    new_path = os.path.expandvars(path)

                if has_bug or new_path != path:
                    cmds.setAttr(attr, new_path, type="string")


# TODO: Objectize texture file data
#       implement __eq__ to compare files


def _hash_MPoint(x, y, z, w):
    x = (x + 1) * 233
    y = (y + x) * 239
    z = (z + y) * 241
    return (x + y + z) * w


def _hash_MFloatVectors(x, y, z):
    x = (x + 1) * 383
    y = (y + x) * 389
    z = (z + y) * 397
    return x + y + z


def _hash_UV(u, v):
    u = (u + 1) * 547
    v = (v + u) * 557
    return u * v


class MeshHasher(object):
    """A mesh geometry hasher for Maya

    For quickly identifying if any change on vertices, normals and UVs.
    Hash value will be encoded as Avalanche-io C4 Asset ID.

    Order matters, transform does not.

    Example Usage:
        >> hasher = MeshHasher()
        >> hasher.set_mesh("path|to|mesh")
        >> hasher.update_points()
        >> hasher.update_normals()
        >> hasher.update_uvmap()
        >> hasher.digest()
        {'normals': 'c41MSCnAGqWS9dBDDpydbpcMwzzFkGH66jNpuTqctfY...',
         'points': 'c44fV5wa6bNiekUadZ4HsRPDL2HZ11RFKcXhf3pntsUJ...',
         'uvmap': 'c45JRQTPxgMNYfcijAbm31vkJRt6CUUSn7ew2X1Mnyjwi...'}

        Hash meshes in loop
        >> for mesh in cmds.ls(type="mesh", ni=Ture, long=True)
        ...    hasher.set_mesh(mesh)
        ...    hasher.update_points()
        ...    hasher.update_normals()
        ...
        >> hasher.digest()
        {'normals': 'c456rBNH5pzobqjHzFnHApanrTdJo64r2R8o4GJxqU9G...',
         'points': 'c449wXhjNSSKfnUjPp2ub3fd1DeNowW2x5gBJDYrSvxrT...'}

        You can still adding more meshes until you call `clear`
        >> hasher.clear()

    """

    def __init__(self):
        self.clear()

    def clear(self):
        self._mesh = None
        self._points = 0
        self._normals = 0
        self._uvmap = 0

    def set_mesh(self, dag_path):
        """Set one mesh geometry node to hasher

        Arguments:
            dag_path (str): Mesh node's DAG path

        """
        sel_list = om.MSelectionList()
        sel_list.add(dag_path)
        sel_obj = sel_list.getDagPath(0)
        self._mesh = om.MFnMesh(sel_obj)

    def update_points(self):
        for i, vt in enumerate(self._mesh.getPoints()):
            self._points += _hash_MPoint(*vt) + i

    def update_normals(self):
        for i, vt in enumerate(self._mesh.getNormals()):
            self._normals += _hash_MFloatVectors(*vt) + i

    def update_uvmap(self, uv_set=""):
        for i, uv in enumerate(zip(*self._mesh.getUVs(uv_set))):
            self._uvmap += _hash_UV(*uv) + i

    def digest(self):
        result = dict()
        hasher = _C4Hasher()

        if self._points:
            hasher.hash_obj.update(str(self._points))
            result["points"] = hasher.digest()
            hasher.clear()

        if self._normals:
            hasher.hash_obj.update(str(self._normals))
            result["normals"] = hasher.digest()
            hasher.clear()

        if self._uvmap:
            hasher.hash_obj.update(str(self._uvmap))
            result["uvmap"] = hasher.digest()
            hasher.clear()

        return result


def remove_unused_plugins():
    """Remove unused plugin from scene

    This will prevent Maya from saving redundant requires into scene file.

    (Copied from Maya support page)
    Maya is not cleaning up requires statements for unused plugins:

    Issue:
        When a plugin is used in Maya 2016, it puts a 'requires' statement
        into the header of the Maya File, akin to: requires "XZY" "1.30"
        When the plugin is subsequently deleted out of the Maya file and
        the Maya file is saved, the requires statement is left in the file.

    Causes:
        It creates extra lines of garbage code which makes the file larger
        and more clutter when files are being diagnosed

    Solution:
        Autodesk introduced one new command unknownPlugin which could be used
        to remove the "requires" line from the file if the plug-in is unknown
        to Maya 2016.

    """
    for plugin in cmds.unknownPlugin(query=True, list=True) or []:
        cmds.unknownPlugin(plugin, remove=True)


def kill_turtle():
    """Ensure the Turtle plugin is not loaded"""

    turtle_nodes = (
        "TurtleDefaultBakeLayer",
        "TurtleBakeLayerManager",
        "TurtleUIOptions",
        "TurtleRenderOptions",
    )

    for node in turtle_nodes:
        if not cmds.objExists(node):
            continue
        cmds.lockNode(node, lock=False)
        cmds.delete(node)

    cmds.unloadPlugin("Turtle", force=True)


def _get_attr(node, attr):
    """Internal function for attribute getting
    """
    if lib.hasAttrExact(node, attr):
        return cmds.getAttr(node + "." + attr)
    else:
        return None


def _add_attr(node, attr):
    """Internal function for attribute adding
    """
    if not lib.hasAttrExact(node, attr):
        cmds.addAttr(node, longName=attr, dataType="string")


def _set_attr(node, attr, value):
    """Internal function for attribute setting
    """
    try:
        cmds.setAttr(node + "." + attr, value, type="string")
    except RuntimeError:
        # Attribute not existed
        pass


class Identifier(object):

    Clean = 0
    Duplicated = 1
    Untracked = 2

    ATTR_ADDRESS = lib.AVALON_ID_ATTR_LONG
    ATTR_VERIFIER = "verifier"

    ID_SEP = ":"
    _NS = ""

    def register_namespace(self, namespace):
        """Setup Avalon UUID namespace

        The namespace will be used or applied in the follow up Avalon UUID
        read/write actions.

        Arguments:
            namespace (str): Avalon UUID namespace

        """
        if not isinstance(namespace, six.string_types):
            raise TypeError("ID namespace must be string.")
        self._NS = namespace + (self.ID_SEP if namespace else "")

    def registered_namespace(self):
        """Return current Avalon UUID namespace setup
        """
        return self._NS[:-len(self.ID_SEP)]

    def read_full_address(self, node):
        """Read Avalon UUID namespace + address value from node

        Arguments:
            node (str): Maya node name

        """
        return _get_attr(node, self.ATTR_ADDRESS)

    def read_namespace(self, node):
        """Read Avalon UUID namespace from node

        Arguments:
            node (str): Maya node name

        """
        full_address = self.read_full_address(node) or ""
        if self.ID_SEP in full_address:
            return full_address.split(self.ID_SEP)[0]
        else:
            return None

    def read_address(self, node):
        """Read address value from node

        Arguments:
            node (str): Maya node name

        """
        try:
            return self.read_full_address(node).split(self.ID_SEP)[-1]
        except AttributeError:
            # full_address is None, 'NoneType' object has no attribute 'split'
            return None

    def read_verifier(self, node):
        """Read verifier value from node

        Arguments:
            node (str): Maya node name

        """
        return _get_attr(node, self.ATTR_VERIFIER)

    def read_uuid(self, node):
        """Read uuid value from node

        Arguments:
            node (str): Maya node name

        """
        muuid = cmds.ls(node, uuid=True)
        if not len(muuid):
            raise RuntimeError("Node not found.")
        elif len(muuid) > 1:
            raise RuntimeError("Found more then one node, use long name.")

        return muuid[0]

    def _generate_address(self):
        """Internal function for generating time-embedded ID address

        Note:
            `bson.ObjectId` is about 1 time faster then `uuid.uuid1`.

        """
        try:
            return str(bson.ObjectId())  # bson is faster
        except NameError:
            return str(uuid.uuid1())[:-18]  # remove mac-addr

    def _generate_verifier(self, muuid, address):
        """Internal function for generating hash value from Maya UUID and address

        Arguments:
            muuid (str): Maya UUID string
            address (str): Previous generated address id from node

        Note:
            Faster then uuid5.

        """
        hasher = hashlib.sha1()
        hasher.update(muuid + ":" + address)
        return hasher.hexdigest()

    def status(self, node):
        """Report `node` current state

        Return node state flag (int), in range 0 - 3:
            0 == Identifier.Clean
            1 == Identifier.Duplicated
            2 == Identifier.Untracked

        Arguments:
            node (str): Maya node name

        Returns:
            (int): Node state flag

        """
        address = self.read_address(node)
        verifier = self.read_verifier(node)

        if not all((address, verifier)):
            # Node did not have the attributes for verification,
            # this is new node.
            return self.Untracked
        else:
            if verifier == self._generate_verifier(self.read_uuid(node),
                                                   address):
                return self.Clean
            else:
                return self.Duplicated

    def on_track(self, node, address=None):
        """Update node's address

        MUST do this if `status` return flag `api.Untracked`.

        Arguments:
            node (str): Maya node name
            address (str, optional): Previous generated address id from node.
                New address id will be generated if not provid one.

        """
        address = address or self._generate_address()
        _add_attr(node, self.ATTR_ADDRESS)
        _set_attr(node, self.ATTR_ADDRESS, self._NS + address)
        self.on_duplicate(node)  # Update verifier

    def on_duplicate(self, node):
        """Update node's verifier

        MUST do this if `status` return flag `api.Duplicated`.

        Arguments:
            node (str): Maya node name
            fingerprint (str): Maya node's hash value

        """
        address = self.read_address(node)
        if address is None:
            return

        verifier = self._generate_verifier(self.read_uuid(node), address)
        _add_attr(node, self.ATTR_VERIFIER)
        _set_attr(node, self.ATTR_VERIFIER, verifier)

    __action_map = {
        Clean: (lambda self, n: None),
        Duplicated: on_track,
        Untracked: on_track,
    }

    def manage(self, node, state):
        """Auto update node's identity attributes by input state

        Arguments:
            node (str): Maya node name
            state (int): State flag returned from `status`

        """
        action = self.__action_map[state]
        action(self, node)

    def update_verifiers(self, nodes):
        """Update input nodes' verifier

        MUST do this on file-import.

        Arguments:
            nodes (list): A list of Maya node name

        """
        for node in nodes:
            self.on_duplicate(node)

    def update_namespace(self, nodes):
        """Update input nodes' UUID namespace

        Remember to use `register_namespace` method to setup the namespace
        you want to apply.

        Arguments:
            nodes (list): A list of Maya node name

        """
        for node in nodes:
            address = self.read_address(node)
            if address is None:
                continue
            _set_attr(node, self.ATTR_ADDRESS, self._NS + address)

    def get_time(self, node):
        """Retrive datetime object from Maya node

        A little bonus gained from datetime embedded id.

        Arguments:
            node (str): Maya node name

        """
        address = self.read_address(node)
        if address is None:
            return None
        return reveries_lib.avalon_id_timestamp(address)


_identifier = Identifier()


@contextlib.contextmanager
def id_namespace(namespace, manager=None):
    """Avalon UUID namespace context
    """
    manager = manager or _identifier

    original_ns = manager.registered_namespace()
    manager.register_namespace(namespace)
    try:
        yield
    finally:
        manager.register_namespace(original_ns)


def upsert_id(node, id=None, namespace_only=False):
    """Add or renew avID ( Avalon ID ) to `node`
    """
    if id is None and not namespace_only:
        # Add or renew id based on id status
        status = _identifier.status(node)
        _identifier.manage(node, status)
    else:
        if namespace_only:
            id = _identifier.read_address(node)
        # Set id
        _identifier.on_track(node, id)


def get_id_namespace(node):
    """
    Get AvalonID namespace of the given node

    Args:
        node (str): the name of the node to retrieve the value from

    """
    return _identifier.read_namespace(node)


def get_id(node):
    """
    Get the `AvalonID` attribute of the given node
    Args:
        node (str): the name of the node to retrieve the attribute from

    Returns:
        str

    """
    return _identifier.read_address(node)


def get_id_status(node):
    return _identifier.status(node)


def _get_full_address(node):
    # AvalonID may have imprinted on shape node if it's coming
    # from alembic which published by Houdini.
    attr_name = "%s." + lib.AVALON_ID_ATTR_LONG
    full_address = ""
    shapes = cmds.listRelatives(node,
                                path=True,
                                shapes=True,
                                noIntermediate=True) or []
    if len(shapes) > 1:
        for n in shapes + [node]:
            try:
                full_address = cmds.getAttr(attr_name % n)
            except ValueError:
                pass
            else:
                break
    else:
        try:
            full_address = cmds.getAttr(attr_name % node)
        except ValueError:
            pass

    if isinstance(full_address, list):
        # Shouldn't be stringArray type, this is human bug
        full_address = full_address[0]

    return full_address


def get_id_loosely(node):
    id = get_id(node)

    if id is None:
        full_address = _get_full_address(node)
        id = full_address.split(":")[-1]

    return id


def get_id_namespace_loosely(node):
    id_namespace_ = get_id_namespace(node)

    if id_namespace_ is None:
        full_address = _get_full_address(node)
        if _identifier.ID_SEP in full_address:
            id_namespace_ = full_address.split(_identifier.ID_SEP)[0]

    return id_namespace_


def update_id_verifiers(nodes):
    _identifier.update_verifiers(nodes)


def generate_container_id():
    hasher = hashlib.sha1()
    hasher.update(os.urandom(40))
    return "CON" + hasher.hexdigest()


def get_wildcard_path(path):
    """Replace namespaces with wildcard

    Change "|foo:bar|foo:nah" into "|*:foo|*nah"

    """
    wildcarded = list()
    for part in path.split("|"):
        namespaces, leaf = ([""] + part.rsplit(":", 1))[-2:]
        w = "*:" * len(namespaces.split(":")) + leaf
        wildcarded.append(w if leaf else "")

    return "|".join(wildcarded)


def get_renderer_by_layer(layer=None):
    layer = layer or get_current_renderlayer()
    return lib.query_by_renderlayer("defaultRenderGlobals",
                                    "currentRenderer",
                                    layer)


def get_current_renderlayer():
    return cmds.editRenderLayerGlobals(query=True, currentRenderLayer=True)


def get_render_filename_prefix(layer=None):
    renderer = get_renderer_by_layer(layer)

    if renderer == "vray":
        return lib.query_by_renderlayer("vraySettings",
                                        "fileNamePrefix",
                                        layer)
    else:
        return lib.query_by_renderlayer("defaultRenderGlobals",
                                        "imageFilePrefix",
                                        layer)


def get_render_resolution(layer=None):
    renderer = get_renderer_by_layer(layer)

    if renderer == "vray":
        width = lib.query_by_renderlayer("vraySettings",
                                         "width",
                                         layer)
        height = lib.query_by_renderlayer("vraySettings",
                                          "height",
                                          layer)
    else:
        width = lib.query_by_renderlayer("defaultResolution",
                                         "width",
                                         layer)
        height = lib.query_by_renderlayer("defaultResolution",
                                          "height",
                                          layer)
    return width, height


def get_render_padding(renderer):
    if renderer == "vray":
        from . import vray

        if not cmds.objExists("vraySettings"):
            vray.utils.create_vray_settings()

        return cmds.getAttr("vraySettings.fileNamePadding")
    else:
        return cmds.getAttr("defaultRenderGlobals.extensionPadding")


def compose_render_filename(layer, renderpass="", camera="", on_frame=None):
    """
    """
    renderer = get_renderer_by_layer(layer)
    prefix = get_render_filename_prefix(layer) or ""
    multi_render_cams = len(lib.ls_renderable_cameras(layer)) > 1
    has_renderlayers = lib.ls_renderable_layers() != ["defaultRenderLayer"]
    is_animated = cmds.getAttr("defaultRenderGlobals.animation")
    padding_str = "#" * get_render_padding(renderer)
    scene_name = cmds.file(query=True,
                           sceneName=True,
                           shortName=True).rsplit(".", 1)[0]

    # (NOTE) There's another *Deep EXR* in both VRay("exr (deep)") and
    #   Arnold("deepexr"), it's not being handled here since it's a rarely
    #   used format.
    #
    # (NOTE) Arnold's "deepexr" has been handled below.
    #

    if renderer == "vray":
        from . import vray

        if not cmds.objExists("vraySettings"):
            vray.utils.create_vray_settings()

        ext, is_multichannel_exr = vray.utils.get_vray_output_image_format()

        separate_folders = cmds.getAttr("vraySettings"
                                        ".relements_separateFolders")
        separate_rgba = cmds.getAttr("vraySettings"
                                     ".relements_separateRGBA")

        prefix = prefix or scene_name

        if renderpass and separate_folders:
            head, tail = os.path.split(prefix)
            prefix = "/".join([head, renderpass, tail])

        elif not renderpass and separate_folders and separate_rgba:
            head, tail = os.path.split(prefix)
            prefix = "/".join([head, "rgba", tail])

        # Put <Camera> tag if having multiple renderable cameras and
        # <Camera> tag not in prefix
        if (multi_render_cams and
                not any(t in prefix for t in ["<Camera>", "<camera>", "%c"])):
            prefix = "/".join(["<Camera>", prefix])

        # Put <Layer> tag if having multiple renderlayers and
        # <Layer> tag not in prefix
        if (has_renderlayers and
                not any(t in prefix for t in ["<Layer>", "<layer>", "%l"])):
            prefix = "/".join(["<Layer>", prefix])

        # Don't transform if the prefix is blank, so we can just default to
        # the scene file name.
        if prefix:
            for tag in ("<Layer>", "<layer>", "%l"):
                # We need to replace renderlayer tag by ourself if we don't
                # switch renderlayer.
                prefix = prefix.replace(tag, lib.pretty_layer_name(layer))
            prefix = mel.eval("vrayTransformFilename("
                              "\"{0}\", \"{1}\", \"{2}\", 0, 0, 0)"
                              "".format(prefix, camera, scene_name))

        pass_sep = cmds.getAttr("vraySettings"
                                ".fileNameRenderElementSeparator")
        if renderpass and not is_multichannel_exr:
            prefix = prefix + pass_sep + renderpass

        elif (not renderpass and separate_folders and
                separate_rgba and not is_multichannel_exr):
            prefix = prefix + pass_sep + "rgba"

        if is_animated:
            # When rendering to a non-raw format, vray places a period before
            # the padding, even though it doesn't show up in the render
            # globals filename.
            if ext == "vrimg":
                output_prefix = prefix + padding_str + "." + ext
            else:
                output_prefix = prefix + "." + padding_str + "." + ext
        else:
            output_prefix = prefix + "." + ext

    else:
        # Not VRay

        current_prefix = cmds.getAttr("defaultRenderGlobals.imageFilePrefix")
        prefix = prefix or scene_name

        if renderer == "arnold" and "<RenderPass>" not in prefix:
            from . import arnold
            aov_names = arnold.utils.get_arnold_aov_names(layer)
            if aov_names:
                prefix = "/".join(["<RenderPass>", prefix])

        # Put <Camera> tag if having multiple renderable cameras and
        # <Camera> tag not in prefix
        if (multi_render_cams and
                not any(t in prefix for t in ["<Camera>", "%c"])):
            prefix = "/".join(["<Camera>", prefix])

        # Put <RenderLayer> tag if having multiple renderlayers and
        # <RenderLayer> tag not in prefix
        if (has_renderlayers and
                not any(t in prefix
                        for t in ["<RenderLayer>", "<Layer>", "%l"])):
            prefix = "/".join(["<RenderLayer>", prefix])

        with capsule.maintained_modification():
            cmds.setAttr("defaultRenderGlobals.imageFilePrefix",
                         prefix,
                         type="string")

            output_prefix = cmds.renderSettings(
                genericFrameImageName=padding_str,
                layer=layer,
                camera=camera,
                customTokenString="RenderPass=" + renderpass)[0]

            cmds.setAttr("defaultRenderGlobals.imageFilePrefix",
                         current_prefix,
                         type="string")

        filename, ext = os.path.splitext(output_prefix)
        if ext == ".deepexr":
            output_prefix = filename + ".exr"

    if is_animated and on_frame is not None:
        frame_str = "%%0%dd" % len(padding_str) % on_frame
        output_prefix = output_prefix.replace(padding_str, frame_str)

    return output_prefix


def get_output_paths(output_dir, renderer, layer, camera):
    """
    """
    paths = OrderedDict()

    if renderer == "vray":
        import reveries.maya.vray.utils as utils_
        aov_names = utils_.get_vray_element_names(layer)

    elif renderer == "arnold":
        import reveries.maya.arnold.utils as utils_
        aov_names = utils_.get_arnold_aov_names(layer)

    else:
        aov_names = [""]

    for aov in aov_names:
        output_prefix = compose_render_filename(layer, aov, camera)
        output_path = output_dir + "/" + output_prefix

        paths[aov] = output_path.replace("\\", "/")

        log.debug("Collecting AOV output path: %s" % aov)
        log.debug("                      path: %s" % paths[aov])

    return paths


def update_dependency(container):
    """Update subset data and references

    This is for updating dependencies and relink them to assets in current
    project for the loaded subset that was originally moved from other project.

    You need to manually update the representation id value in container before
    using this function.

    """

    representation_id = cmds.getAttr(container + ".representation")
    representation_id = io.ObjectId(representation_id)

    representation = io.find_one({"_id": representation_id})

    if representation is None:
        raise Exception("Representation not found.")

    version, subset, asset, project = io.parenthood(representation)

    cmds.setAttr(container + ".assetId", str(asset["_id"]), type="string")
    cmds.setAttr(container + ".subsetId", str(subset["_id"]), type="string")
    cmds.setAttr(container + ".versionId", str(version["_id"]), type="string")

    # Update Reference path
    members = cmds.sets(container, query=True)
    reference_node = next(iter(lib.get_reference_nodes(members)), None)

    if reference_node is None:
        # No reference to update
        return

    package_path = get_representation_path_(representation,
                                            (version, subset, asset, project))

    file_type = representation["name"]
    if file_type == "FBXCache":
        file_type = "FBX"
    elif file_type in ("GPUCache", "LookDev"):
        file_type = "MayaAscii"

    file_name = representation["data"]["entryFileName"]
    entry_path = os.path.join(package_path, file_name)

    if not os.path.isfile(entry_path):
        raise IOError("File Not Found: {!r}".format(entry_path))

    entry_path = env_embedded_path(entry_path)

    cmds.file(entry_path,
              loadReference=reference_node,
              type=file_type,
              defaultExtensions=False)


def drop_interface():
    """Remove deprecated interface nodes from scene

    Transfer data from interface node to container node and delete

    """
    PORTS = ":AVALON_PORTS"
    INTERFACE = "pyblish.avalon.interface"
    CONTAINERS = AVALON_CONTAINERS[1:]

    if not cmds.objExists(PORTS):
        return

    for interface in lib.lsAttr("id", INTERFACE):

        namespace = cmds.getAttr(interface + ".namespace")
        container = get_container_from_namespace(namespace)

        cmds.warning("Processing container: %s" % container)

        getter = (lambda a: cmds.getAttr(interface + "." + a))

        for key, value in {
            "containerId": getter("containerId"),
            "assetId": getter("assetId"),
            "subsetId": getter("subsetId"),
            "versionId": getter("versionId"),
        }.items():
            if not cmds.objExists(container + "." + key):
                cmds.addAttr(container, longName=key, dataType="string")
            cmds.setAttr(container + "." + key, value, type="string")

        try:
            group = cmds.listConnections(interface + ".subsetGroup",
                                         source=True,
                                         destination=False)[0]
        except ValueError:
            pass
        else:
            # Connect subsetGroup
            grp_attr = container + "." + AVALON_GROUP_ATTR
            msg_attr = group + ".message"

            if not cmds.objExists(grp_attr):
                cmds.addAttr(container,
                             longName=AVALON_GROUP_ATTR,
                             attributeType="message")

            if not cmds.isConnected(msg_attr, grp_attr):
                cmds.setAttr(grp_attr, lock=False)
                cmds.connectAttr(msg_attr, grp_attr, force=True)
                cmds.setAttr(grp_attr, lock=True)

        # Ensure container lives in main container
        if CONTAINERS not in cmds.listSets(o=container):
            cmds.sets(container, addElement=CONTAINERS)

        cmds.delete(interface)


class MayaSFTPCJobExporter(avalon_sftpc.util.JobExporter):
    """Avalon SFTPC job file exporter with dependency helper implemented
    """

    def force_file_save(self):
        cmds.file(save=True, force=True)

    def parse_containers(self):
        """

        NOTE: This is the additional job for workfile

        """
        def texture_lookup(version_id):
            representations = set()

            dependent = "data.dependents.%s" % version_id
            filter = {
                "type": "version",
                "data.families": "reveries.texture",
                dependent: {"$exists": True},
            }
            version = io.find_one(filter)

            if version is not None:
                representation = io.find_one({"parent": version["_id"]})
                representations.add(str(representation["_id"]))
                # Patching textures
                for pre_version in io.find({"parent": version["parent"],
                                            "name": {"$lt": version["name"]}},
                                           sort=[("name", -1)]):

                    pre_repr = io.find_one({"parent": pre_version["_id"]})

                    if "fileInventory" in pre_repr["data"]:
                        representations.add(str(pre_repr["_id"]))
                    else:
                        break

            return representations

        # Start

        representations = set()
        versions = set()
        for container in api.registered_host().ls():
            representations.add(container["representation"])
            versions.add(container["versionId"])

        for id in versions:
            representations.update(texture_lookup(id))

        for id in representations:
            self.from_representation(id)

    def parse_stray_textures(self):
        """Find file nodes which pointing files that were not in published space

        If there are any texture files that has not been published...

        NOTE: This is the additional job for workfile

        """
        session = api.Session
        host = api.registered_host()
        workfile = host.current_file()
        project = session["AVALON_PROJECT"]

        jobs = list()

        for file_node in find_stray_textures():
            file_path = cmds.getAttr(file_node + ".fileTextureName",
                                     expandEnvironmentVariables=True)

            if project in file_path:
                head, tail = file_path.split(project, 1)
                # Replace root
                remote_path = self.remote_root + os.sep + project + tail

                file_path = os.path.normpath(file_path)
                remote_path = os.path.normpath(remote_path)

                jobs.append((file_path, remote_path))

        if not jobs:
            return

        self.add_job(files=jobs,
                     type="Stray Textures",
                     description="%s - %s" % (session["AVALON_ASSET"],
                                              os.path.basename(workfile)))


def export_sftpc_job_from_scene(remote_root, remote_user, site):
    """Export Avalon SFTPC job file from Maya scene

    Args:
        remote_root (str): Projects root at remote site
        remote_user (str): SFTP server username
        site (str): SFTP server connection config name

    Returns:
        str: Job file output path

    """
    exporter = MayaSFTPCJobExporter(remote_root=remote_root,
                                    remote_user=remote_user,
                                    site=site)
    additional_jobs = [
        exporter.parse_stray_textures,
        exporter.parse_containers,
        exporter.force_file_save,
    ]
    exporter.from_workfile(additional_jobs)

    return exporter.export()


def get_model_reference_group(geometry_path=None):
    """
    Get model reference group name under "Geometry" group.
    :param geometry_path: "Geometry" maya path
    :return: model_group, invalid_group
        Example:
        model_group = [
            '|ROOT|Group|Geometry|MonsterSharkB_model_01_:modelDefault',
            '|ROOT|Group|Geometry|MonsterSharkB_model_03_:modelLow',
            '|ROOT|Group|Geometry|spear_model_grp1',
        ]
        invalid_group = [
            u'|ROOT|Group|Geometry|foBase_geo2',
            u'|ROOT|Group|Geometry|previewEye_R_geo',
            u'|ROOT|Group|Geometry|previewEye_L_geo'
        ]
    """
    import maya.cmds as cmds

    # Get node's long name
    geometry_path = geometry_path or r'|ROOT|Group|Geometry'
    geometry_path = cmds.ls(geometry_path, long=True)[0]

    model_group = []
    invalid_group = []

    children = cmds.listRelatives(
        geometry_path, allDescendents=True, type="transform", fullPath=True)

    for child_name in children:
        if cmds.referenceQuery(child_name, isNodeReferenced=True):
            model_group_name = r'{}|{}'.format(
                geometry_path, child_name.split('|')[4])
            if model_group_name in model_group:
                continue
            model_group.append(model_group_name)

    for child_name in cmds.listRelatives(
            geometry_path, children=True, fullPath=True):
        if child_name not in model_group:
            invalid_group.append(child_name)

    return model_group, invalid_group


class HierarchyGetter(object):
    def __init__(self, skip_type=[], list_type=[], skip_grp=[]):
        self.shapes = []
        self.hierarchy_data = {}
        self.skip_grp = skip_grp
        self.skip_type = skip_type
        self.list_type = list_type or ["transform", "shape"]

    def _get_children(self, parent):
        children = cmds.listRelatives(parent, c=True, type=self.list_type, fullPath=True)
        if children:
            del_list = []
            for child in children:
                # child_long_name = cmds.ls(child, long=True)[0]

                if cmds.objectType(child) in self.skip_type:
                    del_list.append(child)

                if cmds.attributeQuery(
                        'intermediateObject', node=child, exists=True):
                    if cmds.getAttr('{0}.intermediateObject'.format(child)):
                        del_list.append(child)

            children = [x for x in children if x not in del_list]
        return children

    def _strip_namespace(self, children):
        new_children = []
        for child in children:
            new_children.append(child.split("|")[-1].split(":")[-1])
        return new_children

    def get_hierarchy(self, top_node):
        self.hierarchy_data = {}
        self._get_hierarchy(top_node, self.hierarchy_data)

        return self.hierarchy_data

    def _get_hierarchy(self, node, data):
        children = self._get_children(node)
        if children:
            _parent = node.split("|")[-1].split(":")[-1]
            data[_parent] = (self._strip_namespace(children), {})
            for child in children:
                self._get_hierarchy(child, data[_parent][1])

    def get_shapes(self, node):
        self.shapes = []
        self._get_shapes(node)

        return self.shapes

    def _get_shapes(self, node):
        children = cmds.listRelatives(node, c=True, type=["transform", "shape"], fullPath=True)
        if children:
            for child in children:
                # child_long_name = cmds.ls(child, long=True)[0]
                # print("child: ", child)
                # print("child_long_name: ", child_long_name)
                if cmds.attributeQuery(
                        'intermediateObject', node=child, exists=True):
                    if cmds.getAttr('{0}.intermediateObject'.format(child)):
                        continue
                if cmds.objectType(child) == "mesh":
                    self.shapes.append(child)

                self._get_shapes(child)
