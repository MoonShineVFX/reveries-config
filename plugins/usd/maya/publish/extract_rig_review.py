import os

import pyblish.api

from reveries.maya.usd.rig_review import review_usd_export


class ExtractorRigUSDReview(pyblish.api.InstancePlugin):
    order = pyblish.api.ExtractorOrder + 0.4812
    hosts = ['maya']
    label = 'Extract Rig USD Review'

    families = [
        'reveries.rig.review'
    ]

    def process(self, instance):
        from reveries import utils

        # Export review usd
        staging_dir = utils.stage_dir(dir=instance.data['_sharedStage'])
        instance.data['repr.USD._stage'] = staging_dir

        builder = review_usd_export.RigReview(instance.data)
        instance.data['repr.USD.entryFileName'] = review_usd_export.RIG_REVIEWPRIM
        instance.data['repr.USD._files'] = builder.get_publish_files()

        # Create deadline job
        self.create_render_job(instance, builder)
        self.create_publish_job(instance)

        self._publish_instance(instance)

    def create_render_job(self, instance, builder):
        from reveries.common.utils import check_dir_exists

        # Set image dir
        review_dir = check_dir_exists(
            os.path.join(instance.data['repr.USD._stage'], 'review'))

        instance.data['skip_cleanup_stage'] = True
        instance.data['deadline_plugin'] = 'USDrecord'
        instance.data['USD_Version'] = review_usd_export.USD_VERSION
        instance.data['USD_FilePath'] = builder.review_usd_file
        instance.data['USD_Output_Path'] = os.path.join(review_dir, '###.exr')
        instance.data['USD_Camera_Name'] = instance.data['usdview_cam']
        instance.data['USD_FrameRange'] = '{}:{}x1'.format(
            review_usd_export.RENDER_RANGE[0],
            review_usd_export.RENDER_RANGE[1]
        )
        instance.data['review_dir'] = review_dir

        instance.data['to_deadline'] = True
        instance.data['_preflighted'] = True

        instance.data['repr.USD._delayRun'] = {
            'func': self.do_render,
            'args': [],
        }

    def create_publish_job(self, render_instance):
        from reveries.common.build_delay_run import DelayRunBuilder

        py_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..\\..\\..\\..\\reveries\\maya\\usd\\rig_review\\review_publish.py"
            )
        )

        # Add publish instance
        pub_ins = render_instance.context.create_instance(
            '{} - Publish'.format(render_instance.data['subset']))
        pub_ins.data.update(render_instance.data)
        pub_ins.data['_preflighted'] = True

        # Set deadline env
        pub_ins.data['deadline_plugin'] = 'Python'
        pub_ins.data['ScriptFile'] = py_path  # review_publish.py
        pub_ins.data['Version'] = '3.6'
        pub_ins.data['deadlinePool'] = 'p1---less_than_60mins'
        pub_ins.data['deadlinePriority'] = 10
        pub_ins.data['SKIP_AvalonJobIntegrator'] = True

        delay_builder = DelayRunBuilder(pub_ins)
        pub_ins.data['repr.USD._delayRun'] = {
            'func': self.do_review_publish,
            'args': [delay_builder.instance_data]
        }
        pub_ins.data['deadline_dependency'] = [render_instance]

    def do_render(self):
        pass

    def do_review_publish(self):
        pass

    def _publish_instance(self, instance):
        # === Publish instance === #
        from reveries.common.publish import publish_instance

        publish_instance.run(instance)

        instance.data['_preflighted'] = True
