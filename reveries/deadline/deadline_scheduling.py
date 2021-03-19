# Copy from plugins/global/publish/validate_deadline_scheduling

import pyblish.api


class DeadlineScheduling(pyblish.api.ContextPlugin):

    # label = "Deadline Scheduling"
    # order = pyblish.api.ValidatorOrder + 0.2
    # targets = ["deadline"]

    def process(self, context):
        invalid = set()

        for instance in context:
            if instance.data["family"] not in \
                    context.data.get("support_families", []):
                continue

            if not instance.data.get("publish", True):
                continue

            if "deadlinePriority" in instance.data:
                invalid.add(self.check_priority(instance))

            if "deadlinePool" in instance.data:
                invalid.add(self.check_pool(instance))

        if any(invalid):
            raise Exception("Invalid Deadline settings.")

    def check_priority(self, instance):
        priority_limit = 80
        priority = instance.data["deadlinePriority"]
        if not priority <= priority_limit:
            self.log.error("[%s]: Deadline priority should not be greater "
                           "than %d." % (instance, priority_limit))
            return True

    def check_pool(self, instance):
        pool = instance.data["deadlinePool"]
        if pool == "none":
            self.log.error("[%s]: Deadline pool did not set." % instance)
            return True
