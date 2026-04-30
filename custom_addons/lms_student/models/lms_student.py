import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class LmsStudent(models.Model):
    _name = 'lms.student'
    _description = 'LMS Student Profile'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'
    _student_id_unique = models.Constraint(
        'unique(student_id)', 'Student ID must be unique.'
    )

    # ── Basic Identity ──────────────────────────────────────────
    name = fields.Char(
        string='Full Name',
        required=True,
        tracking=True,
    )
    student_id = fields.Char(
        string='Student ID',
        copy=False,
        readonly=True,
        default=lambda self: 'New',
        tracking=True,
    )
    image = fields.Image(
        string='Profile Photo',
        max_width=256,
        max_height=256,
    )

    # ── Personal Details ────────────────────────────────────────
    date_of_birth = fields.Date(string='Date of Birth', tracking=True)
    age = fields.Integer(string='Age', compute='_compute_age', store=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ], string='Gender', tracking=True)
    nationality = fields.Many2one('res.country', string='Nationality')

    # ── Contact Info ────────────────────────────────────────────
    email = fields.Char(string='Email', required=True, tracking=True)
    phone = fields.Char(string='Phone', tracking=True)
    mobile = fields.Char(string='Mobile')
    address = fields.Text(string='Address')

    # ── Academic Info ───────────────────────────────────────────
    enrollment_date = fields.Date(
        string='Enrollment Date',
        default=fields.Date.today,
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('graduated', 'Graduated'),
        ('suspended', 'Suspended'),
    ], string='Status', default='draft', tracking=True)

    guardian_name  = fields.Char(string='Guardian Name')
    guardian_phone = fields.Char(string='Guardian Phone')
    guardian_email = fields.Char(string='Guardian Email')

    # ── Linked User ─────────────────────────────────────────────
    user_id = fields.Many2one(
        'res.users',
        string='Portal / Internal User',
        help='Link this student to an Odoo user account to enable their personal dashboard.',
        tracking=True,
    )

    # ── Relations ───────────────────────────────────────────────
    enrollment_ids = fields.One2many(
        'lms.enrollment', 'student_id', string='Enrollments'
    )
    academic_record_ids = fields.One2many(
        'lms.academic.record', 'student_id', string='Academic Records'
    )
    attendance_line_ids = fields.One2many(
        'lms.attendance.line', 'student_id', string='Attendance Records'
    )
    assessment_grade_ids = fields.One2many(
        'lms.assessment.grade', 'student_id', string='Assessment Grades'
    )

    enrollment_count = fields.Integer(
        compute='_compute_enrollment_count', string='Courses'
    )
    overall_attendance_percent = fields.Float(
        string='Overall Attendance (%)',
        compute='_compute_overall_attendance',
        store=True,
        digits=(5, 1),
    )
    low_attendance = fields.Boolean(
        string='Low Attendance',
        compute='_compute_overall_attendance',
        store=True,
        help='True when overall attendance is below 75%',
    )
    notes = fields.Html(string='Internal Notes')

    # ── Compute Methods ─────────────────────────────────────────
    @api.depends('date_of_birth')
    def _compute_age(self):
        today = fields.Date.today()
        for rec in self:
            if rec.date_of_birth:
                rec.age = (today - rec.date_of_birth).days // 365
            else:
                rec.age = 0

    @api.depends('enrollment_ids')
    def _compute_enrollment_count(self):
        for rec in self:
            rec.enrollment_count = len(rec.enrollment_ids)

    @api.depends('enrollment_ids.attendance_percent')
    def _compute_overall_attendance(self):
        for rec in self:
            percents = rec.enrollment_ids.mapped('attendance_percent')
            if percents:
                rec.overall_attendance_percent = sum(percents) / len(percents)
            else:
                rec.overall_attendance_percent = 0.0
            rec.low_attendance = rec.overall_attendance_percent < 75.0

    # ── Sequence ────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('student_id', 'New') == 'New':
                vals['student_id'] = self.env['ir.sequence'].next_by_code(
                    'lms.student'
                ) or 'STU0001'
        return super().create(vals_list)

    # ── Validation ──────────────────────────────────────────────
    @api.constrains('email', 'guardian_email')
    def _check_email(self):
        for rec in self:
            if rec.email and '@' not in rec.email:
                raise ValidationError('Please provide a valid student email address.')
            if rec.guardian_email and '@' not in rec.guardian_email:
                raise ValidationError('Please provide a valid guardian email address.')

    # ── State Actions ────────────────────────────────────────────
    def action_activate(self):
        self.state = 'active'
        self._send_email('lms_student.lms_email_student_activated')

    def action_graduate(self):
        self.state = 'graduated'
        self._send_email('lms_student.lms_email_student_graduated')

    def action_suspend(self):
        self.state = 'suspended'
        self._send_email('lms_student.lms_email_student_suspended')

    def action_reset_draft(self):
        self.state = 'draft'

    def _send_email(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for rec in self:
                if rec.email:
                    email_values = {}
                    if rec.guardian_email:
                        email_values['email_cc'] = rec.guardian_email
                    template.send_mail(rec.id, force_send=True,
                                       email_values=email_values or None)

    # ── Admin: open editable popup profile from list ─────────────
    def action_edit_profile(self):
        self.ensure_one()
        popup_view = self.env.ref('lms_student.view_lms_student_popup_form')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Edit Student Profile',
            'res_model': 'lms.student',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(popup_view.id, 'form')],
            'target': 'new',
        }

    # ── My Profile (student self-view) ───────────────────────────
    def action_open_my_profile(self):
        """Open the read-only self-profile for the currently logged-in student."""
        student = self.env['lms.student'].search(
            [('user_id', '=', self.env.uid)], limit=1
        )
        if not student:
            raise UserError(_(
                'No student profile is linked to your account. '
                'Please contact an administrator.'
            ))
        selfprofile_view = self.env.ref(
            'lms_student.view_lms_student_selfprofile', raise_if_not_found=False
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'My Profile',
            'res_model': 'lms.student',
            'res_id': student.id,
            'view_mode': 'form',
            'views': [(selfprofile_view.id if selfprofile_view else False, 'form')],
            'target': 'current',
            'context': {'form_view_initial_mode': 'readonly', 'create': False},
        }

    # ── Smart Button ─────────────────────────────────────────────
    def action_view_enrollments(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enrollments',
            'res_model': 'lms.enrollment',
            'view_mode': 'list,form',
            'domain': [('student_id', '=', self.id)],
            'context': {'default_student_id': self.id},
        }
