from odoo import models, fields, api
from odoo.exceptions import ValidationError


class LmsEnrollment(models.Model):
    _name = 'lms.enrollment'
    _description = 'LMS Student Course Enrollment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'enrollment_date desc'
    _rec_name = 'display_name'

    student_id = fields.Many2one(
        'lms.student', string='Student', required=True,
        ondelete='cascade', tracking=True
    )
    course_id = fields.Many2one(
        'lms.course', string='Course', required=True,
        ondelete='cascade', tracking=True
    )
    enrollment_date = fields.Date(
        string='Enrollment Date',
        default=fields.Date.today,
        tracking=True
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('enrolled', 'Enrolled'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
    ], string='Status', default='pending', tracking=True)

    grade = fields.Selection([
        ('A+', 'A+ (Exceptional)'),
        ('A', 'A (Excellent)'),
        ('B+', 'B+ (Very Good)'),
        ('B', 'B (Good)'),
        ('C+', 'C+ (Above Average)'),
        ('C', 'C (Average)'),
        ('D', 'D (Below Average)'),
        ('F', 'F (Fail)'),
    ], string='Final Grade', tracking=True)

    attendance_percent = fields.Float(
        string='Attendance %',
        compute='_compute_attendance_percent',
        store=True,
        tracking=True
    )

    @api.depends('student_id', 'course_id')
    def _compute_attendance_percent(self):
        for rec in self:
            if not rec.course_id or not rec.student_id:
                rec.attendance_percent = 0.0
                continue
            try:
                total_sessions = self.env['lms.attendance.session'].search_count([
                    ('course_id', '=', rec.course_id.id),
                    ('state', '=', 'done')
                ])
                if total_sessions > 0:
                    present_count = self.env['lms.attendance.line'].search_count([
                        ('student_id', '=', rec.student_id.id),
                        ('course_id', '=', rec.course_id.id),
                        ('status', '=', 'present'),
                        ('session_id.state', '=', 'done')
                    ])
                    rec.attendance_percent = (present_count / total_sessions) * 100
                else:
                    rec.attendance_percent = 0.0
            except Exception:
                rec.attendance_percent = 0.0

    notes = fields.Text(string='Notes')

    display_name = fields.Char(
        compute='_compute_display_name', store=True
    )

    @api.depends('student_id', 'course_id')
    def _compute_display_name(self):
        for rec in self:
            student = rec.student_id.name or ''
            course = rec.course_id.name or ''
            rec.display_name = f'{student} → {course}'

    @api.constrains('student_id', 'course_id')
    def _check_unique_enrollment(self):
        for rec in self:
            duplicate = self.search([
                ('student_id', '=', rec.student_id.id),
                ('course_id', '=', rec.course_id.id),
                ('id', '!=', rec.id),
                ('state', 'not in', ['dropped']),
            ])
            if duplicate:
                raise ValidationError(
                    f'{rec.student_id.name} is already enrolled in '
                    f'{rec.course_id.name}!'
                )

    def action_enroll(self):
        self.state = 'enrolled'
        self._send_email('lms_student.lms_email_enrollment_confirmed')

    def action_complete(self):
        self.state = 'completed'
        self._send_email('lms_student.lms_email_enrollment_completed')

    def action_drop(self):
        self.state = 'dropped'
        self._send_email('lms_student.lms_email_enrollment_dropped')

    def _send_attendance_warning_email(self):
        """Send a warning or critical alert if attendance is below threshold."""
        for rec in self:
            if not rec.student_id.email:
                continue
            pct = rec.attendance_percent
            if pct < 50.0:
                tmpl = self.env.ref(
                    'lms_student.lms_email_attendance_critical', raise_if_not_found=False
                )
            elif pct < 75.0:
                tmpl = self.env.ref(
                    'lms_student.lms_email_attendance_warning', raise_if_not_found=False
                )
            else:
                continue
            if tmpl:
                tmpl.send_mail(rec.id, force_send=True)

    def _send_email(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for rec in self:
                if rec.student_id.email:
                    template.send_mail(rec.id, force_send=True)
