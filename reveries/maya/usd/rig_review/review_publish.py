import os
import json

from avalon import io


class USDReviewPublish(object):
    def __init__(self):
        dumps = os.environ["PYBLISH_EXTRACTOR_DUMPS"].split(";")
        for path in dumps:
            with open(path, "r") as file:
                instance_data = json.load(file)
        print('instance data: ', instance_data)

        args = instance_data["args"][0]

        self.review_dir = args['review_dir']
        self.review_subset_name = args['subset']
        self.asset_id = io.ObjectId(args['assetDoc']['_id'])

        self._check_render_result()
        self._get_rig_subset_id()

        self._update_db()

    def _get_rig_subset_id(self):
        rig_subset_name = self.review_subset_name.split('Review')[0]

        _filter = {'name': rig_subset_name, 'parent': self.asset_id}
        rig_data = io.find_one(_filter)
        self.rig_subset_id = rig_data['_id']

    def _update_db(self):
        from reveries.common.publish import publish_representation

        # Publish Review representation - rigDefault #
        print('Update db')
        rig_version_data = io.find_one(
            {'parent': self.rig_subset_id, 'type': 'version'},
            sort=[("name", -1)])
        rig_version_id = rig_version_data['_id']

        name = 'Review'
        reps_files = self.get_publish_files()
        reps_id = publish_representation.publish(
            rig_version_id, name, reps_files,
            delete_source=False,
        )
        print('{} reps_id: {}'.format(name, reps_id))

        # Update version review data
        if reps_id and reps_id:
            version_filter = {'_id': rig_version_id, 'type': 'version'}
            update = {'data.review.status': 'pending'}
            io.update_many(version_filter, update={'$set': update})

    def _check_render_result(self):
        if not os.listdir(self.review_dir):
            raise RuntimeError(
                'Render failed: {} is empty directory.'.format(self.review_dir))

    def get_publish_files(self):
        reps_files = [os.path.join(self.review_dir, f)
                      for f in os.listdir(self.review_dir)
                      if os.path.isfile(os.path.join(self.review_dir, f))]
        return reps_files


if __name__ == "__main__":
    io.install()
    publisher = USDReviewPublish()
