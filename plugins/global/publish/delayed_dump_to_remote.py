import os
import re
import json
import pyblish.api
import avalon.api
from avalon import io
from reveries import lib, filesys


class PyblishEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        try:
            return json.JSONEncoder.default(self, obj)
        except TypeError:
            return str(obj)


def json_dump(dump, file):
    json.dump(dump, file, indent=4, sort_keys=True, cls=PyblishEncoder)


class DelayedDumpToRemote(pyblish.api.ContextPlugin):
    """Dump context with instances and delayed extractors to remote publish

    This plugin will dump context and instances that have unprocessed delayed
    extractors into JSON files for continuing the publish process in remote
    side.

    At the remote side, it should pick up the extractor dump file (JSON) and
    start extraction from there without re-run the publish from beginning.

    After the remote extraction complete, *filesys* publish should pick the
    context dump file (JSON) and start validating extracted files and publish
    them.

    """

    order = pyblish.api.ExtractorOrder + 0.491
    label = "Delayed Dump To Remote"

    EXTRACTOR_DUMP = "{stage}/.extractor.json"
    INSTANCE_DUMP = "{version}/.instance.json"
    CONTEXT_DUMP = "{filesys}/dumps/.context.{user}.{oid}.json"

    def process(self, context):
        # Skip if any error occurred
        if not all(result["success"] for result in context.data["results"]):
            self.log.warning("Atomicity not held, aborting.")
            return

        instances = list()
        for instance in context:
            if not instance.data.get("publish", True):
                continue

            instances.append(instance)

        if not instances:
            return

        dump_id = str(io.ObjectId())
        dump_user = context.data["user"]

        # Dump instances
        dumps = dict()
        skip_ins = []
        for instance in instances:

            extractors = [(key.split(".")[1], value)
                          for key, value in instance.data.items()
                          if re.match(r"repr\.[a-zA-Z_]*\._delayRun", key)
                          and not value.get("done")]
            extractors.sort(key=lambda t: t[1].get("order", -1))

            if not extractors:
                skip_ins.append(instance.name)
                continue

            self.log.info("Dumping instance %s .." % instance)
            dump_path, dump = self.instance_dump(instance, extractors)
            dumps[instance.name] = (dump_path, dump)

            instance.data["dumpPath"] = dump_path

        if not dumps:
            self.log.info("Nothing to dump.")
            return

        # Get context dump path
        root = self.get_filesys_dir(context)
        outpath = self.CONTEXT_DUMP.format(filesys=root,
                                           user=dump_user,
                                           oid=dump_id)

        for name, (dump_path, dump) in dumps.items():
            dump["contextDump"] = outpath

            with open(dump_path, "w") as file:
                json_dump(dump, file)
            self.log.debug("Instance %s dumped to '%s'" % (name, dump_path))

        # Dump context
        self.log.info("Dumping context ..")

        dump = {
            "by": dump_user,
            "from": context.data["currentMaking"],
            "date": lib.avalon_id_timestamp(dump_id),
            "comment": context.data["comment"],
            "instances": [
                {
                    "id": instance.id,
                    "name": instance.name,
                    "asset": instance.data["asset"],
                    "subset": instance.data["subset"],
                    "family": instance.data["family"],
                    "families": instance.data.get("families", []),
                    "version": instance.data["versionNext"],
                    "dependencies": instance.data.get("dependencies", dict()),
                    "dump": dumps[instance.name][0],
                    "childInstances": [
                        c.id for c in instance.data.get("childInstances", [])
                    ],
                }
                for instance in instances if instance.name not in skip_ins
            ],
        }

        outdir = os.path.dirname(outpath)
        if not os.path.isdir(outdir):
            os.makedirs(outdir)

        with open(outpath, "w") as file:
            json_dump(dump, file)
        self.log.debug("Context dumped to '%s'" % outpath)

    def instance_dump(self, instance, extractors):

        instance.data["dumpedExtractors"] = list()

        # Dump extractors
        for repr_name, extractor in extractors:

            func = extractor["func"]
            args = extractor.get("args", list())
            kwargs = extractor.get("kwargs", dict())

            dump = {
                "class": func.im_class.__name__,
                "func": func.__name__,
                "args": args,
                "kwargs": kwargs,
            }

            stage_dir = instance.data["repr.%s._stage" % repr_name]
            outpath = self.EXTRACTOR_DUMP.format(stage=stage_dir)

            if not os.path.isdir(stage_dir):
                os.makedirs(stage_dir)

            with open(outpath, "w") as file:
                json_dump(dump, file)

            instance.data["dumpedExtractors"].append(outpath)

        # Dump instance
        dump = {
            "contextDump": None,  # Wait for context dump
            "id": instance.id,
        }

        # Include optional data if present in (version data)
        optionals = [
            "reprRoot",
            "startFrame",
            "endFrame",
            "step",
            "handles",
            "hasUnversionedSurfaces",
        ]
        for key in optionals:
            if key in instance.data:
                dump[key] = instance.data[key]

        # Representation data
        for key in instance.data:
            if not key.startswith("repr."):
                continue

            if key.endswith("._delayRun"):
                continue

            dump[key] = instance.data[key]

        version_dir = instance.data["versionDir"]
        outpath = self.INSTANCE_DUMP.format(version=version_dir)
        outpath = outpath.replace("\\", "/")

        return outpath, dump

    def get_filesys_dir(self, context):
        session = avalon.Session.copy()
        app = filesys.Filesys()
        env = app.environ(session)

        return env["AVALON_WORKDIR"].replace("\\", "/")
