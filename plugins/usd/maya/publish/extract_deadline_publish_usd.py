
import pyblish.api

from reveries.deadline.maya import deadline_publish


class ExtractDeadlinePublishUSD(deadline_publish.DeadlinePublish, pyblish.api.InstancePlugin):

    label = "Deadline Publish(USD)"
    order = pyblish.api.ExtractorOrder + 0.4991

    families = [
        r'reveries.rig.review'
    ]

    def process(self, instance):
        # Actually, this instance is context
        context = instance
        context.data["support_families"] = self.families

        if not context.data.get("_submitted", False):
            _ = super(ExtractDeadlinePublishUSD, self).process(context)
