from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LmsAttendanceWizard(models.TransientModel):
    _name = 'lms.attendance.wizard'
    _description = 'Record Attendance Wizard'

    course_id = fields.Many2one('lms.course', string='Course', required=True)
    date = fields.Date(string='Class Date', default=fields.Date.today, required=True)
    lecturer_id = fields.Many2one(
        'res.users', string='Lecturer', default=lambda self: self.env.user
    )
    line_ids = fields.One2many('lms.attendance.wizard.line', 'wizard_id', string='Students')

    present_count = fields.Integer(compute='_compute_counts')
    absent_count = fields.Integer(compute='_compute_counts')
    total_count = fields.Integer(compute='_compute_counts')

    @api.depends('line_ids', 'line_ids.is_present')
    def _compute_counts(self):
        for rec in self:
            rec.total_count = len(rec.line_ids)
            rec.present_count = len(rec.line_ids.filtered('is_present'))
            rec.absent_count = rec.total_count - rec.present_count

    @api.onchange('course_id')
    def _onchange_course_id(self):
        if not self.course_id:
            self.line_ids = [(5, 0, 0)]
            return
        enrollments = self.env['lms.enrollment'].search([
            ('course_id', '=', self.course_id.id),
            ('state', '=', 'enrolled'),
        ], order='id asc')
        self.line_ids = [(5, 0, 0)] + [
            (0, 0, {'student_id': e.student_id.id, 'is_present': True})
            for e in enrollments
        ]

    def action_mark_all_present(self):
        self.line_ids.write({'is_present': True})
        return self._reopen()

    def action_mark_all_absent(self):
        self.line_ids.write({'is_present': False})
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_save_attendance(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please select a course — no students are loaded yet.'))

        # Guard against duplicate session for same course + date
        existing = self.env['lms.attendance.session'].search([
            ('course_id', '=', self.course_id.id),
            ('date', '=', self.date),
        ], limit=1)
        if existing:
            raise UserError(_(
                'An attendance session already exists for %s on %s.\n'
                'Open "View All Sessions" to edit it.'
            ) % (self.course_id.name, self.date))

        session = self.env['lms.attendance.session'].create({
            'course_id': self.course_id.id,
            'date': self.date,
            'lecturer_id': self.lecturer_id.id,
        })
        for line in self.line_ids:
            self.env['lms.attendance.line'].create({
                'session_id': session.id,
                'student_id': line.student_id.id,
                'status': 'present' if line.is_present else 'absent',
            })
        session.action_confirm()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Attendance Saved'),
                'message': _(
                    'Attendance for %s on %s has been recorded. '
                    'Present: %d  |  Absent: %d'
                ) % (self.course_id.name, self.date,
                     self.present_count, self.absent_count),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class LmsAttendanceWizardLine(models.TransientModel):
    _name = 'lms.attendance.wizard.line'
    _description = 'Attendance Wizard Line'
    _order = 'student_id asc'

    wizard_id = fields.Many2one('lms.attendance.wizard', ondelete='cascade')
    student_id = fields.Many2one('lms.student', string='Student', required=True)
    student_code = fields.Char(
        related='student_id.student_id', string='Student ID', readonly=True
    )
    is_present = fields.Boolean(string='Present', default=True)
