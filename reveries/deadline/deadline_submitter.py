
import os
import re
import logging
import subprocess
import avalon.api
import avalon.io
from avalon.vendor import requests


class DeadlineSubmitter(object):

    def __init__(self, context):

        self.log = logging.getLogger(name="DeadlineSubmitter")

        self._jobs = dict()
        self._submitted = dict()

        self._cmd = None
        self._url = None
        self._auth = None
        self._environment = None

        if context.data.get("USE_DEADLINE_APP"):
            AVALON_DEADLINE_APP = avalon.api.Session["AVALON_DEADLINE_APP"]

            # E.g. C:/Program Files/Thinkbox/Deadline10/bin/deadlinecommand.exe
            self._cmd = AVALON_DEADLINE_APP

        else:
            AVALON_DEADLINE = avalon.api.Session["AVALON_DEADLINE"]

            # E.g. http://192.168.0.1:8082/api/jobs
            self._url = "{}/api/jobs".format(AVALON_DEADLINE)
            #
            # Documentation about RESTful api
            # https://docs.thinkboxsoftware.com/products/deadline/
            # 10.0/1_User%20Manual/manual/rest-jobs.html#rest-jobs-ref-label
            #
            # Documentation for keys available at:
            # https://docs.thinkboxsoftware.com
            #    /products/deadline/8.0/1_User%20Manual/manual
            #    /manual-submission.html#job-info-file-options

            self._auth = os.environ["AVALON_DEADLINE_AUTH"].split(":")

        # Save Session
        #
        environment = dict({
            # This will trigger `userSetup.py` on the slave
            # such that proper initialisation happens the same
            # way as it does on a local machine.
            # TODO(marcus): This won't work if the slaves don't
            # have accesss to these paths, such as if slaves are
            # running Linux and the submitter is on Windows.
            "PYTHONPATH": os.getenv("PYTHONPATH", ""),
            "AVALON_TOOLS": os.getenv("AVALON_TOOLS", ""),
        }, **avalon.api.Session)

        # From current environment (required)
        for var in [
            "PYBLISH_FILESYS_EXECUTABLE",
            "PYBLISH_FILESYS_SCRIPT",
        ]:
            try:
                environment[var] = os.environ[var]
            except KeyError:
                self.log.error("Required environ var '%s' missing." % var)
                raise KeyError("Missing important environment variable.")

        self._environment = environment

    def environment(self):
        return self._environment.copy()

    def add_job(self, payload):
        """Add job to queue and returns an index"""
        index = str(len(self._jobs))
        self._jobs[index] = payload
        return index

    def submit(self):
        """Submit all jobs"""
        while self._jobs:
            index, payload = self._jobs.popitem()
            self._pre_submit(index, payload)

    def _pre_submit(self, index, payload):
        deps = payload["JobInfo"].get("JobDependencies")
        if deps:
            dep_jobids = list()
            for _index in deps.split(","):
                if _index in self._submitted:
                    _jobid = self._submitted[_index]
                else:
                    _payload = self._jobs.pop(_index)
                    _jobid = self._pre_submit(_index, _payload)

                dep_jobids.append(_jobid)

            payload["JobInfo"]["JobDependencies"] = ",".join(dep_jobids)

        return self._submit(index, payload)

    def _submit(self, index, payload):
        # (NOTE) "Error: Alternate job auxiliary path <...> doesn't exist"
        #   If Deadline Repository has custom Auxiliary Files path that is
        #   set to a file server and you got this error, try re-connect the
        #   file server.
        if self._cmd:
            jobid = self._via_command(payload)
        else:
            jobid = self._via_web_service(payload)

        self._submitted[index] = jobid

        return jobid

    def _via_web_service(self, payload):
        response = requests.post(self._url,
                                 json=payload,
                                 auth=tuple(self._auth))

        if not response.ok:
            raise Exception(response.text)
        else:
            jobid = eval(response.text)["_id"]
            self.log.info("Success. JobID: %s" % jobid)
            return jobid

    def _via_command(self, payload):
        from reveries import utils

        def to_txt(document, out):
            # Write dict to key-value txt file
            with open(out, "w") as fp:
                for key, val in document.items():
                    fp.write("{key}={val}\n".format(key=key, val=val))

        job_info = payload["JobInfo"]
        plugin_info = payload["PluginInfo"]

        info_dir = utils.stage_dir(prefix="deadline_")
        job_info_file = os.path.join(info_dir, "job_info.job")
        plugin_info_file = os.path.join(info_dir, "plugin_info.job")

        to_txt(job_info, job_info_file)
        to_txt(plugin_info, plugin_info_file)

        cmd = self._cmd

        cmd += " %s %s" % (job_info_file, plugin_info_file)
        output = subprocess.check_output(cmd)

        output = output.decode("utf-8")
        if "Result=Success" not in output.split():
            raise Exception("Submission failed...")
        else:
            parts = re.split("[=\n\r]", output)
            jobid = parts[parts.index("JobID") + 1]
            self.log.info("Success. JobID: %s" % jobid)
            return jobid