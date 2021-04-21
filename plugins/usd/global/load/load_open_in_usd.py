import os
import subprocess

import avalon.api
from reveries.plugins import PackageLoader


def env_embedded_path(path):
    """Embed environment var `$AVALON_PROJECTS` and `$AVALON_PROJECT` into path

    This will ensure reference or cache path resolvable when project root
    moves to other place.

    """
    path = path.replace(
        "$AVALON_PROJECTS", avalon.api.registered_root()
    )
    path = path.replace(
        "$AVALON_PROJECT", avalon.Session["AVALON_PROJECT"]
    )
    return path


class OpenInUSD(PackageLoader, avalon.api.Loader):
    """Load the model"""

    label = "Open in USD view"
    order = -15
    icon = "list"
    color = "#56a6db"

    # hosts = ["maya"]

    families = [
        "reveries.model",
        "reveries.pointcache",
        "reveries.look.asset_prim",
        "reveries.ani.ani_prim",
        "reveries.setdress.layer_prim",
        "reveries.setdress.usd",
        "reveries.layout.usd",
        "reveries.rig.usd",
        "reveries.skeletoncache",
        "reveries.rig.review"
    ]

    representations = [
        "USD",
    ]

    def _file_path(self, representation):
        file_name = representation["data"]["entryFileName"]
        entry_path = os.path.join(self.package_path, file_name)

        if not os.path.isfile(entry_path):
            raise IOError("File Not Found: {!r}".format(entry_path))

        return env_embedded_path(entry_path)

    def load(self, context, name, namespace, data):
        # Get usd file
        representation = context["representation"]
        entry_path = self._file_path(representation)
        usd_file = os.path.expandvars(entry_path).replace("/", "\\")

        if not usd_file:
            directory = self.package_path
            files = os.listdir(directory)
            if not files:
                self.log.info('No usd file found in : {}'.format(directory))
                return

            usd_file = os.path.join(directory, files[0]).replace("/", "\\")

        self._open_usdview(usd_file)

    def _open_usdview(self, usd_file):
        self.log.info('usd_file: {}'.format(usd_file))

        usdview_bat = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..\\..\\..\\usd\\template\\usdview.bat"
            )
        )

        if not os.path.exists(usdview_bat):
            self.log.info('usdview.bat file not exists.')
            return

        cmd = [usdview_bat, usd_file]
        print('open usdview cmd: {}'.format(cmd))
        popen = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        popen.communicate()  # For fix long print lock
