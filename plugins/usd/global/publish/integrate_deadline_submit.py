# Copy from plugins/global/publish/submit_deadline

import pyblish.api


class SubmitDeadlineJobsUSD(pyblish.api.InstancePlugin):

    order = pyblish.api.IntegratorOrder + .15
    label = "Submit To Deadline(USD)"

    families = [
        r'reveries.rig.review'
    ]

    def process(self, instance):
        context = instance.context

        if not all(result["success"] for result in context.data["results"]):
            self.log.warning("Atomicity not held, aborting.")
            return

        submitter = context.data["deadlineSubmitter"]
        submitter.submit()
