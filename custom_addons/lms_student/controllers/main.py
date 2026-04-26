from odoo import http
from odoo.http import request


class LmsChatController(http.Controller):

    @http.route('/lms/chat', type='http', auth='user')
    def lms_chat(self, **kwargs):
        """Redirect to the built-in Odoo live chat support page for the LMS channel."""
        channel = request.env.ref(
            'lms_student.lms_livechat_channel',
            raise_if_not_found=False,
        )
        if not channel:
            return request.not_found()
        return request.redirect(f'/im_livechat/support/{channel.id}')
