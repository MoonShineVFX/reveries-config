
import pyblish.api
from reveries.deadline.deadline_submitter import DeadlineSubmitter


class PublishDeadlineSubmitter(pyblish.api.ContextPlugin):
    """Deadline 發佈機器人"""

    order = pyblish.api.ExtractorOrder - 0.3
    label = "Deadline 發佈機器人"

    targets = ["deadline"]

    def process(self, context):

        context.data["deadlineSubmitter"] = DeadlineSubmitter(context)
