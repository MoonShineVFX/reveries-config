# Copy from plugins/global/publish/publish_deadline_submitter

import pyblish.api
from reveries.deadline.deadline_submitter import DeadlineSubmitter


class PublishDeadlineSubmitterUSD(pyblish.api.InstancePlugin):
    """Deadline 發佈機器人"""

    order = pyblish.api.ValidatorOrder + 0.142
    label = "Deadline Submitter(USD)"

    families = [
        r'reveries.rig.review'
    ]

    def process(self, instance):
        context = instance.context
        context.data["deadlineSubmitter"] = DeadlineSubmitter(context)
