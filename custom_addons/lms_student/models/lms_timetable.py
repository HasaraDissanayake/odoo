from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class LmsTimetable(models.Model):
    _name = 'lms.timetable'
    _description = 'LMS Timetable'
    _order = 'date asc, time_start asc'
    # No mail.thread — keeps the form clean, no chatter noise

    name = fields.Char(string='Title', compute='_compute_name', store=True)

    type = fields.Selection([
        ('lecture', 'Lecture'),
        ('exam',    'Exam'),
    ], string='Type', required=True, default='lecture')

    course_id   = fields.Many2one('lms.course', string='Course',   required=True)
    lecturer_id = fields.Many2one('res.users',  string='Lecturer / Invigilator')
    room        = fields.Char(string='Room / Venue')

    date        = fields.Date(string='Date', required=True)
    day_of_week = fields.Char(string='Day',  compute='_compute_day', store=True)

    time_start   = fields.Float(string='Start Time', required=True)
    time_end     = fields.Float(string='End Time',   required=True)
    time_display = fields.Char(string='Time', compute='_compute_time_display', store=True)

    academic_year = fields.Char(
        string='Academic Year',
        default=lambda self: self._default_academic_year(),
    )
    semester = fields.Selection([
        ('1', 'Semester 1'),
        ('2', 'Semester 2'),
        ('3', 'Summer'),
    ], string='Semester', default='1')

    notes = fields.Text(string='Notes / Instructions')
    state = fields.Selection([
        ('draft',     'Draft'),
        ('published', 'Published'),
    ], string='Status', default='draft')

    # ── computed ────────────────────────────────────────────────

    @api.depends('type', 'course_id', 'date')
    def _compute_name(self):
        labels = {'lecture': 'Lecture', 'exam': 'Exam'}
        for rec in self:
            parts = [
                labels.get(rec.type, ''),
                rec.course_id.name if rec.course_id else '',
                str(rec.date) if rec.date else '',
            ]
            rec.name = ' — '.join(p for p in parts if p)

    @api.depends('date')
    def _compute_day(self):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday']
        for rec in self:
            rec.day_of_week = days[rec.date.weekday()] if rec.date else ''

    @api.depends('time_start', 'time_end')
    def _compute_time_display(self):
        for rec in self:
            rec.time_display = '%s – %s' % (
                self._fmt(rec.time_start),
                self._fmt(rec.time_end),
            )

    @staticmethod
    def _fmt(t):
        h = int(t)
        m = int(round((t - h) * 60))
        return '%02d:%02d' % (h, m)

    def _default_academic_year(self):
        from datetime import date
        y = date.today().year
        return '%d/%d' % (y, y + 1)

    # ── constraints ─────────────────────────────────────────────

    @api.constrains('time_start', 'time_end')
    def _check_times(self):
        for rec in self:
            if rec.time_end <= rec.time_start:
                raise ValidationError(_('End Time must be after Start Time.'))

    # ── actions ─────────────────────────────────────────────────

    def action_publish(self):
        for rec in self:
            rec.state = 'published'
            rec._send_timetable_email()

    def action_draft(self):
        self.state = 'draft'

    # ── email ────────────────────────────────────────────────────

    def _send_timetable_email(self):
        for rec in self:
            enrollments = self.env['lms.enrollment'].search([
                ('course_id', '=', rec.course_id.id),
                ('state',     '=', 'enrolled'),
            ])
            if not enrollments:
                return

            type_label   = 'Exam Schedule' if rec.type == 'exam' else 'Lecture Timetable'
            header_color = '#c0392b'       if rec.type == 'exam' else '#1565C0'
            icon         = '&#128221;'     if rec.type == 'exam' else '&#128197;'
            lec_label    = 'Invigilator'   if rec.type == 'exam' else 'Lecturer'
            lecturer_name = rec.lecturer_id.name if rec.lecturer_id else 'TBA'

            notes_row = (
                '<tr><td style="padding:6px 12px;color:#777;">Notes</td>'
                '<td style="padding:6px 12px;"><b>%s</b></td></tr>' % rec.notes
            ) if rec.notes else ''

            for enr in enrollments:
                email = enr.student_id.email
                if not email:
                    continue
                body = """
<div style="font-family:Arial,sans-serif;max-width:580px;margin:auto;
            border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
  <div style="background:%(hc)s;padding:20px 24px;color:#fff;">
    <div style="font-size:22px;font-weight:700;">%(icon)s %(tl)s</div>
    <div style="font-size:14px;margin-top:4px;opacity:0.9;">%(course)s</div>
  </div>
  <div style="padding:20px 24px;">
    <p style="color:#555;margin-top:0;">
      Dear <b>%(student)s</b>,<br>
      A %(tl_lower)s entry has been published. Please note the details below.
    </p>
    <table style="width:100%%;border-collapse:collapse;background:#f9f9f9;
                  border-radius:6px;overflow:hidden;">
      <tr style="background:%(hc)s;color:#fff;">
        <td colspan="2" style="padding:8px 12px;font-weight:700;">Schedule Details</td>
      </tr>
      <tr><td style="padding:6px 12px;color:#777;width:38%%;">Course</td>
          <td style="padding:6px 12px;"><b>%(course)s</b></td></tr>
      <tr style="background:#fff;">
          <td style="padding:6px 12px;color:#777;">Type</td>
          <td style="padding:6px 12px;"><b>%(tl)s</b></td></tr>
      <tr><td style="padding:6px 12px;color:#777;">Date</td>
          <td style="padding:6px 12px;"><b>%(date)s (%(day)s)</b></td></tr>
      <tr style="background:#fff;">
          <td style="padding:6px 12px;color:#777;">Time</td>
          <td style="padding:6px 12px;"><b>%(time)s</b></td></tr>
      <tr><td style="padding:6px 12px;color:#777;">Room / Venue</td>
          <td style="padding:6px 12px;"><b>%(room)s</b></td></tr>
      %(notes_row)s
    </table>
    <p style="color:#aaa;font-size:12px;margin-bottom:0;margin-top:16px;">
      Automated notification from the LMS — please do not reply.
    </p>
  </div>
</div>""" % {
                    'hc':       header_color,
                    'icon':     icon,
                    'tl':       type_label,
                    'tl_lower': type_label.lower(),
                    'course':   rec.course_id.name,
                    'student':  enr.student_id.name,
                    'date':     str(rec.date),
                    'day':      rec.day_of_week or '',
                    'time':     rec.time_display or '',
                    'room':     rec.room or 'TBA',
                    'll':       lec_label,
                    'lecturer': lecturer_name,
                    'notes_row': notes_row,
                }
                self.env['mail.mail'].sudo().create({
                    'subject':   '%s: %s — %s' % (type_label, rec.course_id.name, rec.date),
                    'body_html': body,
                    'email_to':  email,
                    'author_id': self.env.user.partner_id.id,
                }).send()


# ── Wizard ──────────────────────────────────────────────────────────────────

class LmsTimetableWizard(models.TransientModel):
    _name = 'lms.timetable.wizard'
    _description = 'Add Timetable Entry'

    type = fields.Selection([
        ('lecture', 'Lecture'),
        ('exam',    'Exam'),
    ], string='Type', required=True, default='lecture')

    course_id   = fields.Many2one('lms.course', string='Course',   required=True)
    lecturer_id = fields.Many2one('res.users',  string='Lecturer / Invigilator',
                                  default=lambda self: self.env.user)
    room        = fields.Char(string='Room / Venue')
    date        = fields.Date(string='Date', required=True, default=fields.Date.today)
    time_start  = fields.Float(string='Start Time', required=True, default=9.0)
    time_end    = fields.Float(string='End Time',   required=True, default=11.0)

    academic_year = fields.Char(
        string='Academic Year',
        default=lambda self: self._default_year(),
    )
    semester = fields.Selection([
        ('1', 'Semester 1'),
        ('2', 'Semester 2'),
        ('3', 'Summer'),
    ], string='Semester', default='1')

    notes       = fields.Text(string='Notes / Special Instructions')
    publish_now = fields.Boolean(
        string='Publish & Notify Students Immediately',
        default=True,
    )

    def _default_year(self):
        from datetime import date
        y = date.today().year
        return '%d/%d' % (y, y + 1)

    @api.constrains('time_start', 'time_end')
    def _check_times(self):
        for rec in self:
            if rec.time_end <= rec.time_start:
                raise ValidationError(_('End Time must be after Start Time.'))

    def action_save(self):
        self.ensure_one()
        entry = self.env['lms.timetable'].create({
            'type':          self.type,
            'course_id':     self.course_id.id,
            'lecturer_id':   self.lecturer_id.id if self.lecturer_id else False,
            'room':          self.room,
            'date':          self.date,
            'time_start':    self.time_start,
            'time_end':      self.time_end,
            'academic_year': self.academic_year,
            'semester':      self.semester,
            'notes':         self.notes,
        })

        msg = ''
        if self.publish_now:
            entry.action_publish()
            msg = 'Entry published — students have been notified by email.'
        else:
            msg = 'Entry saved as draft. Open it from the list to publish later.'

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   'Timetable Entry Saved',
                'message': msg,
                'type':    'success',
                'sticky':  False,
                'next':    {'type': 'ir.actions.act_window_close'},
            },
        }
