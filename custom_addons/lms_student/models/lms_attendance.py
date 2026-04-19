from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class LmsAttendanceSession(models.Model):
    _name = 'lms.attendance.session'
    _description = 'LMS Attendance Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default='New')
    course_id = fields.Many2one('lms.course', string='Course', required=True, tracking=True)
    date = fields.Date(string='Date', default=fields.Date.today, required=True, tracking=True)
    lecturer_id = fields.Many2one('res.users', string='Lecturer', default=lambda self: self.env.user, tracking=True)
    attendance_line_ids = fields.One2many('lms.attendance.line', 'session_id', string='Attendance Lines', copy=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Confirmed')
    ], string='Status', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('lms.attendance.session') or 'ATS'
        return super().create(vals_list)

    def action_confirm(self):
        for rec in self:
            if not rec.attendance_line_ids:
                raise ValidationError(_("Please add attendance lines before confirming."))
            rec.state = 'done'

            # Trigger recompute for enrolled students in this course
            enrollments = self.env['lms.enrollment'].search([
                ('course_id', '=', rec.course_id.id),
                ('state', '=', 'enrolled')
            ])
            for enrollment in enrollments:
                enrollment._compute_attendance_percent()

            # Send absence notifications for students marked absent this session
            rec._send_absence_emails()

            # Send attendance warnings based on updated percentages
            for enrollment in enrollments:
                enrollment._send_attendance_warning_email()


    def _send_absence_emails(self):
        """Send an absence notification to every student marked absent in this session."""
        template = self.env.ref(
            'lms_student.lms_email_absence_recorded', raise_if_not_found=False
        )
        if not template:
            return
        for line in self.attendance_line_ids.filtered(lambda l: l.status == 'absent'):
            if line.student_id.email:
                template.send_mail(line.id, force_send=True)

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'
            # Trigger recompute for enrolled students in this course
            enrollments = self.env['lms.enrollment'].search([
                ('course_id', '=', rec.course_id.id),
                ('state', '=', 'enrolled')
            ])
            for enrollment in enrollments:
                enrollment._compute_attendance_percent()


    @api.onchange('course_id')
    def _onchange_course_id(self):
        if self.course_id:
            lines = []
            enrollments = self.env['lms.enrollment'].search([
                ('course_id', '=', self.course_id.id),
                ('state', '=', 'enrolled')
            ])
            for enrollment in enrollments:
                lines.append((0, 0, {
                    'student_id': enrollment.student_id.id,
                    'status': 'present',
                }))
            self.attendance_line_ids = [(5, 0, 0)] + lines


class LmsAttendanceLine(models.Model):
    _name = 'lms.attendance.line'
    _description = 'LMS Attendance Line'

    session_id = fields.Many2one('lms.attendance.session', string='Session', ondelete='cascade', required=True)
    student_id = fields.Many2one('lms.student', string='Student', required=True)
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent')
    ], string='Status', default='present', required=True)
    
    course_id = fields.Many2one(related='session_id.course_id', store=True, string='Course')
    date = fields.Date(related='session_id.date', store=True, string='Date')
