import os
import subprocess

import avalon.api
from reveries.plugins import PackageLoader


class OpenInRV(PackageLoader, avalon.api.Loader):
    """Load the model"""

    label = "Open in RV"
    order = -15
    icon = "film"
    color = "#56a6db"

    families = [
        "reveries.rig"
    ]

    representations = [
        "Review",
    ]

    def load(self, context, name, namespace, data):
        self.log.info('image_dir: {}'.format(self.package_path))

        if not os.listdir(self.package_path):
            self.log.error('{} is empty directory.'.format(self.package_path))
            raise RuntimeError('{} is empty directory.'.format(self.package_path))

        rv_exe = r'C:/Program Files/Shotgun/RV-7.7.0/bin/rv.exe'

        cmd = [rv_exe, self.package_path]
        print('open rv cmd: {}'.format(cmd))

        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
