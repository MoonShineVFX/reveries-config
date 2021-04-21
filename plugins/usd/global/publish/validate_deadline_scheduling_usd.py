
import pyblish.api

from reveries.deadline import deadline_scheduling


class ValidateDeadlineSchedulingUSD(deadline_scheduling.DeadlineScheduling,
                                    pyblish.api.InstancePlugin):

    label = "Deadline Scheduling(USD)"
    order = pyblish.api.ValidatorOrder + 0.141

    families = [
        r'reveries.rig.review'
    ]

    def process(self, instance):
        # Actually, this instance is context a
        context = instance
        context.data["support_families"] = self.families

        _ = super(ValidateDeadlineSchedulingUSD, self).process(context)
