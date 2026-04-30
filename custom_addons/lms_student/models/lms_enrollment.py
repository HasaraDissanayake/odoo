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

    def action_enroll_and_notify(self):
        for rec in self:
            rec.state = 'enrolled'
            rec._send_enrollment_email()

    def action_complete(self):
        self.state = 'completed'

    def action_drop(self):
        self.state = 'dropped'

    def _send_enrollment_email(self):
        for rec in self:
            body = """
                <div style="font-family:Arial,sans-serif; max-width:600px; margin:auto;">
                    <div style="background:#875A7B; padding:20px; border-radius:6px 6px 0 0;">
                        <h2 style="color:#fff; margin:0;">Enrollment Confirmed</h2>
                        <p style="color:#f0e6f6; margin:4px 0 0;">Learning Management System</p>
                    </div>
                    <div style="background:#fff; padding:24px; border:1px solid #ddd;
                                border-top:none; border-radius:0 0 6px 6px;">
                        <p>Dear <strong>%s</strong>,</p>
                        <p>You have been successfully enrolled in the following course:</p>
                        <div style="background:#f9f4fb; border-left:4px solid #875A7B;
                                    padding:12px 16px; margin:16px 0; border-radius:0 4px 4px 0;">
                            <strong style="font-size:16px;">%s</strong>
                        </div>
                        <p>Your enrollment date is <strong>%s</strong>.</p>
                        <p>Please log in to the student portal to view your course materials.</p>
                        <hr style="border:none; border-top:1px solid #eee; margin:16px 0;"/>
                        <p style="color:#888; font-size:12px; margin:0;">
                            This is an automated message from the Learning Management System.
                        </p>
                    </div>
                </div>
            """ % (
                rec.student_id.name,
                rec.course_id.name,
                rec.enrollment_date,
            )
            if not rec.student_id.email:
                continue
            mail_vals = {
                'subject':   'Enrollment Confirmed - %s' % rec.course_id.name,
                'body_html': body,
                'email_to':  rec.student_id.email,
                'author_id': self.env.user.partner_id.id,
            }
            if rec.student_id.guardian_email:
                mail_vals['email_cc'] = rec.student_id.guardian_email
            self.env['mail.mail'].sudo().create(mail_vals).send()
