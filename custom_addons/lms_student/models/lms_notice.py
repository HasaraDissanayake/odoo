from odoo import models, fields, api


class LmsCourseNotice(models.Model):
    _name = 'lms.course.notice'
    _description = 'Course Notice Board'
    _order = 'published_date desc, id desc'

    course_id = fields.Many2one(
        'lms.course', string='Course', required=True, ondelete='cascade'
    )
    title = fields.Char(string='Title', required=True)
    content = fields.Html(string='Content')
    state = fields.Selection([
        ('draft',     'Draft'),
        ('published', 'Published'),
    ], string='Status', default='draft')
    published_date = fields.Datetime(string='Published On', readonly=True)
    author_id = fields.Many2one(
        'res.users', string='Posted By',
        default=lambda self: self.env.user, readonly=True
    )

    def action_publish(self):
        for rec in self:
            rec.state = 'published'
            rec.published_date = fields.Datetime.now()
            rec._send_notice_emails()

    def action_reset_draft(self):
        self.state = 'draft'
        self.published_date = False

    def _send_notice_emails(self):
        """Send an email to every enrolled student in the course."""
        enrollments = self.course_id.enrollment_ids.filtered(
            lambda e: e.state == 'enrolled'
        )
        if not enrollments:
            return

        for enr in enrollments:
            email = enr.student_id.user_id.email
            if not email:
                continue

            body = f"""
                <div style="font-family:Arial,sans-serif; max-width:600px; margin:auto;">
                    <div style="background:#875A7B; padding:20px; border-radius:6px 6px 0 0;">
                        <h2 style="color:#fff; margin:0;">📢 Course Notice</h2>
                        <p style="color:#f0e6f6; margin:4px 0 0;">
                            {self.course_id.name}
                        </p>
                    </div>
                    <div style="background:#fff; padding:24px; border:1px solid #ddd;
                                border-top:none; border-radius:0 0 6px 6px;">
                        <p>Dear <strong>{enr.student_id.name}</strong>,</p>
                        <p>A new notice has been posted for your course
                           <strong>{self.course_id.name}</strong>:</p>
                        <hr style="border:none; border-top:1px solid #eee; margin:16px 0;"/>
                        <h3 style="color:#875A7B; margin-top:0;">{self.title}</h3>
                        <div style="line-height:1.6;">{self.content or ''}</div>
                        <hr style="border:none; border-top:1px solid #eee; margin:16px 0;"/>
                        <p style="color:#888; font-size:12px; margin:0;">
                            Posted by {self.author_id.name} &nbsp;|&nbsp;
                            {self.course_id.name}
                        </p>
                    </div>
                </div>
            """

            self.env['mail.mail'].sudo().create({
                'subject': f'[{self.course_id.name}] {self.title}',
                'body_html': body,
                'email_to': email,
                'author_id': self.env.user.partner_id.id,
            }).send()
