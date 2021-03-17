
import logging
import json
import os

import maya.cmds as cmds

from avalon import io, api
from avalon.maya.pipeline import AVALON_CONTAINER_ID

from ....utils import get_representation_path_
from ....maya import lib, utils
from ...pipeline import (
    get_container_from_namespace,
    iter_containers_from_namespace,
    get_group_from_container,
    parse_container,
)

from .models import UNDEFINED_SUBSET


log = logging.getLogger(__name__)


def get_workfile():
    path = cmds.file(query=True, sceneName=True) or "untitled"
    return os.path.basename(path)


def get_workfolder():
    return os.path.dirname(cmds.file(query=True, sceneName=True))


def select(nodes):
    cmds.select(nodes, noExpand=True)


def group_from_namespace(namespace):
    """Return group nodes from namespace

    Args:
        namespace (str, unicode): Target subset's namespace

    Returns:
        str: group node in long name

    """
    for container in iter_containers_from_namespace(namespace):
        yield get_group_from_container(container)


def get_asset_id(node):
    try:
        return utils.get_id_namespace_loosely(node)
    except Exception as e:
        import traceback
        print("# get_asset_id failed: %s" % node)
        traceback.print_exc()


def list_descendents(nodes):
    """Include full descendant hierarchy of given nodes.

    This is a workaround to cmds.listRelatives(allDescendents=True) because
    this way correctly keeps children instance paths (see Maya documentation)

    This fixes LKD-26: assignments not working as expected on instanced shapes.

    Return:
        list: List of children descendents of nodes

    """
    result = []
    while True:
        nodes = cmds.listRelatives(nodes,
                                   path=True,
                                   type="transform")
        if nodes:
            result.extend(nodes)
        else:
            return result


def get_session_asset_id():
    doc = io.find_one({"type": "asset", "name": api.Session["AVALON_ASSET"]},
                      projection={"_id": True})
    return str(doc["_id"])


def get_selected_asset_nodes():

    def get_member(node):
        return set(cmds.ls(cmds.sets(node, query=True), type="transform"))

    nodes = list()
    session_asset_id = None

    selection = cmds.ls(selection=True)
    hierarchy = list_descendents(selection)

    containers = {
        node: get_member(node) for node in
        cmds.ls("*.id", objectsOnly=True, type="objectSet", recursive=True)
        if cmds.getAttr(node + ".id") == "pyblish.avalon.container"
    }

    for node in set(selection + hierarchy):

        asset_id = get_asset_id(node)
        if asset_id is None:
            session_asset_id = session_asset_id or get_session_asset_id()

        for container, members in containers.items():
            if node in members:
                subset = cmds.getAttr(container + ".name")
                namespace = cmds.getAttr(container + ".namespace")
                break
        else:
            subset = UNDEFINED_SUBSET
            namespace = lib.get_ns(node)

        nodes.append({
            "node": node,
            "assetId": asset_id or session_asset_id,
            "subset": subset,
            "namespace": namespace,
        })

    return nodes


def get_all_asset_nodes():
    """Get all assets from the scene, container based"""

    host = api.registered_host()

    nodes = list()
    session_asset_id = None

    for container in host.ls():
        # We only interested in surface assets !
        # (TODO): This black list should be somewhere else
        if container["loader"] in ("LookLoader",
                                   "CameraLoader",
                                   "ArnoldAssLoader",
                                   "SetDressLoader",
                                   "LightSetLoader"):
            continue

        # Gather all information
        subset = container["name"]
        namespace = container["namespace"]

        # (NOTE) Previously, nodes was collecting from container objectSet,
        #        but container may lost it's member nodes during production.
        #        So change to get asset nodes from hierarchy to ensure user
        #        always gets all loaded subsets.
        group = container.get("subsetGroup")
        if not group:
            if container["loader"] == "XGenLegacyLoader":
                members = cmds.sets(container["objectName"], query=True)
                palette = cmds.ls(members, type="xgmPalette")
                if palette:
                    group = palette[0]
                else:
                    continue
            else:
                continue

        for node in cmds.listRelatives(group,
                                       allDescendents=True,
                                       path=True,
                                       type="transform"):

            asset_id = get_asset_id(node)
            if asset_id is None:
                session_asset_id = session_asset_id or get_session_asset_id()

            nodes.append({
                "node": node,
                "assetId": asset_id or session_asset_id,
                "subset": subset,
                "namespace": namespace,
            })

    return nodes


def create_items(nodes, by_selection=False):
    """Create an item for the view

    It fetches the look document based on the asset ID found in the content.
    The item will contain all important information for the tool to work.

    If there is an asset ID which is not registered in the project's collection
    it will log a warning message.

    Args:
        nodes (set): A set of maya nodes

    Returns:
        list of dicts

    """
    if not nodes:
        return []

    asset_view_items = []

    id_hashes = dict()
    for node in nodes:
        asset_id = node["assetId"]
        if asset_id not in id_hashes:
            id_hashes[asset_id] = list()
        id_hashes[asset_id].append(node)

    for asset_id, asset_nodes in id_hashes.items():
        asset = io.find_one({"_id": io.ObjectId(asset_id)},
                            projection={"name": True,
                                        "data.visualParent": True})

        # Skip if asset id is not found
        if not asset:
            log.warning("Asset id not found in the database, skipping '%s'."
                        % asset_id)
            continue

        # Collect available look subsets for this asset
        looks = list_looks(asset)
        loaded_looks = list_loaded_looks(asset)

        # Collect namespaces the asset is found in
        subsets = dict()
        namespace_nodes = dict()
        namespace_selection = dict()

        for node in asset_nodes:
            namespace = node["namespace"]
            subset = node["subset"]

            if namespace not in namespace_nodes:
                subsets[namespace] = subset
                namespace_nodes[namespace] = set()

            namespace_nodes[namespace].add(node["node"])

        for k in namespace_nodes:
            namespace_nodes[k] = list(namespace_nodes[k])

        namespaces = list(subsets.keys())

        if by_selection:
            namespace_selection = namespace_nodes
        else:
            for namespace in namespaces:
                selection = set()
                for group in group_from_namespace(namespace):
                    if group is not None:
                        selection.add(group)
                namespace_selection[namespace] = list(selection)

        asset_view_items.append({"label": asset["name"],
                                 "asset": asset,
                                 "looks": looks,
                                 "loadedLooks": loaded_looks,
                                 "namespaces": namespaces,
                                 "subsets": subsets,
                                 "nodesByNamespace": namespace_nodes,
                                 "selectByNamespace": namespace_selection})

    return asset_view_items


def list_looks(asset):
    """Return all look subsets from database for the given asset
    """
    asset_id = asset["_id"]
    parent_id = asset["data"]["visualParent"]
    if parent_id:
        parent = {"$in": [asset_id, parent_id]}
    else:
        parent = asset_id

    look_subsets = list(io.find({"parent": parent,
                                 "type": "subset",
                                 "name": {"$regex": "look*"},
                                 # Ignore looks that have been dump to trash
                                 "data.subsetGroup": {"$ne": "Trash Bin"}}))
    for look in look_subsets:
        # Get the latest version of this look subset
        version = io.find_one({"type": "version",
                               "parent": look["_id"]},
                              sort=[("name", -1)])
        look["version"] = version["name"]
        look["versionId"] = version["_id"]

    return look_subsets


def list_loaded_looks(asset):
    look_subsets = list()
    cached_look = dict()

    asset_id = asset["_id"]
    parent_id = asset["data"]["visualParent"]

    containers = lib.lsAttrs({
        "id": AVALON_CONTAINER_ID,
        "loader": "LookLoader",
        "assetId": str(asset_id),
    })
    if parent_id:
        containers += lib.lsAttrs({
            "id": AVALON_CONTAINER_ID,
            "loader": "LookLoader",
            "assetId": str(parent_id),
        })

    for container in containers:

        subset_id = cmds.getAttr(container + ".subsetId")
        if subset_id in cached_look:
            look = cached_look[subset_id].copy()
        else:
            look = io.find_one({"_id": io.ObjectId(subset_id)})
            cached_look[subset_id] = look

        namespace = cmds.getAttr(container + ".namespace")
        # Example: ":Zombie_look_02_"
        # result: "Zombie 02"
        asset = namespace[1:].rsplit("_", 3)[0]  # Zombie
        num = namespace.split("_")[-2]  # "02"
        ident = asset + " " + num
        look["ident"] = ident
        look["namespace"] = namespace

        look_subsets.append(look)

    return look_subsets


def load_look(look, overload=False):
    """Load look subset if it's not been loaded
    """
    representation = io.find_one({"type": "representation",
                                  "parent": look["versionId"],
                                  "name": "LookDev"})
    representation_id = str(representation["_id"])

    is_loaded = False
    for container in lib.lsAttrs({"id": AVALON_CONTAINER_ID,
                                  "loader": "LookLoader",
                                  "representation": representation_id}):
        if overload:
            is_loaded = True
            log.info("Overload look ..")
            break

        log.info("Reusing loaded look ..")
        return parse_container(container)

    if not is_loaded:
        # Not loaded
        log.info("Using look for the first time ..")

    loaders = api.loaders_from_representation(api.discover(api.Loader),
                                              representation_id)
    Loader = next((i for i in loaders if i.__name__ == "LookLoader"), None)
    if Loader is None:
        raise RuntimeError("Could not find LookLoader, this is a bug")

    container = api.load(Loader,
                         representation,
                         options={"overload": overload})
    return container


def get_loaded_look(look, *args, **kwargs):
    container = get_container_from_namespace(look["namespace"])
    return parse_container(container)


def remove_unused_looks():
    """Removes all loaded looks for which none of the shaders are used.

    This will cleanup all loaded "LookLoader" containers that are unused in
    the current scene.

    """

    host = api.registered_host()

    unused = list()
    for container in host.ls():
        if container["loader"] == "LookLoader":
            members = cmds.sets(container["objectName"], query=True)
            look_sets = cmds.ls(members, type="objectSet")
            for look_set in look_sets:
                # If the set is used than we consider this look *in use*
                if cmds.sets(look_set, query=True):
                    break
            else:
                unused.append(container)

    for container in unused:
        log.info("Removing unused look container: %s", container['objectName'])
        api.remove(container)

    log.info("Finished removing unused looks. (see log for details)")


def get_relationship(look):
    representation_id = io.ObjectId(look["representation"])
    representation = io.find_one({"_id": representation_id})

    parents = io.parenthood(representation)
    package_path = get_representation_path_(representation, parents)

    file_name = representation["data"]["linkFname"]
    relationship = os.path.join(package_path, file_name)

    return relationship


def assign_look(nodes, look, via_uv):
    """Assign looks via namespaces

    Args:
        namespaces (str, unicode or set): Target subsets' namespaces
        look (dict): The container data of look

    """
    relationship = get_relationship(look)

    if not os.path.isfile(relationship):
        log.warning("Look development asset "
                    "has no relationship data.\n"
                    "{!r} was not found".format(relationship))
        return

    # Load map
    with open(relationship) as f:
        relationships = json.load(f)

    by_name = relationships.get("byNodeName", False)

    # Assign
    #
    if via_uv:
        _look_via_uv(look, relationships, nodes, by_name)
    else:
        _apply_shaders(look,
                       relationships["shaderById"],
                       nodes,
                       by_name)
        _connect_uv_chooser(look,
                            relationships.get("uvChooser"),
                            nodes,
                            by_name)
        _apply_crease_edges(look,
                            relationships["creaseSets"],
                            nodes,
                            by_name)

        arnold_attrs = relationships.get("arnoldAttrs",
                                         relationships.get("alSmoothSets"))
        _apply_ai_attrs(look,
                        arnold_attrs,
                        nodes,
                        by_name)


def _apply_shaders(look, relationship, nodes, by_name=False):
    namespace = look["namespace"][1:]

    lib.apply_shaders(relationship,
                      namespace,
                      nodes=nodes,
                      by_name=by_name)


def _connect_uv_chooser(look, relationship, nodes, by_name=False):
    if not relationship:
        return

    namespace = look["namespace"][1:]

    lib.connect_uv_chooser(relationship,
                           namespace,
                           nodes=nodes,
                           by_name=by_name)


def _apply_crease_edges(look, relationship, nodes, by_name=False):
    namespace = look["namespace"][1:]

    crease_sets = lib.apply_crease_edges(relationship,
                                         namespace,
                                         nodes=nodes,
                                         by_name=by_name)
    cmds.sets(crease_sets, forceElement=look["objectName"])


def _apply_ai_attrs(look, relationship, nodes, by_name=False):
    namespace = look["namespace"][1:]

    if relationship is not None:
        try:
            from ....maya import arnold
        except RuntimeError:
            pass
        else:
            arnold.utils.apply_ai_attrs(
                relationship,
                namespace,
                nodes=nodes,
                by_name=by_name,
            )


def _look_via_uv(look, relationships, nodes, by_name=False):
    """Assign looks via namespaces and using UV hash as hint

    In some cases, a setdress liked subset may assembled from a numbers of
    duplicated models, and for some reason the duplicated models may be given
    different Avalon UUIDs. Which cause the look only able to apply to one of
    those models.

    By the help of UV hash, as long as there's one set of model's Avalon UUID
    is correct, the rest of the models can compare with thier UV hashes and
    use that as a hint to apply look.

    """

    hasher = utils.MeshHasher()
    uv_via_id = dict()
    id_via_uv = dict()

    hierarchy = list_descendents(nodes)

    for mesh in cmds.ls(list(set(nodes + hierarchy)),
                        type="mesh",  # We can only hash meshes.
                        ):
        node = cmds.listRelatives(mesh, parent=True, path=True)[0]

        id = utils.get_id_loosely(node)
        if id in uv_via_id:
            continue

        hasher.clear()
        hasher.set_mesh(node)
        hasher.update_uvmap()
        uv_hash = hasher.digest().get("uvmap")

        if uv_hash is None:
            continue

        uv_via_id[id] = uv_hash

        if uv_hash not in id_via_uv:
            id_via_uv[uv_hash] = set()
        id_via_uv[uv_hash].add(id)

    # Apply shaders
    #
    shader_by_id = dict()
    for shader, ids in relationships["shaderById"].items():
        shader_by_id[shader] = list()

        for id_ in ids:
            id, faces = (id_.rsplit(".", 1) + [""])[:2]

            if id not in uv_via_id:
                # The id from relationships does not exists in scene
                continue

            uv_hash = uv_via_id[id]
            same_uv_ids = id_via_uv[uv_hash]
            shader_by_id[shader] += [".".join([i, faces]) for i in same_uv_ids]

    _apply_shaders(look, shader_by_id, nodes, by_name)

    # Apply crease edges
    #
    crease_by_id = dict()
    for level, members in relationships["creaseSets"].items():
        crease_by_id[level] = list()

        for member in members:
            id, edges = member.split(".")

            if id not in uv_via_id:
                # The id from relationships does not exists in scene
                continue

            uv_hash = uv_via_id[id]
            same_uv_ids = id_via_uv[uv_hash]
            crease_by_id[level] += [".".join([i, edges]) for i in same_uv_ids]

    _apply_crease_edges(look, crease_by_id, nodes, by_name)

    # COnnect UV Choosers
    #
    uv_chooser = dict()
    for chooser, members in relationships.get("uvChooser", {}).items():
        uv_chooser[chooser] = list()

        for member in members:
            id, attr = member.split(".")

            if id not in uv_via_id:
                # The id from relationships does not exists in scene
                continue

            uv_hash = uv_via_id[id]
            same_uv_ids = id_via_uv[uv_hash]
            uv_chooser[chooser] += [".".join([i, attr]) for i in same_uv_ids]

    _connect_uv_chooser(look,
                        uv_chooser,
                        nodes,
                        by_name)

    # Apply Arnold attributes
    #
    arnold_attrs = relationships.get("arnoldAttrs",
                                     relationships.get("alSmoothSets"))
    if arnold_attrs is None:
        return

    ai_attrs_by_id = dict()
    for id, attrs in arnold_attrs.items():

        if id not in uv_via_id:
            # The id from relationships does not exists in scene
            continue

        uv_hash = uv_via_id[id]
        same_uv_ids = id_via_uv[uv_hash]
        for i in same_uv_ids:
            ai_attrs_by_id[i] = attrs

    _apply_ai_attrs(look, ai_attrs_by_id, nodes, by_name)


def remove_look(nodes, asset_ids):

    look_sets = set()
    for container in lib.lsAttrs({"id": AVALON_CONTAINER_ID,
                                  "loader": "LookLoader"}):
        container = parse_container(container)
        if container["assetId"] not in asset_ids:
            continue

        members = cmds.sets(container["objectName"], query=True)
        look_sets.update(cmds.ls(members, type="objectSet"))

    shaded = cmds.ls(nodes, type=("transform", "surfaceShape"))

    for look_set in look_sets:
        for member in cmds.sets(look_set, query=True) or []:
            if member.rsplit(".")[0] in shaded:
                cmds.sets(member, remove=look_set)

    # Assign to lambert1
    cmds.sets(shaded, forceElement="initialShadingGroup")
