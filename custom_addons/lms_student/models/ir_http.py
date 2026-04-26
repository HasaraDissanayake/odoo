from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        if not self.env.user._is_internal():
            return result

        # Inject the LMS live chat channel into the backend session so
        # the chatbot widget appears for teachers and managers.
        channel = self.env.ref(
            'lms_student.lms_livechat_channel',
            raise_if_not_found=False,
        )
        if not channel:
            return result

        info = channel.get_livechat_info(username=self.env.user.name)
        if info.get('available'):
            result['livechatData'] = {
                'can_load_livechat': True,
                'serverUrl': info['server_url'],
                'options': info['options'],
            }
        return result
