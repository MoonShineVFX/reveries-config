import os
import shutil

from avalon import io, api


def publish(version_id, name, publish_files, delete_source=False, **kwargs):
    """
    Publish representations.
    :param version_id: (obj/str) Version id
    :param name: (str) Representation name
    :param publish_files: (list) Publish files.
        [
            r'C:/Users/rebeccalin209/tmp/24f2/asset_prim.usda',
            r'C:/Users/rebeccalin209/tmp/24f2/subAsset_data.json'
        ]
    :param delete_source: (bool) Delete dir of publish files
    :param kwargs: (dict) Other args.
        {
            'entryFileName': 'asset_prim.usda'
        }
    :return: Representation id
    """

    _data = kwargs.get('data', {})

    # Check representation exists
    _filter = {
        'type': 'representation',
        'name': name,
        'parent': version_id,
    }
    reps_data = io.find_one(_filter)
    if reps_data:
        reps_id = reps_data['_id']
    else:
        representations_context = {
            'data': _data,
            'schema': 'avalon-core:representation-2.0'
        }
        representations_context.update(_filter)
        reps_id = io.insert_one(representations_context).inserted_id

    # Copy files
    if reps_id:
        pub_dir = _create_folder(version_id, name)
        for _files in publish_files:
            if os.path.isfile(_files):
                dst = os.path.join(pub_dir, os.path.basename(_files))
                _copy_file(_files, dst)
            else:
                continue

        if delete_source:
            for _files in publish_files:
                if os.path.exists(os.path.dirname(_files)):
                    shutil.rmtree(os.path.dirname(_files))
        return reps_id

    return False


def _create_folder(version_id, name):
    project = io.find_one({"name": api.Session["AVALON_PROJECT"],
                           "type": "project"})
    publish_template = project["config"]["template"]["publish"]

    version_data = _get_version_data(version_id)
    subset_data = _get_subset_data(version_data['parent'])
    asset_data = _get_asset_data(subset_data['parent'])

    _dir = publish_template.format(**{
        "root": api.registered_root(),
        "project": project["name"],
        "asset": asset_data["name"],
        "silo": asset_data["silo"],
        "subset": subset_data["name"],
        "version": version_data["name"],
        "representation": name,
    })

    if not os.path.exists(_dir):
        try:
            os.makedirs(_dir)
            os.chmod(_dir, 777)
        except Exception as e:
            print('makedir error: ', e)
    return _dir


def _copy_file(src, dst):
    try:
        shutil.copy2(src, dst)
    except OSError:
        msg = "An unexpected error occurred."
        raise OSError(msg)


def _get_asset_data(asset_id):
    _filter = {
        'type': 'asset',
        '_id': asset_id
    }
    return io.find_one(_filter)


def _get_subset_data(subset_id):
    _filter = {
        'type': 'subset',
        '_id': subset_id
    }
    return io.find_one(_filter)


def _get_version_data(version_id):
    _filter = {
        'type': 'version',
        '_id': version_id
    }
    return io.find_one(_filter)
