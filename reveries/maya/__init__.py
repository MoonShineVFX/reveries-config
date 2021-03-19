
import os
import sys
import logging
from avalon import api as avalon
import pyblish_qml.settings
from pyblish import api as pyblish
from maya import mel, cmds

from . import pipeline
from .. import PLUGINS_DIR
from ..utils import override_event

self = sys.modules[__name__]
self.installed = None

log = logging.getLogger("reveries.maya")

PUBLISH_PATH = os.path.join(PLUGINS_DIR, "maya", "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "maya", "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "maya", "create")
INVENTORY_PATH = os.path.join(PLUGINS_DIR, "maya", "inventory")

PYMEL_MOCK_FLAG = os.path.join(os.environ["MAYA_APP_DIR"], "pymel.mock")


def _override():
    import avalon.maya.commands as commands
    from .pipeline import has_turntable, set_scene_timeline, set_resolution

    # Override avalon.maya menu function
    log.info("Overriding <avalon.maya.commands.reset_frame_range>")
    _set_time = (lambda: set_scene_timeline(asset_name=has_turntable()))
    commands.reset_frame_range = _set_time
    log.info("Overriding <avalon.maya.commands.reset_resolution>")
    _set_res = (lambda: set_resolution(asset_name=has_turntable()))
    commands.reset_resolution = _set_res


def _override_deferred():
    from xgenm.ui.widgets.xgExpressionUI import ExpressionUI
    from .xgen import legacy

    # Override Maya XGen expression map string parser
    log.info("Overriding <xgenm.ui.widgets.xgExpressionUI.ExpressionUI."
             "ExpressionUI.parseMapString>")
    ExpressionUI.parseMapString = legacy._parseMapString_override


def install():  # pragma: no cover
    from avalon import io
    from . import menu, callbacks

    # install pipeline menu
    menu.install()
    # install pipeline plugins
    pyblish.register_plugin_path(PUBLISH_PATH)
    avalon.register_plugin_path(avalon.Loader, LOAD_PATH)
    avalon.register_plugin_path(avalon.Creator, CREATE_PATH)
    avalon.register_plugin_path(avalon.InventoryAction, INVENTORY_PATH)

    # Check USD pipeline
    project = io.find_one({"type": "project"})

    if project.get('usd_pipeline', False):
        pyblish.register_plugin_path(
            os.path.join(PLUGINS_DIR, "usd", "maya", "publish")
        )
        pyblish.register_plugin_path(
            os.path.join(PLUGINS_DIR, "usd", "global", "publish")
        )
        avalon.register_plugin_path(
            avalon.Creator,
            os.path.join(PLUGINS_DIR, "usd", "maya", "create")
        )
        avalon.register_plugin_path(
            avalon.InventoryAction,
            os.path.join(PLUGINS_DIR, "usd", "maya", "inventory")
        )
        avalon.register_plugin_path(
            avalon.Loader,
            os.path.join(PLUGINS_DIR, "usd", "global", "load")
        )
        avalon.register_plugin_path(
            avalon.Loader,
            os.path.join(PLUGINS_DIR, "usd", "maya", "load")
        )

    # install callbacks
    log.info("Installing callbacks ... ")
    avalon.on("init", callbacks.on_init)
    avalon.on("new", callbacks.on_new)
    avalon.on("open", callbacks.on_open)
    avalon.on("save", callbacks.on_save)
    avalon.before("save", callbacks.before_save)

    log.info("Overriding existing event 'taskChanged'")
    override_event("taskChanged", callbacks.on_task_changed)

    # Temporarily workaround
    # script node: uiConfigurationScriptNode
    # (TODO): Should try to cleanup that script node if possible...
    mel.eval("global proc CgAbBlastPanelOptChangeCallback(string $pass){}")
    log.info("Unknown proc <CgAbBlastPanelOptChangeCallback> "
             "workaround init.")
    mel.eval("global proc look(){}")
    log.info("Unknown proc <look> workaround init.")

    _override()

    cmds.evalDeferred("import reveries.maya;"
                      "reveries.maya._override_deferred()")

    # Maya 2020 renderSetup
    log.info("Disabling 'includeAllLights' for RenderSetup.")
    cmds.optionVar(intValue=["renderSetup_includeAllLights", 0])

    # Config Pyblish QML
    pyblish_qml.settings.Directions = {
        "Local Publish": {
            "awesomeIcon": "motorcycle",
            "description": "Publish from this computer",
            "targets": ["default", "localhost"],
        },
        "Deadline Publish": {
            "awesomeIcon": "rocket",
            "description": "Publish in Deadline render farm",
            "targets": ["default", "deadline"],
        },
    }

    self.installed = True


def uninstall():  # pragma: no cover
    from . import menu

    # uninstall pipeline menu
    menu.uninstall()
    # uninstall pipeline plugins
    pyblish.deregister_plugin_path(PUBLISH_PATH)
    avalon.deregister_plugin_path(avalon.Loader, LOAD_PATH)
    avalon.deregister_plugin_path(avalon.Creator, CREATE_PATH)

    # (TODO) uninstall callbacks

    self.installed = False


def collect_container_metadata(container):
    """Collect container additional data

    This will be called by `host.ls()`, which will parse container data and
    the data collected from this method.

    Args:
        container (str): container node name

    Returns:
        dict: Additional key-value dataset

    """
    return pipeline.container_metadata(container)
