
import os
import shutil

import errno
import pyblish.api
from avalon import api, io
from avalon.vendor import filelink


class IntegrateAvalonSubset(pyblish.api.InstancePlugin):
    """公開檔案並發佈至網路硬碟"""

    """Write to files and metadata, Resolve any dependency issues

    This plug-in exposes your data to others by encapsulating it
    into a new version.

    This plug-in resolves any paths which, if not updated might break
    the published file.

    The order of families is important, when working with lookdev you want to
    first publish the texture, update the texture paths in the nodes and then
    publish the shading network. Same goes for file dependent assets.

    (NOTE) No database write happens here, only file transfer.

    """

    label = "上傳 Subset"
    order = pyblish.api.IntegratorOrder

    targets = ["localhost"]

    def __init__(self, *args, **kwargs):
        super(IntegrateAvalonSubset, self).__init__(*args, **kwargs)
        self.is_progressive = None
        self.progress = 0
        self.progress_output = None
        self.transfers = dict(files=list(),
                              hardlinks=list())

    def process(self, instance):

        # Atomicity
        #
        # Guarantee atomic publishes - each asset contains
        # an identical set of members.
        #     __
        #    /     o
        #   /       \
        #  |    o    |
        #   \       /
        #    o   __/
        #

        if instance.data.get("_preflighted", False):
            return

        context = instance.context
        if not all(result["success"] for result in context.data["results"]):
            self.log.warning("Atomicity not held, aborting.")
            return

        # Assemble data and create version, representations
        subset, version, representations = self.register(instance)

        instance.data["toDatabase"] = (subset, version, representations)

        # Integrate representations' files to shareable space
        self.log.info("Integrating representations to shareable space ...")
        self.integrate()

    def register(self, instance):
        context = instance.context

        self.is_progressive = context.data.get("_progressivePublishing")
        self.progress = instance.data.get("_progressiveStep", -1)
        self.progress_output = instance.data.get("_progressiveOutput")

        # Assemble
        #
        #       |
        #       v
        #  --->   <----
        #       ^
        #       |
        #

        # Assemble families
        families = []
        current_families = instance.data.get("families", list())
        instance_family = instance.data.get("family", None)
        if instance_family is not None:
            families.append(instance_family)
        families += current_families

        # It's okay to create subset before integration complete if not exists
        subset = self.get_subset(instance, families)

        # get next version
        next_version = instance.data["versionNext"]
        version_data = self.create_version_data(context, instance)
        locations = [api.Session["AVALON_LOCATION"]]
        version = self.create_version(subset=subset,
                                      families=families,
                                      version_number=next_version,
                                      locations=locations,
                                      data=version_data)

        # Find the representations to transfer
        #
        representations = dict()
        _repr_data = dict()

        # Should not have any kind of check on files here, that should be done
        # by extractors, here only need to publish representation dirs.

        template_publish = instance.data["publishPathTemplate"]
        template_data = instance.data["publishPathTemplateData"]

        for key in sorted(instance.data.keys()):
            if not key.startswith("repr."):
                continue

            _, repr_name, entry = key.split(".", 2)

            if repr_name.startswith("_"):
                continue

            if repr_name not in representations:

                repr_data = dict()

                representation = {
                    "schema": "avalon-core:representation-2.0",
                    "type": "representation",
                    "parent": None,  # write this later
                    "name": repr_name,
                    "data": repr_data,
                }
                representations[repr_name] = representation
                _repr_data[repr_name] = repr_data

                src = instance.data["repr.%s._stage" % repr_name]
                dst = template_publish.format(representation=repr_name,
                                              **template_data)

                self.transfers["files"] += [
                    ("%s/%s" % (src, tail), "%s/%s" % (dst, tail)) for tail in
                    instance.data.get("repr.%s._files" % repr_name, [])
                ]
                self.transfers["hardlinks"] += [
                    ("%s/%s" % (src, tail), "%s/%s" % (dst, tail)) for tail in
                    instance.data.get("repr.%s._hardlinks" % repr_name, [])
                ]

            # Filtering representation data
            if not entry.startswith("_"):
                _repr_data[repr_name][entry] = instance.data[key]

        return subset, version, list(representations.values())

    def integrate(self):
        """Move the files

        Through `self.transfers`

        """
        if self.progress_output is None:
            progress_output = None
        else:
            progress_output = [
                os.path.abspath(
                    os.path.normpath(os.path.expandvars(file)))
                for file in self.progress_output
            ]

        # Write to disk
        #          _
        #         | |
        #        _| |_
        #    ____\   /
        #   |\    \ / \
        #   \ \    v   \
        #    \ \________.
        #     \|________|
        #

        transfered = list()

        for job in self.transfers:
            transfers = self.transfers[job]

            for src, dst in transfers:
                # normpath
                # self.log.debug("Src. Before: {!r}".format(src))
                # self.log.debug("Dst. Before: {!r}".format(dst))

                src = os.path.abspath(
                    os.path.normpath(os.path.expandvars(src)))
                dst = os.path.abspath(
                    os.path.normpath(os.path.expandvars(dst)))

                if self.is_progressive:
                    if os.path.isfile(dst):
                        continue
                    if (progress_output is not None
                            and src not in progress_output):
                        continue

                print("Copying {0}: {1} \n"
                      "          -> {2}".format(job, src, dst))

                if src == dst:
                    self.log.debug("Source and destination are the same, "
                                   "will not copy.")
                    continue

                if dst in transfered:
                    # (TODO) Should not implement like this. This is a hot-fix.
                    self.log.warning("File transfered: %s" % dst)
                    continue

                if job == "files":
                    self.copy_file(src, dst)
                if job == "hardlinks":
                    self.hardlink_file(src, dst)

                transfered.append(dst)

    def copy_file(self, src, dst):
        file_dir = os.path.dirname(dst)
        if not os.path.isdir(file_dir):
            try:
                os.makedirs(file_dir)
            except Exception as e:
                self.log.warning("Makedir error: %s" % e)
        try:
            shutil.copy2(src, dst)
        except OSError:
            msg = "An unexpected error occurred."
            self.log.critical(msg)
            raise OSError(msg)

    def hardlink_file(self, src, dst):
        if os.path.isfile(dst):
            self.log.warning("File exists, skip creating hardlink: %s" % dst)
            return

        dirname = os.path.dirname(dst)
        try:
            os.makedirs(dirname)
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                self.log.critical("An unexpected error occurred.")
                raise

        try:
            filelink.create(src, dst, filelink.HARDLINK)
        except OSError:
            msg = "An unexpected error occurred."
            self.log.critical(msg)
            raise OSError(msg)

    def get_subset(self, instance, families):

        asset_id = instance.data["assetDoc"]["_id"]

        subset = io.find_one({"type": "subset",
                              "parent": asset_id,
                              "name": instance.data["subset"]})

        if subset is None:
            subset_name = instance.data["subset"]
            self.log.info("Subset '%s' not found, creating.." % subset_name)

            subset = {
                "_id": io.ObjectId(),  # Pre-generate subset id
                "schema": "avalon-core:subset-3.0",
                "type": "subset",
                "name": subset_name,
                "data": {
                    "families": families,
                    "subsetGroup": instance.data.get("subsetGroup", ""),
                },
                "parent": asset_id,
            }

            # For lookdev publish
            if instance.data.get("model_subset_id", None):
                subset["data"]["model_subset_id"] = \
                    instance.data["model_subset_id"]
            # For lookdev TensionMap
            if instance.data.get("requireTensionMap", None):
                subset["data"]["requireTensionMap"] = \
                    instance.data["requireTensionMap"]

        return subset

    def create_version(self,
                       subset,
                       families,
                       version_number,
                       locations,
                       data):
        """ Copy given source to destination

        Args:
            subset (dict): the registered subset of the asset
            families (list): instance's families
            version_number (int): the version number
            locations (list): the currently registered locations
            data (dict): version data

        Returns:
            dict: collection of data to create a version
        """
        # Imprint currently registered location
        version_locations = [location for location in locations if
                             location is not None]

        version = {
            "type": "version",
            "parent": subset["_id"],
            "name": version_number,
            "locations": version_locations,
            "data": data
        }

        if subset["schema"] == "avalon-core:subset-3.0":
            version["schema"] = "avalon-core:version-3.0"
        else:
            version["schema"] = "avalon-core:version-2.0"
            version["data"]["families"] = families

        if self.is_progressive and self.progress >= 0:
            try:
                start = int(data["startFrame"])
                end = int(data["endFrame"])
                step = int(data["step"])

            except KeyError:
                raise KeyError("Missing frame range data, this is a bug.")

            else:
                total = len(range(start, end + 1, step))
                if data.get("isStereo"):
                    total *= 2
                version["data"]["progress"] = {
                    "total": total,
                    "current": self.progress,
                }

        return version

    def create_version_data(self, context, instance):
        """Create the data collection for the version

        Args:
            context: the current context
            instance: the current instance being published

        Returns:
            dict: the required information with instance.data as key
        """
        # create relative source path for DB
        source = context.data["currentMaking"]
        source = source.replace(api.registered_root(), "{root}")
        source = source.replace("\\", "/")

        work_dir = api.Session.get("AVALON_WORKDIR")
        work_dir = work_dir.replace(api.registered_root(), "{root}")
        work_dir = work_dir.replace("\\", "/")

        version_data = {
            "time": context.data["time"],
            "author": context.data["user"],
            "task": api.Session.get("AVALON_TASK"),
            "source": source,
            "workDir": work_dir,
            "comment": context.data.get("comment"),
            "dependencies": instance.data.get("dependencies", dict()),
            "dependents": dict(),
        }

        # Include optional data if present in
        optionals = [
            "startFrame",
            "endFrame",
            "step",
            "handles",
            "hasUnversionedSurfaces",
            "deadlineJobId",
            # "model_subset_data",  # For rig publish
            "shape_merge"  # For model/lookdev publish
        ]
        for key in optionals:
            if key in instance.data:
                version_data[key] = instance.data[key]

        return version_data
