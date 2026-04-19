from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class LmsAssessment(models.Model):
    _name = 'lms.assessment'
    _description = 'LMS Course Assessment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string='Assessment Name', required=True, tracking=True)
    course_id = fields.Many2one(
        'lms.course', string='Course', required=True, tracking=True
    )
    type = fields.Selection([
        ('assignment', 'Assignment'),
        ('quiz', 'Quiz'),
        ('mid_exam', 'Mid-term Exam'),
        ('final_exam', 'Final Exam'),
        ('participation', 'Participation'),
        ('other', 'Other'),
    ], string='Assessment Type', default='assignment', required=True, tracking=True)
    
    date = fields.Date(string='Assessment Date', default=fields.Date.today)
    max_score = fields.Float(string='Maximum Score', default=100.0, required=True)
    weight = fields.Float(string='Weight (%)', default=10.0, help="Weightage in final course grade")
    
    grade_ids = fields.One2many(
        'lms.assessment.grade', 'assessment_id', string='Grades'
    )
    
    grade_count = fields.Integer(compute='_compute_grade_count')

    @api.depends('grade_ids')
    def _compute_grade_count(self):
        for rec in self:
            rec.grade_count = len(rec.grade_ids)

    def action_generate_grade_lines(self):
        """Automatically create grade lines for all enrolled students who don't have one yet."""
        self.ensure_one()
        enrolled_students = self.env['lms.enrollment'].search([
            ('course_id', '=', self.course_id.id),
            ('state', '=', 'enrolled')
        ]).mapped('student_id')
        
        existing_students = self.grade_ids.mapped('student_id')
        students_to_add = enrolled_students - existing_students
        
        grade_vals = []
        for student in students_to_add:
            grade_vals.append({
                'assessment_id': self.id,
                'student_id': student.id,
                'course_id': self.course_id.id,
                'max_score': self.max_score,
            })
        
        if grade_vals:
            self.env['lms.assessment.grade'].create(grade_vals)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Grade lines generated for %s students.') % len(students_to_add),
                'sticky': False,
            }
        }

class LmsAssessmentGrade(models.Model):
    _name = 'lms.assessment.grade'
    _description = 'Student Assessment Grade'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'

    assessment_id = fields.Many2one(
        'lms.assessment', string='Assessment', required=True, ondelete='cascade'
    )
    student_id = fields.Many2one(
        'lms.student', string='Student', required=True, ondelete='cascade'
    )
    course_id = fields.Many2one(
        'lms.course', string='Course', related='assessment_id.course_id', store=True
    )
    score = fields.Float(string='Score Obtained', default=0.0, tracking=True)
    max_score = fields.Float(string='Max Score', related='assessment_id.max_score', store=True)
    percentage = fields.Float(string='Percentage', compute='_compute_percentage', store=True)
    remarks = fields.Text(string='Remarks')
    
    display_name = fields.Char(compute='_compute_display_name', store=True)
    is_flagged = fields.Boolean(
        string='Below 75%', compute='_compute_is_flagged', store=True
    )

    @api.depends('percentage')
    def _compute_is_flagged(self):
        for rec in self:
            rec.is_flagged = rec.percentage < 75.0

    @api.depends('student_id', 'assessment_id')
    def _compute_display_name(self):
        for rec in self:
            student = rec.student_id.name or '?'
            assessment = rec.assessment_id.name or '?'
            rec.display_name = f"{student}: {assessment}"

    @api.depends('score', 'max_score')
    def _compute_percentage(self):
        for rec in self:
            if rec.max_score > 0:
                rec.percentage = (rec.score / rec.max_score) * 100
            else:
                rec.percentage = 0.0

    @api.constrains('score', 'max_score')
    def _check_score(self):
        for rec in self:
            if rec.score > rec.max_score:
                raise ValidationError(_("Score cannot be greater than the maximum score (%s)!") % rec.max_score)
            if rec.score < 0:
                raise ValidationError(_("Score cannot be negative!"))

    def write(self, vals):
        result = super().write(vals)
        if 'score' in vals:
            self._send_grade_emails()
        return result

    def _send_grade_emails(self):
        grade_tmpl = self.env.ref(
            'lms_student.lms_email_grade_published', raise_if_not_found=False
        )
        low_tmpl = self.env.ref(
            'lms_student.lms_email_grade_low_score', raise_if_not_found=False
        )
        for rec in self:
            if not rec.student_id.email:
                continue
            if grade_tmpl:
                grade_tmpl.send_mail(rec.id, force_send=True)
            if low_tmpl and rec.is_flagged:
                low_tmpl.send_mail(rec.id, force_send=True)
