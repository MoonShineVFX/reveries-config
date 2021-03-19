import os
from avalon import io


def get_fps():
    _filter = {"type": "project"}
    project_data = io.find_one(_filter) or {}

    _fps = project_data.get("data", {}).get("fps", 24.0)
    return _fps


def project_root_path(file_path):

    root = os.environ["AVALON_PROJECTS"]
    proj_name = os.environ["AVALON_PROJECT"]

    project_root = r'{}/{}'.format(root, proj_name)
    if "PROJECT_ROOT" not in os.environ.keys():
        os.environ["PROJECT_ROOT"] = project_root
    file_path = file_path.replace(project_root, "$PROJECT_ROOT")

    return file_path


def check_dir_exists(dir_path):
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)

    return dir_path
