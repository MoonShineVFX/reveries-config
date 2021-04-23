
import pyblish.api


class CollectDeformedOutputs(pyblish.api.InstancePlugin):
    """Collect out geometry data for instance.

    * Only visible objects will be cached.

    If the caching subset has any objectSet which name is or endswith
    "OutSet", will create instances from them. For "OutSet" that has
    prefix, will use that prefix as variant of subset.

    For example:
             "OutSet" -> "pointcache.Boy_model_01_Default"
          "SimOutSet" -> "pointcache.Boy_model_01_Sim"
        "ClothOutSet" -> "pointcache.Boy_model_01_Cloth"

    If no "OutSet", collect deformable nodes directly from instance
    member (selection).

    If subset was nested in hierarchy but has "OutSet", nodes in "OutSet"
    will be used.

    """

    order = pyblish.api.CollectorOrder - 0.2999
    label = "Collect Deformed Outputs"
    hosts = ["maya"]
    families = [
        "reveries.pointcache",
    ]

    def process(self, instance):
        import maya.cmds as cmds
        from reveries.maya import lib, pipeline

        # Frame range
        if instance.data["staticCache"]:
            start_frame = cmds.currentTime(query=True)
            end_frame = cmds.currentTime(query=True)
        else:
            get = (lambda f: cmds.playbackOptions(query=True, **f))
            start_frame = get({"minTime": True})
            end_frame = get({"maxTime": True})

        members = instance[:]
        asset_docs = dict()
        out_sets = list()

        # Find OutSet from *Subset Group nodes*
        #
        for group in cmds.ls(members, type="transform", long=True):
            if cmds.listRelatives(group, shapes=True):
                continue

            try:
                container = pipeline.get_container_from_group(group)
            except AssertionError:
                # Not a subset group node
                continue

            nodes = cmds.sets(container, query=True)
            sets = [
                s for s in cmds.ls(nodes, type="objectSet")
                if s.endswith("OutSet")
            ]
            if sets:
                asset_id = cmds.getAttr(container + ".assetId")
                out_sets += [(asset_id, s) for s in sets]
                members.remove(group)

                if asset_id not in asset_docs:
                    asset_docs[asset_id] = self.get_asset_doc(asset_id)

        # Collect cacheable nodes

        created = False
        context = instance.context
        backup = instance

        if out_sets:
            # Cacheables from OutSet of loaded subset
            out_cache = dict()
            subset = backup.data["subset"][len("pointcache"):]

            for asset_id, out_set in out_sets:

                variant = out_set.rsplit(":", 1)[-1][:-len("OutSet")]
                if variant:
                    name = variant + "." + subset
                else:
                    name = subset

                self.log.info(name)

                namespace = lib.get_ns(out_set)
                set_member = cmds.ls(cmds.sets(out_set, query=True), long=True)
                all_cacheables = lib.pick_cacheable(set_member)
                cacheables = lib.get_visible_in_frame_range(all_cacheables,
                                                            int(start_frame),
                                                            int(end_frame))
                has_hidden = len(all_cacheables) > len(cacheables)

                # Plus locator
                cacheables += self.pick_locators(set_member)

                out_cache[(asset_id, namespace, name)] = (
                    has_hidden, cacheables, all_cacheables
                )

                for n in cacheables:
                    if n in members:
                        members.remove(n)

            # Re-Create instances

            for k, (has_hidden, cacheables, all_cacheables) in out_cache.items():
                asset_id, namespace, name = k

                if not cacheables:
                    self.log.debug("Skip empty OutSet %s in %s"
                                   % (name, namespace))
                    if has_hidden:
                        self.log.warning("Geometry in OutSet %s is hidden, "
                                         "possible wrong LOD ?" % namespace)
                    continue

                if has_hidden:
                    self.log.debug("Some geometry in OutSet %s is hidden."
                                   % namespace)

                namespace = namespace[1:]  # Remove root ":"
                # For filesystem, remove other ":" if the namespace is nested
                namespace = namespace.replace(":", "._.")

                instance = context.create_instance(namespace + "." + name)
                created = True

                instance.data.update(backup.data)

                # New subset name
                instance.data["subset"] = ".".join(["pointcache",
                                                    namespace,
                                                    name])
                instance[:] = cacheables
                instance.data["outCache"] = cacheables
                instance.data["_hasHidden"] = has_hidden
                instance.data["requireAvalonUUID"] = cacheables
                instance.data["startFrame"] = start_frame
                instance.data["endFrame"] = end_frame
                instance.data["all_cacheables"] = all_cacheables

                asset_doc = asset_docs[asset_id]
                self.find_tension_required(instance, asset_doc)
                self.is_rest_position_required(instance, asset_doc)
                self.add_families(instance)

        if not members:
            # Nothing left, all in/has OutSet

            if not created:
                self.log.warning("No pointcache instance created.")
            else:
                context.remove(backup)

        else:
            # Cache nodes that were not in any OutSet

            instance = backup

            # Cacheables from instance member
            expanded = self.outset_respected_expand(members)
            all_cacheables = lib.pick_cacheable(expanded, all_descendents=False)
            cacheables = lib.get_visible_in_frame_range(all_cacheables,
                                                        int(start_frame),
                                                        int(end_frame))
            has_hidden = len(all_cacheables) > len(cacheables)
            # Plus locator
            cacheables += self.pick_locators(members)

            instance[:] = cacheables
            instance.data["outCache"] = cacheables
            instance.data["_hasHidden"] = has_hidden
            instance.data["requireAvalonUUID"] = cacheables
            instance.data["startFrame"] = start_frame
            instance.data["endFrame"] = end_frame
            instance.data["all_cacheables"] = all_cacheables

            if instance.data.get("tryTension"):
                instance.data["requireTensionMap"] = cacheables
            if instance.data.get("tryRestPos"):
                instance.data["requireRestPos"] = True

            self.add_families(instance)

    def outset_respected_expand(self, members):
        from maya import cmds
        from reveries.maya import pipeline

        expanded = set(members)

        def walk_hierarchy(parent):
            for node in cmds.listRelatives(parent,
                                           children=True,
                                           path=True,
                                           type="transform") or []:
                yield node

                try:
                    container = pipeline.get_container_from_group(node)
                except AssertionError:
                    # Not a subset group node
                    for n in walk_hierarchy(node):
                        yield n
                else:
                    # Look for OutSet
                    nodes = cmds.sets(container, query=True)
                    out_sets = [
                        s for s in cmds.ls(nodes, type="objectSet")
                        if s.endswith("OutSet")
                    ]
                    if out_sets:
                        out_set = sorted(out_sets)[0]
                        if len(out_sets) > 1:
                            self.log.warning(
                                "Multiple OutSet found in %s, but only one "
                                "OutSet will be expanded: %s"
                                % (container, out_set))

                        for n in cmds.sets(out_set, query=True) or []:
                            yield n
                    else:
                        for n in walk_hierarchy(node):
                            yield n

        for member in members:
            for node in walk_hierarchy(member):
                expanded.add(node)

        return cmds.ls(sorted(expanded), long=True)

    def pick_locators(self, members):
        import maya.cmds as cmds

        locator_shapes = cmds.listRelatives(members,
                                            shapes=True,
                                            path=True,
                                            type="locator")
        locators = cmds.listRelatives(locator_shapes,
                                      parent=True,
                                      fullPath=True)
        if locators:
            self.log.info("Including locators..")

        return locators or []

    def add_families(self, instance):

        families = list()

        if "extractType" in instance.data:  # For backward compat
            families.append({
                "Alembic": "reveries.pointcache.abc",
                "GPUCache": "reveries.pointcache.gpu",
                "FBXCache": "reveries.pointcache.fbx",
                "AniUSDData": "reveries.pointcache.usd",
            }[instance.data.pop("extractType")])

        else:
            if instance.data.pop("exportAlembic"):
                families.append("reveries.pointcache.abc")
            if instance.data.pop("exportGPUCache"):
                families.append("reveries.pointcache.gpu")
            if instance.data.pop("exportFBXCache"):
                families.append("reveries.pointcache.fbx")

            instance.data["exportPointCacheUSD"] = False
            if "exportAniUSDData" in instance.data.keys():
                if instance.data.pop("exportAniUSDData"):
                    families.append("reveries.pointcache.usd")
                    instance.data["exportPointCacheUSD"] = True

        instance.data["families"] = families

    def retrieve_tension_data(self, asset):
        from avalon import io

        if not asset:
            return None

        subset = io.find_one(
            {"type": "subset", "parent": asset["_id"], "name": "lookDefault"},
        )
        if not subset:
            return None

        version = io.find_one(
            {"type": "version", "parent": subset["_id"]},
            sort=[("name", -1)],
            projection={"data.requireTensionMap": True}
        )
        if not version:
            return None

        return version["data"].get("requireTensionMap")

    def find_tension_required(self, instance, asset_doc):
        from maya import cmds

        tensioned_data = self.retrieve_tension_data(asset_doc)
        if not tensioned_data:
            return

        self.log.info("TensionMap required: %s" % instance.data["subset"])

        wildcards = []
        for path in tensioned_data:
            w = "|*:".join([p.rsplit(":", 1)[-1] for p in path.split("|")])
            wildcards.append("*:" + w)

        tension_required = []
        cacheables = instance.data["outCache"]
        for node in cmds.ls(wildcards, long=True):
            if node in cacheables:
                tension_required.append(node)

        instance.data["requireTensionMap"] = tension_required

    def is_rest_position_required(self, instance, asset_doc):
        value_path = "taskOptions.rigging.outputRestPosition.value"
        value = asset_doc["data"]
        for entry in value_path.split("."):
            value = value.get(entry, {})

        require = value is True

        if require:
            self.log.info("RestPRef required: %s" % instance.data["subset"])
            instance.data["requireRestPos"] = require

    def get_asset_doc(self, asset_id):
        from avalon import io
        asset_doc = io.find_one({"type": "asset",
                                 "_id": io.ObjectId(asset_id)})
        return asset_doc
