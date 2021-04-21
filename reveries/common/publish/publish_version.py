import getpass

from avalon import io, api


def publish(subset_id, **kwargs):
    # Check publish version name
    version_name = kwargs.get('version_name', None)
    if not version_name:
        _filter = {
            "type": "version",
            "parent": io.ObjectId(subset_id)
        }
        version_data = io.find_one(_filter, sort=[("name", -1)])
        if version_data:
            version_name = int(version_data['name']) + 1
        else:
            version_name = 1

    # Get publish value
    source = kwargs.get('source', '')
    work_dir = kwargs.get('work_dir', '')
    task = kwargs.get('task', api.Session.get("AVALON_TASK"))
    dependencies = kwargs.get('dependencies', {})
    dependents = kwargs.get('dependents', {})
    comment = kwargs.get('comment', 'Publish')
    review_data = kwargs.get('review', {})

    # Generate version context
    version_context = {
        'name': version_name,
        'parent': subset_id,
        'type': 'version',
        'locations': ['http://127.0.0.1'],
        'data': {
            'comment': comment,
            'source': source,
            'task': task,
            'workDir': work_dir,
            'author': getpass.getuser(),
            'time': api.time(),
            'dependencies': dependencies,
            'dependents': dependents
        },
        'schema': 'avalon-core:version-3.0'
    }

    if review_data:
        version_context['data'].update(review_data)

    version_id = io.insert_one(version_context).inserted_id
    return version_id
