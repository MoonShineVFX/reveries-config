from maya import cmds
import avalon.maya
from avalon import io, api

from reveries.maya.lib import TRANSFORM_ATTRS
from reveries.maya.pipeline import put_instance_icon


class RigCreator(avalon.maya.Creator):
    """Animatable Controller"""

    label = "Rig"
    family = "reveries.rig"
    icon = "sitemap"

    defaults = [
        "default",
        "Low",
        "Crowd",
        "XGen",
        "cloth",
    ]

    def build_base(self):
        if cmds.objExists("|ROOT"):
            return

        make_empty = not ((self.options or {}).get("useSelection") and
                          bool(cmds.ls(sl=True)))
        cmds.group(name="ROOT", empty=make_empty, world=True)

    def process(self):
        self.build_base()

        # For usd setting
        self.data["publishUSD"] = False
        project = io.find_one({"name": api.Session["AVALON_PROJECT"],
                               "type": "project"})

        if project.get('usd_pipeline', False):
            self.data["publishUSD"] = True

        self.data["subsetGroup"] = "Rig"

        instance = super(RigCreator, self).process()
        self.log.info("Creating Rig instance set up ...")

        for attr in TRANSFORM_ATTRS:
            cmds.setAttr("|ROOT." + attr, keyable=False)
        cmds.setAttr("|ROOT.visibility", keyable=False)

        sub_object_sets = ["OutSet", "ControlSet"]

        for set_name in sub_object_sets:
            cmds.sets(cmds.sets(name=set_name, empty=True),
                      forceElement=instance)

        return put_instance_icon(instance)
