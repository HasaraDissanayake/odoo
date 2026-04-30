from odoo import models, fields, api


class LmsCourseMaterial(models.Model):
    _name = 'lms.course.material'
    _description = 'Course Material'
    _order = 'week_number, sequence, id'

    course_id = fields.Many2one(
        'lms.course', string='Course', required=True, ondelete='cascade'
    )
    name = fields.Char(string='Title', required=True)
    material_type = fields.Selection([
        ('document',  'Document'),
        ('slide',     'Slide Deck'),
        ('recording', 'Lecture Recording'),
        ('link',      'External Link'),
    ], string='Type', required=True, default='document')
    description = fields.Text(string='Description')
    url = fields.Char(string='URL / Link')
    week_number = fields.Integer(string='Week', default=1)
    sequence = fields.Integer(string='Order', default=10)
    uploaded_by = fields.Many2one(
        'res.users', string='Uploaded By', default=lambda self: self.env.user
    )
    upload_date = fields.Date(string='Date', default=fields.Date.today)
    duration_minutes = fields.Integer(string='Duration (min)')


class LmsAssignmentSubmission(models.Model):
    _name = 'lms.assignment.submission'
    _description = 'Assignment Submission'
    _order = 'submission_date desc'
    _rec_name = 'display_name'

    assessment_id = fields.Many2one(
        'lms.assessment', string='Assessment', required=True, ondelete='cascade'
    )
    student_id = fields.Many2one(
        'lms.student', string='Student', required=True, ondelete='cascade',
        default=lambda self: self.env['lms.student'].search(
            [('user_id', '=', self.env.uid)], limit=1
        ),
    )
    course_id = fields.Many2one(
        'lms.course', related='assessment_id.course_id', store=True, string='Course'
    )
    submission_date = fields.Datetime(
        string='Submitted On', default=fields.Datetime.now
    )
    notes = fields.Text(string='Notes / Comments')
    submission_url = fields.Char(string='Submission Link',
        help='Paste a Google Drive, OneDrive, Dropbox or any public link to your document.')
    state = fields.Selection([
        ('draft',     'Draft'),
        ('submitted', 'Submitted'),
        ('graded',    'Graded'),
    ], string='Status', default='submitted')
    grade_id = fields.Many2one(
        'lms.assessment.grade', string='Grade Record'
    )
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('student_id', 'assessment_id')
    def _compute_display_name(self):
        for rec in self:
            student = rec.student_id.name or '?'
            assessment = rec.assessment_id.name or '?'
            rec.display_name = f"{student} → {assessment}"
