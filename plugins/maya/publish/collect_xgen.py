
import pyblish.api
from maya import cmds
from reveries import plugins
from reveries.maya import lib, pipeline


def create_model_subset_from_xgen(instance):
    family = "reveries.model"
    subset = "modelXGenBoundMesh"
    member = cmds.listRelatives(instance.data["igsBoundMeshes"],
                                parent=True,
                                fullPath=True) or []
    plugins.create_dependency_instance(instance,
                                       subset,
                                       family,
                                       member,
                                       category="XGen Bound Mesh")


def create_look_subset_from_xgen(instance):
    family = "reveries.look"
    subset = "lookXGenHair"
    member = instance.data["igsDescriptions"]
    plugins.create_dependency_instance(instance,
                                       subset,
                                       family,
                                       member,
                                       category="XGen LookDev")


def create_texture_subset_from_look(instance, textures):
    family = "reveries.texture"
    subset = "textureXGenMaps"
    plugins.create_dependency_instance(instance,
                                       subset,
                                       family,
                                       textures,
                                       category="XGen Maps")


class CollectXGen(pyblish.api.InstancePlugin):
    """Collect xgen content and data
    """

    order = pyblish.api.CollectorOrder + 0.1  # run before look collector
    hosts = ["maya"]
    label = "Collect XGen"
    families = ["reveries.xgen"]

    def process(self, instance):
        getattr(self, instance.data["XGenType"])(instance)

    def get_interactive(self, instance):
        """Interactive Groom Spline"""

        # Inject shadow family
        instance.data["families"] = ["reveries.xgen.interactive"]

        descriptions = lib.list_lead_descriptions(instance[:])
        instance.data["igsDescriptions"] = descriptions

        bound_meshes = lib.list_bound_meshes(descriptions)
        instance.data["igsBoundMeshes"] = bound_meshes

        # Create model subset for bounding meshes
        create_model_subset_from_xgen(instance)

        # Create lookDev subset for hair
        create_look_subset_from_xgen(instance)

        # Create texture subet for descriptions
        stray = pipeline.find_stray_textures(cmds.listHistory(descriptions))
        if stray:
            create_texture_subset_from_look(instance, stray)

    def get_legacy(self, instance):
        """Legacy XGen"""

        # Inject shadow family
        instance.data["families"] = ["reveries.xgen.legacy"]

        palette = cmds.ls(instance, type="xgmPalette", long=True)
        if not palette:
            return

        descriptions = cmds.ls(instance, type="xgmDescription", long=True)
        if not descriptions:
            return

        # Not finished
