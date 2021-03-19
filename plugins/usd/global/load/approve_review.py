import getpass

import avalon.api
from avalon import io
from reveries.plugins import PackageLoader


class ApproveReview(PackageLoader, avalon.api.Loader):
    """Load the model"""

    label = 'Approve'
    order = -15
    icon = 'thumbs-up'
    color = r'#7cb342'

    families = [
        'reveries.rig'
    ]

    representations = [
        'Review',
    ]

    def load(self, context, name, namespace, data):
        from avalon.tools import loader

        reps_data = context['representation']

        # Check approve status
        version_filter = {'type': 'version', '_id': reps_data['parent']}
        version_data = io.find_one(version_filter)
        review_status = version_data['data'].get('review', {}).get('status', '')

        if str(review_status) == 'approved':
            self.log.info('Already approved.')
            return

        # Set to approve
        update = {
            'data.review.status': 'approved',
            'data.review.approved_by': getpass.getuser(),
        }
        io.update_many(version_filter, update={'$set': update})

        # Refresh loader UI
        loader.app.window.refresh()
