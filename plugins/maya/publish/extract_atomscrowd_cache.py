
import pyblish.api


class ExtractAtomsCrowdCache(pyblish.api.InstancePlugin):

    label = "Extract AtomsCrowd Cache"
    order = pyblish.api.ExtractorOrder
    hosts = ["maya"]
    families = ["reveries.atomscrowd"]

    def process(self, instance):
        from reveries import utils
        from AtomsMaya.hostbridge.commands import MayaCommandsHostBridge

        staging_dir = utils.stage_dir(dir=instance.data["_sharedStage"])

        start = int(instance.data["startFrame"])
        end = int(instance.data["endFrame"])

        # Get agentTypes
        agent_types = set()
        for node in instance.data["AtomsAgentGroups"]:
            agent_group = MayaCommandsHostBridge.get_agent_group(node)
            agent_types.update(agent_group.agentTypeMapper().keys())

        filename = "%s.atoms" % instance.data["subset"]  # Cache header
        agent_type = "agentTypes/%s.agentType"  # agentType file
        agent_script = "agentTypes/%s.py"  # Python event wrapper script
        frames = "%s.%%04d.%%s.atoms" % instance.data["subset"]  # Frame files
        variation = "%s.json" % instance.data["subset"]  # Crowd Variation
        # (NOTE) Atoms Crowd cache padding is always 4

        files = [frames % (f, x)
                 for f in range(start, end + 1)
                 for x in ("frame", "header", "meta", "pose")]
        files += [agent_type % agtype for agtype in agent_types]
        files += [agent_script % agtype for agtype in agent_types]
        files += [filename, variation]

        instance.data["repr.atoms._stage"] = staging_dir
        instance.data["repr.atoms._hardlinks"] = files
        instance.data["repr.atoms.entryFileName"] = filename
        instance.data["repr.atoms.variationFile"] = variation

        cache_dir = staging_dir
        cache_name = instance.data["subset"]

        agent_groups = instance.data["AtomsAgentGroups"]
        MayaCommandsHostBridge.export_atoms_cache(cache_dir,
                                                  cache_name,
                                                  start,
                                                  end,
                                                  agent_groups)

        variation_path = "%s/%s" % (staging_dir, variation)
        with open(variation_path, "w") as variation:
            variation.write(instance.data["variationStr"])
