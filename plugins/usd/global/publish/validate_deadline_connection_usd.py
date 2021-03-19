
import os
import subprocess
import pyblish.api
import avalon.api as api
from avalon.vendor import requests

from reveries.deadline import deadline_connection


class ValidateDeadlineConnectionUSD(deadline_connection.DeadlineConnection,
                                    pyblish.api.InstancePlugin):
    """Validate Deadline Web Service is running"""

    label = "Deadline Connection(USD)"
    order = pyblish.api.ValidatorOrder + 0.140

    families = [
        r'reveries.rig.review'
    ]

    def process(self, instance):
        # Actually, this instance is context a
        context = instance

        _ = super(ValidateDeadlineConnectionUSD, self).process(context)
