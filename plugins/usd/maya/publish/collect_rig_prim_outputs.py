from avalon import io
import pyblish.api


class CollectRigPrimOutputs(pyblish.api.InstancePlugin):

    order = pyblish.api.CollectorOrder + 0.25
    label = r'Collect Rig Prim USD Outputs'
    hosts = ['maya']
    families = [
        'reveries.rig'
    ]

    def ins_exists(self, context, name):
        _exists = False
        for instance in context:
            if instance.data['subset'] == name:
                _exists = True
                break
        return _exists

    def process(self, instance):
        if not instance.data.get('publishUSD', False):
            return

        subset_name = instance.data['subset']

        # Create new instance
        context = instance.context
        backup = instance

        # === Generate skeleton usd === #
        self._generate_new_subset(
            context, backup,
            subset_name='{}Skeleton'.format(subset_name),
            family='reveries.rig.skeleton',
            subset_group='USD'
        )
        # name = '{}Skeleton'.format(subset_name)
        # if not self.ins_exists(context, name):
        #     _family = "reveries.rig.skeleton"
        #
        #     _instance = context.create_instance(name)
        #     _instance.data.update(backup.data)
        #
        #     _instance.data["family"] = _family
        #     _instance.data["families"] = [_family]
        #     _instance.data["subset"] = name
        #     _instance.data["subsetGroup"] = "USD"

        # === Generate rigPrim usd === #
        self._generate_new_subset(
            context, backup,
            subset_name='{}Prim'.format(subset_name),
            family='reveries.rig.usd',
            version_pin=True
        )
        # name = '{}Prim'.format(subset_name)
        # if not self.ins_exists(context, name):
        #     _family = "reveries.rig.usd"
        #
        #     _instance = context.create_instance(name)
        #     _instance.data.update(backup.data)
        #
        #     _instance.data["family"] = _family
        #     _instance.data["families"] = [_family]
        #     _instance.data["subset"] = name
        #     self._check_version_pin(_instance, name)

        # === Generate review subset === #
        self._generate_new_subset(
            context, backup,
            subset_name='{}Review'.format(subset_name),
            family='reveries.rig.review',
            deadline_priority=5,
            deadline_pool='gpu',  # r'p1---less_than_60mins',
            subset_group='USD',
            instance_name='{}Review - Render'.format(subset_name)
        )

        # === Update review data information === #
        review = {
            'status': 'rendering',
            'approved_by': ''
        }
        instance.data['review'] = review

    def _generate_new_subset(
            self, context, backup,  subset_name=None, family=None,
            subset_group=None,
            version_pin=None,
            deadline_priority=None,
            deadline_pool=None,
            instance_name=None
    ):
        if not self.ins_exists(context, subset_name):
            _instance = context.create_instance(instance_name or subset_name)
            _instance.data.update(backup.data)

            _instance.data['family'] = family
            _instance.data['families'] = [family]
            _instance.data['subset'] = subset_name

            if subset_group:
                _instance.data['subsetGroup'] = subset_group

            if version_pin:
                self._check_version_pin(_instance, subset_name)

            if deadline_priority:
                _instance.data['deadlinePriority'] = deadline_priority

            if deadline_pool:
                _instance.data['deadlinePool'] = deadline_pool

    def _check_version_pin(self, instance, subset_name):
        shot_name = instance.data['asset']
        _filter = {'type': 'asset', 'name': shot_name}
        asset_data = io.find_one(_filter)

        # Get subset id
        _filter = {
            'type': 'subset',
            'parent': asset_data['_id'],
            'name': subset_name  # "camPrim"/"layPrim"/"finalPrim"
        }
        subset_data = io.find_one(_filter)
        if subset_data:
            # Get version name
            _filter = {
                'type': 'version',
                'parent': subset_data['_id'],
            }
            version_data = io.find_one(_filter, sort=[('name', -1)])
            if version_data:
                instance.data['versionPin'] = version_data['name']
