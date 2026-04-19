from odoo import models, fields, api


class LmsAcademicRecord(models.Model):
    _name = 'lms.academic.record'
    _description = 'LMS Academic Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'academic_year desc, semester desc'

    student_id = fields.Many2one(
        'lms.student', string='Student', required=True,
        ondelete='cascade', tracking=True
    )
    academic_year = fields.Char(
        string='Academic Year', required=True, tracking=True
    )
    semester = fields.Selection([
        ('1', 'Semester 1'),
        ('2', 'Semester 2'),
        ('3', 'Semester 3 (Summer)'),
    ], string='Semester', required=True, tracking=True)

    # ── Grades Line ─────────────────────────────────────────────
    record_line_ids = fields.One2many(
        'lms.academic.record.line', 'record_id', string='Course Grades'
    )

    # ── Summary Metrics ─────────────────────────────────────────
    gpa = fields.Float(
        string='GPA', compute='_compute_gpa',
        store=True, digits=(4, 2)
    )
    total_credits = fields.Integer(
        string='Total Credits', compute='_compute_gpa', store=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('locked', 'Locked'),
    ], string='Status', default='draft', tracking=True)

    remarks = fields.Text(string='Remarks')
    issued_date = fields.Date(string='Issue Date', default=fields.Date.today)

    @api.depends('record_line_ids.grade_points', 'record_line_ids.credits')
    def _compute_gpa(self):
        for rec in self:
            lines = rec.record_line_ids
            total_points = sum(l.grade_points * l.credits for l in lines)
            total_credits = sum(l.credits for l in lines)
            rec.total_credits = total_credits
            rec.gpa = round(total_points / total_credits, 2) if total_credits else 0.0

    def action_confirm(self):
        self.state = 'confirmed'
        self._send_email('lms_student.lms_email_results_available')

    def action_lock(self):
        self.state = 'locked'
        self._send_email('lms_student.lms_email_transcript_locked')

    def action_reset_draft(self):
        self.state = 'draft'

    def _send_email(self, template_xmlid):
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            for rec in self:
                if rec.student_id.email:
                    template.send_mail(rec.id, force_send=True)

    def action_import_csv(self):
        """Open the bulk CSV import wizard for academic records."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Academic Records (CSV)',
            'res_model': 'lms.academic.record.import.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    _sql_constraints = [
        ('unique_student_year_semester',
         'UNIQUE(student_id, academic_year, semester)',
         'An academic record for this student, year and semester already exists.'),
    ]


class LmsAcademicRecordLine(models.Model):
    _name = 'lms.academic.record.line'
    _description = 'Academic Record Line (Course Grade)'

    record_id = fields.Many2one(
        'lms.academic.record', string='Record',
        required=True, ondelete='cascade'
    )
    course_id = fields.Many2one(
        'lms.course', string='Course', required=True
    )
    credits = fields.Integer(
        string='Credits', related='course_id.credits', store=True
    )
    marks_obtained = fields.Float(string='Marks Obtained', default=0.0)
    total_marks = fields.Float(string='Total Marks', default=100.0)
    percentage = fields.Float(
        string='Percentage (%)', compute='_compute_percentage', store=True
    )
    grade = fields.Char(
        string='Grade', compute='_compute_grade', store=True
    )
    grade_points = fields.Float(
        string='Grade Points', compute='_compute_grade', store=True
    )
    result = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
    ], string='Result', compute='_compute_grade', store=True)
    is_flagged = fields.Boolean(
        string='Below 75%', compute='_compute_is_flagged', store=True
    )

    @api.depends('percentage')
    def _compute_is_flagged(self):
        for line in self:
            line.is_flagged = line.percentage < 75.0

    @api.depends('marks_obtained', 'total_marks')
    def _compute_percentage(self):
        for line in self:
            if line.total_marks:
                line.percentage = (line.marks_obtained / line.total_marks) * 100
            else:
                line.percentage = 0.0

    @api.depends('percentage')
    def _compute_grade(self):
        for line in self:
            p = line.percentage
            if p >= 90:
                line.grade, line.grade_points, line.result = 'A+', 4.0, 'pass'
            elif p >= 80:
                line.grade, line.grade_points, line.result = 'A', 4.0, 'pass'
            elif p >= 75:
                line.grade, line.grade_points, line.result = 'B+', 3.5, 'pass'
            elif p >= 65:
                line.grade, line.grade_points, line.result = 'B', 3.0, 'pass'
            elif p >= 60:
                line.grade, line.grade_points, line.result = 'C+', 2.5, 'pass'
            elif p >= 50:
                line.grade, line.grade_points, line.result = 'C', 2.0, 'pass'
            elif p >= 40:
                line.grade, line.grade_points, line.result = 'D', 1.0, 'pass'
            else:
                line.grade, line.grade_points, line.result = 'F', 0.0, 'fail'
