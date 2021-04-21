# Copy from plugins/maya/publish/submit_deadline_publish

import os
import copy
import json
import platform
import pyblish.api


class DeadlinePublish(pyblish.api.ContextPlugin):
    """Publish via running script on Deadline

    Submitting jobs per instance group to deadline.

    """

    # order = pyblish.api.ExtractorOrder + 0.492
    # hosts = ["maya"]
    # label = "Deadline Publish"
    #
    # targets = ["deadline"]

    RENDER_TYPES = [
        "reveries.renderlayer",
    ]

    SCRIPT_SEQUENCE_TYPES = [
        "reveries.standin",
        "reveries.rsproxy",
    ]

    def process(self, context):
        import reveries

        if not all(result["success"] for result in context.data["results"]):
            self.log.warning("Atomicity not held, aborting.")
            return

        reveries_path = reveries.__file__

        # Context data

        username = context.data["user"]
        comment = context.data.get("comment", "")
        project = context.data["projectDoc"]

        fpath = context.data["currentMaking"]
        workspace = context.data["workspaceDir"]
        maya_version = context.data["mayaVersion"]

        project_id = str(project["_id"])[-4:].upper()
        project_code = project["data"].get("codename") or project_id
        fname = os.path.basename(fpath)

        # Instance data

        for instance in context:
            if instance.data["family"] not in \
                    context.data.get("support_families", []):
                continue

            if not instance.data.get("publish", True):
                continue

            if instance.data.get("isDependency"):
                continue

            if not instance.data.get("dumpedExtractors"):
                continue

            asset = instance.data["assetDoc"]["name"]
            subset = instance.data["subset"]
            version = instance.data["versionNext"]

            batch_name = "({projcode}): [{asset}] {filename}".format(
                projcode=project_code,
                asset=asset,
                filename=fname
            )

            deadline_pool = instance.data["deadlinePool"]
            deadline_prio = instance.data["deadlinePriority"]
            deadline_group = instance.data.get("deadlineGroup")

            frame_per_task = instance.data.get("deadlineFramesPerTask", 1)

            try:
                frame_start = int(instance.data["startFrame"])
                frame_end = int(instance.data["endFrame"])
                frame_step = int(instance.data["step"])

            except KeyError:
                frames = None
            else:
                frames = "{start}-{end}x{step}".format(
                    start=frame_start,
                    end=frame_end,
                    step=frame_step,
                )

            job_name = "{subset} v{version:0>3}".format(
                subset=subset,
                version=version,
            )

            if instance.data.get("deadlineSuspendJob", False):
                init_state = "Suspended"
            else:
                init_state = "Active"

            # Assemble payload

            payload = {
                "JobInfo": {
                    "Plugin": instance.data.get("deadline_plugin", "MayaBatch"),
                    "BatchName": batch_name,  # Top-level group name
                    "Name": job_name,
                    "UserName": username,
                    "MachineName": platform.node(),
                    "Comment": comment,
                    "Pool": deadline_pool,
                    "Group": deadline_group,
                    "Priority": deadline_prio,

                    "InitialStatus": init_state,

                    "ExtraInfo0": project["name"],
                    # "Whitelist": "mare1-01"  # platform.node().lower()
                },

                # Mandatory for Deadline, may be empty
                "AuxFiles": [],
                "IdOnly": True
            }

            # Add dependency for pointcache usd
            if instance.data.get("deadline_dependency", False):
                payload = self._add_dependency_for_usd_pointcache(
                    instance, payload)

            if instance.data.get("hasYeti"):
                # Change Deadline group for Yeti
                payload["JobInfo"]["Group"] = "yeti_render"

            # Environment
            #

            payload = self.set_environment(instance, payload, reveries_path)

            # About to submit...
            #

            if instance.data["family"] in self.RENDER_TYPES:
                # Render Job
                output_dir = context.data["outputDir"]
                has_renderlayer = context.data["hasRenderLayers"]
                use_rendersetup = context.data["usingRenderSetup"]

                output_prefix = instance.data["fileNamePrefix"]
                renderlayer = instance.data["renderlayer"]
                renderer = instance.data["renderer"]

                payload["JobInfo"]["Frames"] = frames
                payload["JobInfo"]["ChunkSize"] = frame_per_task

                payload["PluginInfo"] = {
                    # Input
                    "SceneFile": fpath,
                    # Resolve relative references
                    "ProjectPath": workspace,
                    # Mandatory for Deadline
                    "Version": maya_version,
                    # Output directory and filename
                    "OutputFilePath": output_dir,
                    "OutputFilePrefix": output_prefix,

                    "UsingRenderLayers": has_renderlayer,
                    "UseLegacyRenderLayers": not use_rendersetup,
                    "RenderLayer": renderlayer,
                    "Renderer": renderer,
                }

                def parse_output_path(outpaths):
                    output_path_keys = dict()
                    for count, outpath in enumerate(outpaths.values()):
                        head, tail = os.path.split(outpath)
                        output_path_keys["OutputDirectory%d" % count] = head
                        output_path_keys["OutputFilename%d" % count] = tail

                    return output_path_keys

                stereo_pairs = instance.data.get("stereo")
                if stereo_pairs is None:
                    # Normal render
                    rendercam = instance.data["camera"]
                    outpaths = instance.data["outputPaths"]

                    output_path_keys = parse_output_path(outpaths)
                    payload["JobInfo"].update(output_path_keys)
                    payload["PluginInfo"]["Camera"] = rendercam

                    self.submit_instance(context, instance, payload)

                else:
                    # Stereo render
                    stereo_outputs = instance.data["outputPaths"]
                    left = True
                    for cam, out in zip(stereo_pairs, stereo_outputs):
                        side = "  [L]" if left else "  [R]"
                        stereo_payload = copy.deepcopy(payload)

                        output_path_keys = parse_output_path(out)
                        stereo_payload["JobInfo"].update(output_path_keys)
                        stereo_payload["JobInfo"]["Name"] += side
                        stereo_payload["PluginInfo"]["Camera"] = cam

                        self.submit_instance(context, instance, stereo_payload)
                        left = False

            else:
                # Script Job

                if instance.data["family"] in self.SCRIPT_SEQUENCE_TYPES:
                    # Extract in sequence
                    payload["JobInfo"]["Frames"] = frames
                    payload["JobInfo"]["ChunkSize"] = frame_per_task

                    head, tail = os.path.split(instance.data["outputPath"])
                    payload["JobInfo"].update({
                        "OutputDirectory0": head,
                        "OutputFilename0": tail,
                    })

                script_file = os.path.join(os.path.dirname(reveries_path),
                                           "scripts",
                                           "deadline_extract.py")

                payload["PluginInfo"] = {
                    "ScriptJob": True,
                    "ScriptFilename": script_file,
                    # Input
                    "SceneFile": fpath,
                    # Resolve relative references
                    "ProjectPath": workspace,
                    # Mandatory for Deadline
                    "Version": maya_version,
                }

                # Extra plugin info
                extra_key = [
                    "USD_Version",
                    "USD_FilePath",
                    "USD_Output_Path",
                    "USD_Camera_Name",
                    "USD_FrameRange",
                    "ScriptFile",
                    "Version"  # Python/USD version
                ]
                for _key in extra_key:
                    if _key in instance.data.keys():
                        payload["PluginInfo"][_key] = instance.data[_key]

                self.submit_instance(context, instance, payload)

        context.data["_submitted"] = True

    def _add_dependency_for_usd_pointcache(self, instance, payload):
        _child_indexs = []

        for _instance in instance.data.get("deadline_dependency", []):
            if "deadline_index" in list(_instance.data.keys()):
                _child_indexs.append(_instance.data.get("deadline_index", ""))
        if _child_indexs:
            dependency_list = {
                "JobDependencies": ",".join(_child_indexs)
            }
            payload["JobInfo"].update(dependency_list)
        return payload

    def submit_instance(self, context, instance, payload):
        self.log.info("Submitting.. %s" % instance)
        self.log.info(json.dumps(
            payload, indent=4, sort_keys=True)
        )
        submitter = context.data["deadlineSubmitter"]
        index = submitter.add_job(payload)
        instance.data["deadline_index"] = index

    def assemble_environment(self, instance):
        """Compose submission required environment variables for instance

        Return:
            environment (dict): A set of remote variables, return `None` if
                instance is not assigning to remote site or publish is
                disabled.

        """
        submitter = instance.context.data["deadlineSubmitter"]
        environment = submitter.environment()

        # From current environment
        for var in [
            "MAYA_MODULE_PATH",
            "ARNOLD_PLUGIN_PATH",
        ]:
            environment[var] = os.getenv(var, "")

        dumped = instance.data["dumpedExtractors"]
        for child in instance.data.get("childInstances", []):
            dumped += child.data["dumpedExtractors"]

        environment["PYBLISH_EXTRACTOR_DUMPS"] = ";".join(dumped)
        environment["PYBLISH_DUMP_FILE"] = instance.data["dumpPath"]

        # Post task scripts
        post_task = list()
        if instance.data.get("setupProgressivePublish"):
            post_task.append("publish_by_task")
        if instance.data.get("notifyLocalSync"):
            post_task.append("emit_changes")
        environment["AVALON_POST_TASK_SCRIPTS"] = ";".join(post_task)

        if instance.data.get("SKIP_AvalonJobIntegrator", False):
            environment["SKIP_AvalonJobIntegrator"] = True

        return environment

    def set_environment(self, instance, payload, reveries_path):

        if instance.data.get("deadline_plugin", "") in ["USDrecord"]:
            parsed_environment = {
                "EnvironmentKeyValue0": r"PATH=Q:\\Resource\\USD-21.02\\lib;Q:\\Resource\\USD-21.02\\bin;T:\\third-party\\python27;T:\\third-party\\python27\\Scrip",
                "EnvironmentKeyValue1": r'PYTHONPATH=Q:\Resource\USD-21.02\lib\python'
            }
            payload["JobInfo"].update(parsed_environment)

        else:
            environment = self.assemble_environment(instance)
            if environment.get("AVALON_POST_TASK_SCRIPTS"):
                script_file = os.path.join(os.path.dirname(reveries_path),
                                           "scripts",
                                           "post_task",
                                           "_chained.py")
                payload["JobInfo"]["PostTaskScript"] = script_file

            if instance.data.get("hasAtomsCrowds"):
                # Change Deadline group for AtomsCrowd
                payload["JobInfo"]["Group"] = "atomscrowd"
            else:
                # AtomsCrowd module path is available for every machine by
                # default, so we must remove it if this renderLayer does
                # not require AtomsCrowd plugin. Or the license will not
                # be enough for other job that require Atoms.
                module_path = environment["MAYA_MODULE_PATH"]
                filtered = list()
                for path in module_path.split(";"):
                    if "AtomsMaya" not in path:
                        filtered.append(path)
                environment["MAYA_MODULE_PATH"] = ";".join(filtered)

            parsed_environment = {
                "EnvironmentKeyValue%d" % index: u"{key}={value}".format(
                    key=key,
                    value=environment[key]
                ) for index, key in enumerate(environment)
            }
            payload["JobInfo"].update(parsed_environment)

        return payload