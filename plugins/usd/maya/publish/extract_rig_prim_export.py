import os

import pyblish.api
from avalon import io


class ExtractRigPrimExport(pyblish.api.InstancePlugin):
    """Export rig primitive usd file
    """

    order = pyblish.api.ExtractorOrder + 0.201
    hosts = ['maya']
    label = r'Extract Rig Prim USD Export'
    families = [
        r'reveries.rig.usd'
    ]

    def process(self, instance):
        from reveries import utils
        from reveries.maya.usd import load_maya_plugin
        from reveries.maya.usd import rig_prim_export

        staging_dir = utils.stage_dir(dir=instance.data['_sharedStage'])

        file_name = 'rig_prim.usda'

        # Update information in instance data
        instance.data['repr.USD._stage'] = staging_dir
        instance.data['repr.USD._files'] = [file_name]
        instance.data['repr.USD.entryFileName'] = file_name

        load_maya_plugin()

        # Export rig prim usd
        output_path = os.path.join(staging_dir, file_name)

        exporter = rig_prim_export.RigPrimExporter(
            output_path,
            asset_name=instance.data['asset'],
            rig_subset_name=instance.data['subset'].replace('Prim', '')
        )
        exporter.export()

        self.log.info(r'Export rig prim usd done.')

        self._update_db(instance)

        self._publish_instance(instance)

    def _update_db(self, instance):
        _filter = {'type': 'asset', 'name': instance.data['asset']}
        asset_data = io.find_one(_filter)

        subset_filter = {
            'type': 'subset',
            'name': instance.data['subset'],
            'parent': asset_data['_id']
        }

        subset_data = [s for s in io.find(subset_filter)]

        if subset_data:
            subset_data = subset_data[0]

            if not subset_data['data'].get('subsetGroup', ''):
                update = {'data.subsetGroup': 'Rig'}
                io.update_many(subset_filter, update={r'$set': update})

    def _publish_instance(self, instance):
        # === Publish instance === #
        from reveries.common.publish import publish_instance

        publish_instance.run(instance)

        instance.data['_preflighted'] = True
