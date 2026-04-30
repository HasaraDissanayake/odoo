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
    material_ids = fields.One2many(
        'lms.course.material', 'course_id', string='Course Materials'
    )
    submission_ids = fields.One2many(
        'lms.assignment.submission', 'course_id', string='Submissions'
    )
    notice_ids = fields.One2many(
        'lms.course.notice', 'course_id', string='Notices'
    )
    attendance_session_ids = fields.One2many(
        'lms.attendance.session', 'course_id', string='Attendance Sessions'
    )
    enrolled_count = fields.Integer(
        compute='_compute_enrolled_count', string='Enrolled', store=True
    )
    my_enrollment_state = fields.Selection(
        selection=[
            ('enrolled',     'Enrolled'),
            ('completed',    'Completed'),
            ('pending',      'Pending'),
            ('dropped',      'Dropped'),
            ('not_enrolled', 'Not Enrolled'),
        ],
        string='My Status',
        compute='_compute_my_enrollment_state',
    )

    image = fields.Image(string='Course Image', max_width=512, max_height=256)

    @api.depends('enrollment_ids')
    def _compute_enrolled_count(self):
        for rec in self:
            rec.enrolled_count = len(
                rec.enrollment_ids.filtered(lambda e: e.state == 'enrolled')
            )

    def _compute_my_enrollment_state(self):
        student = self.env['lms.student'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if student:
            enrollments = self.env['lms.enrollment'].search([
                ('student_id', '=', student.id),
                ('course_id', 'in', self.ids),
            ])
            enr_map = {e.course_id.id: e.state for e in enrollments}
        else:
            enr_map = {}
        for course in self:
            course.my_enrollment_state = enr_map.get(course.id, 'not_enrolled')

    def action_publish(self):
        self.state = 'published'
        template = self.env.ref(
            'lms_student.lms_email_course_published', raise_if_not_found=False
        )
        if template:
            for course in self:
                for enrollment in course.enrollment_ids.filtered(
                    lambda e: e.state == 'enrolled'
                ):
                    if enrollment.student_id.email:
                        email_values = {}
                        if enrollment.student_id.guardian_email:
                            email_values['email_cc'] = enrollment.student_id.guardian_email
                        template.send_mail(enrollment.id, force_send=True,
                                           email_values=email_values or None)

    def action_archive_course(self):
        self.state = 'archived'

    def action_reset_draft(self):
        self.state = 'draft'

    def action_open_notice_form(self):
        """Open a blank notice form pre-filled with this course (manager only)."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Notice',
            'res_model': 'lms.course.notice',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_course_id': self.id,
            },
        }

    def action_open_attendance_session(self):
        """Open a new attendance session form pre-filled with this course and enrolled students."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Record Attendance',
            'res_model': 'lms.attendance.session',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_course_id': self.id,
                'default_lecturer_id': self.env.uid,
            },
        }

    def action_open_submission_form(self):
        """Open a blank submission form for the current student, pre-filled with this course."""
        student = self.env['lms.student'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Submit Assignment',
            'res_model': 'lms.assignment.submission',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_course_id': self.id,
                'default_student_id': student.id if student else False,
            },
        }
