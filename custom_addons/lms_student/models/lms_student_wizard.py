from odoo import models, fields, api
from odoo.exceptions import ValidationError


class LmsStudentWizard(models.TransientModel):
    _name = 'lms.student.wizard'
    _description = 'New Student Wizard'

    # ── Identity ──────────────────────────────────────────────
    name  = fields.Char(string='Full Name', required=True)
    image = fields.Image(string='Profile Photo', max_width=256, max_height=256)

    # ── Personal ──────────────────────────────────────────────
    date_of_birth = fields.Date(string='Date of Birth')
    gender = fields.Selection([
        ('male',   'Male'),
        ('female', 'Female'),
        ('other',  'Other'),
    ], string='Gender')
    nationality = fields.Many2one('res.country', string='Nationality')

    # ── Contact ───────────────────────────────────────────────
    email   = fields.Char(string='Email', required=True)
    phone   = fields.Char(string='Phone')
    mobile  = fields.Char(string='Mobile')
    address = fields.Text(string='Address')

    # ── Academic ──────────────────────────────────────────────
    enrollment_date = fields.Date(
        string='Enrollment Date', default=fields.Date.today
    )
    user_id = fields.Many2one(
        'res.users', string='Portal / Internal User',
        help='Link to an Odoo user account for student portal access.',
    )

    # ── Guardian ──────────────────────────────────────────────
    guardian_name  = fields.Char(string='Guardian Name')
    guardian_phone = fields.Char(string='Guardian Phone')
    guardian_email = fields.Char(string='Guardian Email')

    # ── Validation ────────────────────────────────────────────
    @api.constrains('email', 'guardian_email')
    def _check_emails(self):
        for rec in self:
            if rec.email and '@' not in rec.email:
                raise ValidationError('Please enter a valid student email address.')
            if rec.guardian_email and '@' not in rec.guardian_email:
                raise ValidationError('Please enter a valid guardian email address.')

    # ── Action ────────────────────────────────────────────────
    def action_create_student(self):
        self.ensure_one()
        student = self.env['lms.student'].create({
            'name':            self.name,
            'image':           self.image,
            'date_of_birth':   self.date_of_birth,
            'gender':          self.gender,
            'nationality':     self.nationality.id if self.nationality else False,
            'email':           self.email,
            'phone':           self.phone,
            'mobile':          self.mobile,
            'address':         self.address,
            'enrollment_date': self.enrollment_date,
            'user_id':         self.user_id.id if self.user_id else False,
            'guardian_name':   self.guardian_name,
            'guardian_phone':  self.guardian_phone,
            'guardian_email':  self.guardian_email,
        })
        # Open the created student record
        return {
            'type':      'ir.actions.act_window',
            'name':      'Student',
            'res_model': 'lms.student',
            'res_id':    student.id,
            'view_mode': 'form',
            'target':    'current',
        }
