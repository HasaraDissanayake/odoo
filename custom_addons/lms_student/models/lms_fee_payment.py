from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class LmsFeePayment(models.Model):
    _name = 'lms.fee.payment'
    _description = 'LMS Fee Payment'
    _order = 'due_date asc, id desc'

    name = fields.Char(
        string='Reference', readonly=True, copy=False, default='New'
    )

    # ── Core details (set by admin) ──────────────────────────────────────────
    student_id = fields.Many2one(
        'lms.student', string='Student', required=True, ondelete='cascade'
    )
    course_id  = fields.Many2one('lms.course', string='Course')
    fee_type   = fields.Selection([
        ('tuition',      'Tuition Fee'),
        ('exam',         'Exam Fee'),
        ('registration', 'Registration Fee'),
        ('library',      'Library Fee'),
        ('other',        'Other'),
    ], string='Fee Type', required=True, default='tuition')

    amount      = fields.Float(string='Amount Due', required=True, digits=(10, 2))
    academic_year = fields.Char(
        string='Academic Year',
        default=lambda self: self._default_year(),
    )
    semester    = fields.Selection([
        ('1', 'Semester 1'),
        ('2', 'Semester 2'),
        ('3', 'Summer'),
    ], string='Semester', default='1')
    due_date    = fields.Date(string='Due Date')
    description = fields.Text(string='Description / Instructions')

    # ── Student submission ───────────────────────────────────────────────────
    slip_url        = fields.Char(string='Payment Slip Link')
    payment_notes   = fields.Text(string='Payment Notes')
    submitted_date  = fields.Datetime(string='Submitted On', readonly=True)

    # ── Admin review ─────────────────────────────────────────────────────────
    admin_remarks = fields.Text(string='Admin Remarks')
    verified_date = fields.Datetime(string='Reviewed On', readonly=True)
    verified_by   = fields.Many2one('res.users', string='Reviewed By', readonly=True)

    # ── Status ───────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',     'Pending Payment'),
        ('submitted', 'Slip Submitted'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('paid',      'Paid'),
    ], string='Status', default='draft')

    # ── Computed helpers ─────────────────────────────────────────────────────
    is_overdue = fields.Boolean(compute='_compute_is_overdue', string='Overdue', store=True)

    @api.depends('due_date', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for rec in self:
            rec.is_overdue = (
                bool(rec.due_date)
                and rec.due_date < today
                and rec.state not in ('paid',)
            )

    def _default_year(self):
        from datetime import date
        y = date.today().year
        return '%d/%d' % (y, y + 1)

    # ── Sequence ─────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('lms.fee.payment')
                    or 'FEE'
                )
        return super().create(vals_list)

    # ── Student action ────────────────────────────────────────────────────────
    def action_submit(self):
        for rec in self:
            if not rec.slip_url:
                raise UserError(
                    _('Please paste your payment slip link (Google Drive / '
                      'OneDrive / Dropbox) before submitting.')
                )
            rec.state = 'submitted'
            rec.submitted_date = fields.Datetime.now()
            rec._email_submission_confirmation()
            rec._email_admin_new_submission()

    # ── Admin actions ─────────────────────────────────────────────────────────
    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted payments can be approved.'))
            rec.state = 'approved'
            rec.verified_date = fields.Datetime.now()
            rec.verified_by   = self.env.user
            rec._email_student_approved()

    def action_reject(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted payments can be rejected.'))
            rec.state = 'rejected'
            rec.verified_date = fields.Datetime.now()
            rec.verified_by   = self.env.user
            rec._email_student_rejected()

    def action_mark_paid(self):
        for rec in self:
            rec.state = 'paid'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'
            rec.slip_url       = False
            rec.payment_notes  = False
            rec.submitted_date = False
            rec.verified_date  = False
            rec.verified_by    = False

    # ── Emails ────────────────────────────────────────────────────────────────

    def _send(self, subject, body_html, email_to, email_cc=None):
        mail_vals = {
            'subject':   subject,
            'body_html': body_html,
            'email_to':  email_to,
            'author_id': self.env.user.partner_id.id,
        }
        if email_cc:
            mail_vals['email_cc'] = email_cc
        self.env['mail.mail'].sudo().create(mail_vals).send()

    def _email_submission_confirmation(self):
        """Confirm to student (and guardian) that slip was received."""
        for rec in self:
            if not rec.student_id.email:
                continue
            body = """
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
            border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
  <div style="background:#1565C0;padding:18px 24px;color:#fff;">
    <div style="font-size:20px;font-weight:700;">&#128203; Payment Slip Received</div>
  </div>
  <div style="padding:20px 24px;">
    <p>Dear <b>%(student)s</b>,</p>
    <p>Your payment slip for <b>%(ref)s</b> has been submitted successfully
    and is now under review.</p>
    <table style="width:100%%;border-collapse:collapse;background:#f9f9f9;
                  border-radius:6px;margin:12px 0;">
      <tr><td style="padding:7px 12px;color:#777;width:40%%;">Reference</td>
          <td style="padding:7px 12px;"><b>%(ref)s</b></td></tr>
      <tr style="background:#fff;">
          <td style="padding:7px 12px;color:#777;">Fee Type</td>
          <td style="padding:7px 12px;"><b>%(ftype)s</b></td></tr>
      <tr><td style="padding:7px 12px;color:#777;">Amount</td>
          <td style="padding:7px 12px;"><b>%(amount).2f</b></td></tr>
      <tr style="background:#fff;">
          <td style="padding:7px 12px;color:#777;">Submitted</td>
          <td style="padding:7px 12px;"><b>%(submitted)s</b></td></tr>
    </table>
    <p style="color:#555;">You will receive another email once your payment is verified.</p>
    <p style="color:#aaa;font-size:12px;">Automated notification — please do not reply.</p>
  </div>
</div>""" % {
                'student':   rec.student_id.name,
                'ref':       rec.name,
                'ftype':     dict(rec._fields['fee_type'].selection).get(rec.fee_type, ''),
                'amount':    rec.amount,
                'submitted': str(rec.submitted_date)[:16] if rec.submitted_date else '',
            }
            self._send('Payment Slip Submitted — %s' % rec.name, body,
                       rec.student_id.email,
                       email_cc=rec.student_id.guardian_email or None)

    def _email_admin_new_submission(self):
        """Notify admin/company when a student submits a slip."""
        admin_email = self.env.company.email
        if not admin_email:
            return
        for rec in self:
            body = """
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
            border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
  <div style="background:#e65100;padding:18px 24px;color:#fff;">
    <div style="font-size:20px;font-weight:700;">&#128276; New Payment Slip Submitted</div>
  </div>
  <div style="padding:20px 24px;">
    <p>A student has submitted a payment slip for review.</p>
    <table style="width:100%%;border-collapse:collapse;background:#f9f9f9;border-radius:6px;margin:12px 0;">
      <tr><td style="padding:7px 12px;color:#777;width:40%%;">Reference</td>
          <td style="padding:7px 12px;"><b>%(ref)s</b></td></tr>
      <tr style="background:#fff;">
          <td style="padding:7px 12px;color:#777;">Student</td>
          <td style="padding:7px 12px;"><b>%(student)s</b></td></tr>
      <tr><td style="padding:7px 12px;color:#777;">Fee Type</td>
          <td style="padding:7px 12px;"><b>%(ftype)s</b></td></tr>
      <tr style="background:#fff;">
          <td style="padding:7px 12px;color:#777;">Amount</td>
          <td style="padding:7px 12px;"><b>%(amount).2f</b></td></tr>
      <tr><td style="padding:7px 12px;color:#777;">Slip Link</td>
          <td style="padding:7px 12px;"><a href="%(slip)s">View Slip</a></td></tr>
    </table>
    <p style="color:#aaa;font-size:12px;">Please log in to the LMS to approve or reject.</p>
  </div>
</div>""" % {
                'ref':     rec.name,
                'student': rec.student_id.name,
                'ftype':   dict(rec._fields['fee_type'].selection).get(rec.fee_type, ''),
                'amount':  rec.amount,
                'slip':    rec.slip_url or '#',
            }
            self._send('New Payment Slip — %s (%s)' % (rec.student_id.name, rec.name),
                       body, admin_email)

    def _email_student_approved(self):
        """Notify student and guardian that payment is approved."""
        for rec in self:
            if not rec.student_id.email:
                continue
            body = """
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
            border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
  <div style="background:#2e7d32;padding:18px 24px;color:#fff;">
    <div style="font-size:20px;font-weight:700;">&#10004; Payment Approved</div>
  </div>
  <div style="padding:20px 24px;">
    <p>Dear <b>%(student)s</b>,</p>
    <p>Your payment slip for <b>%(ref)s</b> has been <b style="color:#2e7d32;">approved</b>.</p>
    <table style="width:100%%;border-collapse:collapse;background:#f9f9f9;border-radius:6px;margin:12px 0;">
      <tr><td style="padding:7px 12px;color:#777;width:40%%;">Reference</td>
          <td style="padding:7px 12px;"><b>%(ref)s</b></td></tr>
      <tr style="background:#fff;">
          <td style="padding:7px 12px;color:#777;">Fee Type</td>
          <td style="padding:7px 12px;"><b>%(ftype)s</b></td></tr>
      <tr><td style="padding:7px 12px;color:#777;">Amount</td>
          <td style="padding:7px 12px;"><b>%(amount).2f</b></td></tr>
      %(remarks_row)s
    </table>
    <p style="color:#aaa;font-size:12px;">Automated notification — please do not reply.</p>
  </div>
</div>""" % {
                'student':     rec.student_id.name,
                'ref':         rec.name,
                'ftype':       dict(rec._fields['fee_type'].selection).get(rec.fee_type, ''),
                'amount':      rec.amount,
                'remarks_row': (
                    '<tr style="background:#fff;"><td style="padding:7px 12px;color:#777;">Remarks</td>'
                    '<td style="padding:7px 12px;">%s</td></tr>' % rec.admin_remarks
                ) if rec.admin_remarks else '',
            }
            self._send('Payment Approved — %s' % rec.name, body,
                       rec.student_id.email,
                       email_cc=rec.student_id.guardian_email or None)

    def _email_student_rejected(self):
        """Notify student and guardian that payment is rejected."""
        for rec in self:
            if not rec.student_id.email:
                continue
            body = """
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;
            border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
  <div style="background:#c62828;padding:18px 24px;color:#fff;">
    <div style="font-size:20px;font-weight:700;">&#10007; Payment Rejected</div>
  </div>
  <div style="padding:20px 24px;">
    <p>Dear <b>%(student)s</b>,</p>
    <p>Unfortunately, your payment slip for <b>%(ref)s</b> has been
    <b style="color:#c62828;">rejected</b>. Please review the admin remarks
    below and resubmit a correct slip.</p>
    <table style="width:100%%;border-collapse:collapse;background:#f9f9f9;border-radius:6px;margin:12px 0;">
      <tr><td style="padding:7px 12px;color:#777;width:40%%;">Reference</td>
          <td style="padding:7px 12px;"><b>%(ref)s</b></td></tr>
      %(remarks_row)s
    </table>
    <p style="color:#555;font-size:13px;">
      Please log in to the LMS, upload a correct slip and resubmit.
    </p>
    <p style="color:#aaa;font-size:12px;">Automated notification — please do not reply.</p>
  </div>
</div>""" % {
                'student':     rec.student_id.name,
                'ref':         rec.name,
                'remarks_row': (
                    '<tr style="background:#fff;"><td style="padding:7px 12px;color:#777;">Reason</td>'
                    '<td style="padding:7px 12px;"><b>%s</b></td></tr>' % rec.admin_remarks
                ) if rec.admin_remarks else '',
            }
            self._send('Payment Rejected — %s' % rec.name, body,
                       rec.student_id.email,
                       email_cc=rec.student_id.guardian_email or None)
