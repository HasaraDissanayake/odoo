from odoo import models, fields, api


class LmsCourse(models.Model):
    _name = 'lms.course'
    _description = 'LMS Course'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    name = fields.Char(string='Course Name', required=True, tracking=True)
    code = fields.Char(string='Course Code', required=True, tracking=True)
    description = fields.Html(string='Description')
    credits = fields.Integer(string='Credits', default=3)
    duration_weeks = fields.Integer(string='Duration (Weeks)', default=12)

    instructor_id = fields.Many2one(
        'res.users', string='Instructor', tracking=True
    )
    category = fields.Selection([
        ('science', 'Science'),
        ('arts', 'Arts'),
        ('commerce', 'Commerce'),
        ('technology', 'Technology'),
        ('language', 'Language'),
        ('other', 'Other'),
    ], string='Category', default='other', tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', tracking=True)

    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    max_students = fields.Integer(string='Max Students', default=30)

    enrollment_ids = fields.One2many(
        'lms.enrollment', 'course_id', string='Enrolled Students'
    )
    enrolled_count = fields.Integer(
        compute='_compute_enrolled_count', string='Enrolled', store=True
    )

    image = fields.Image(string='Course Image', max_width=512, max_height=256)

    @api.depends('enrollment_ids')
    def _compute_enrolled_count(self):
        for rec in self:
            rec.enrolled_count = len(
                rec.enrollment_ids.filtered(lambda e: e.state == 'enrolled')
            )

    def action_publish(self):
        self.state = 'published'
        template = self.env.ref(
            'lms_student.lms_email_course_published', raise_if_not_found=False
        )
        if template:
            for course in self:
                for enrollment in course.enrollment_ids.filtered(
                    lambda e: e.state == 'enrolled' and e.student_id.email
                ):
                    template.send_mail(enrollment.id, force_send=True)

    def action_archive_course(self):
        self.state = 'archived'

    def action_reset_draft(self):
        self.state = 'draft'
