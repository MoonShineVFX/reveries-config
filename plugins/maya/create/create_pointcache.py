
import avalon.maya
from avalon import io, api

from reveries.maya.pipeline import put_instance_icon
from reveries import lib


class PointCacheCreator(avalon.maya.Creator):
    """Extract pointcache for deformable objects

    Extract cache for each loaded subset

    """

    label = "PointCache"
    family = "reveries.pointcache"
    icon = "diamond"

    def process(self):
        # Build pipeline render settings

        self.data["exportAlembic"] = True
        self.data["exportGPUCache"] = False
        self.data["exportFBXCache"] = False
        self.data["exportAniUSDData"] = False

        self.data["staticCache"] = False
        self.data["isDummy"] = False

        self.data["deadlinePriority"] = 80
        self.data["deadlinePool"] = lib.get_deadline_pools()

        # Apply Euler filter to rotations for Alembic
        self.data["eulerFilter"] = True

        # for nodes that are not in any OutSet
        self.data["tryTension"] = False
        self.data["tryRestPos"] = False

        # Check usd pipeline
        project = io.find_one({"name": api.Session["AVALON_PROJECT"],
                               "type": "project"})

        if project.get('usd_pipeline', False):
            self.data["exportAniUSDData"] = True

        return put_instance_icon(super(PointCacheCreator, self).process())
