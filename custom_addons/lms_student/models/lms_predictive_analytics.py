from odoo import models, fields, api, _


class LmsPredictiveAnalytics(models.Model):
    _name = 'lms.predictive.analytics'
    _description = 'Student Risk Prediction'
    _rec_name = 'student_id'
    _order = 'risk_score desc, student_id asc'

    student_id = fields.Many2one(
        'lms.student', string='Student', required=True,
        ondelete='cascade', index=True,
    )

    # ── Overall input metrics ─────────────────────────────────────
    enrollment_count = fields.Integer(string='Enrolled Courses', default=0)
    attendance_pct   = fields.Float(string='Attendance %',   digits=(5, 1), default=0.0)
    avg_grade_pct    = fields.Float(string='Avg Grade %',    digits=(5, 1), default=0.0)
    low_score_count  = fields.Integer(string='Low Score Flags', default=0)
    absence_count    = fields.Integer(string='Absence Count',   default=0)

    # ── Overall risk output ───────────────────────────────────────
    risk_score = fields.Float(string='Risk Score', digits=(5, 1), default=0.0)
    risk_level = fields.Selection([
        ('low',    'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high',   'High Risk'),
    ], string='Risk Level', default='low')
    suggestion    = fields.Text(string='Suggestion')
    last_computed = fields.Datetime(string='Last Computed', readonly=True)

    # ── Course link (for search / record-rule filtering) ──────────
    course_ids = fields.Many2many(
        'lms.course',
        'lms_prediction_course_rel',
        'prediction_id', 'course_id',
        string='Enrolled Courses',
    )

    # ── Per-course breakdown ──────────────────────────────────────
    course_detail_ids = fields.One2many(
        'lms.predictive.analytics.line', 'prediction_id',
        string='Course Breakdown',
    )

    _sql_constraints = [
        ('student_uniq', 'unique(student_id)',
         'A prediction record already exists for this student.'),
    ]

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _risk_level_from_score(score):
        if score < 30:
            return 'low'
        elif score < 60:
            return 'medium'
        return 'high'

    def _compute_course_line(self, student, enrollment):
        """Return a vals dict for one course-level risk line."""
        env      = self.env
        course   = enrollment.course_id

        # Attendance for this course
        att_pct = enrollment.attendance_percent or 0.0

        # Absences in this course
        absence_count = env['lms.attendance.line'].search_count([
            ('student_id', '=', student.id),
            ('course_id',  '=', course.id),
            ('status',     '=', 'absent'),
        ])

        # Grades for this course
        grades = env['lms.assessment.grade'].search([
            ('student_id', '=', student.id),
            ('course_id',  '=', course.id),
        ])
        if grades:
            avg_grade_pct   = sum(g.percentage for g in grades) / len(grades)
            low_score_count = len(grades.filtered('is_flagged'))
        else:
            avg_grade_pct   = 100.0
            low_score_count = 0

        score = max(0.0, round(
            (100.0 - att_pct)       * 0.5
            + (100.0 - avg_grade_pct) * 0.4
            + low_score_count         * 5,
            1,
        ))

        return {
            'course_id':        course.id,
            'attendance_pct':   round(att_pct, 1),
            'avg_grade_pct':    round(avg_grade_pct, 1),
            'low_score_count':  low_score_count,
            'absence_count':    absence_count,
            'course_risk_score': score,
            'course_risk_level': self._risk_level_from_score(score),
        }

    # ── Core computation ──────────────────────────────────────────

    def _gather_metrics(self, student):
        """Collect data and compute overall + per-course risk for one student."""
        env = self.env

        # Overall attendance (avg across enrollments)
        attendance_pct = student.overall_attendance_percent or 0.0

        # Total absences
        absence_count = env['lms.attendance.line'].search_count([
            ('student_id', '=', student.id),
            ('status',     '=', 'absent'),
        ])

        # Overall grades
        grades = env['lms.assessment.grade'].search([('student_id', '=', student.id)])
        if grades:
            avg_grade_pct   = sum(g.percentage for g in grades) / len(grades)
            low_score_count = len(grades.filtered('is_flagged'))
        else:
            avg_grade_pct   = 100.0
            low_score_count = 0

        # Active enrollments
        enrollments = env['lms.enrollment'].search([
            ('student_id', '=', student.id),
            ('state', 'not in', ['dropped']),
        ])
        enrollment_count = len(enrollments)
        course_ids       = enrollments.mapped('course_id').ids

        # ── Overall risk score ───────────────────────────────────
        risk_score = max(0.0, round(
            (100.0 - attendance_pct) * 0.5
            + (100.0 - avg_grade_pct) * 0.4
            + low_score_count * 5,
            1,
        ))
        risk_level = self._risk_level_from_score(risk_score)

        suggestions = {
            'low':    'Continue monitoring. Student is performing well across all areas.',
            'medium': ('Recommend lecturer follow-up. '
                       'Student may benefit from additional academic support or counselling.'),
            'high':   ('Immediate academic intervention required. '
                       'Please contact the student and their guardian as soon as possible.'),
        }

        # ── Per-course breakdown lines ───────────────────────────
        course_lines = [(5, 0, 0)]   # delete existing lines first
        for enr in enrollments:
            course_lines.append((0, 0, self._compute_course_line(student, enr)))

        return {
            'student_id':       student.id,
            'attendance_pct':   round(attendance_pct, 1),
            'absence_count':    absence_count,
            'avg_grade_pct':    round(avg_grade_pct, 1),
            'low_score_count':  low_score_count,
            'enrollment_count': enrollment_count,
            'risk_score':       risk_score,
            'risk_level':       risk_level,
            'suggestion':       suggestions[risk_level],
            'last_computed':    fields.Datetime.now(),
            'course_ids':       [(6, 0, course_ids)],
            'course_detail_ids': course_lines,
        }

    # ── Button: single record ─────────────────────────────────────

    def action_generate_prediction(self):
        self.ensure_one()
        vals = self._gather_metrics(self.student_id)
        self.write(vals)
        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Prediction Updated'),
                'message': _('Risk prediction recalculated for %s.') % self.student_id.name,
                'sticky':  False,
            },
        }

    # ── Button: recalculate all ───────────────────────────────────

    @api.model
    def action_recalculate_all(self):
        """Recalculate predictions for all active students; creates missing records."""
        students = self.env['lms.student'].search([('state', '=', 'active')])
        existing = {r.student_id.id: r for r in self.search([])}

        to_create = []
        for student in students:
            vals = self._gather_metrics(student)
            if student.id in existing:
                existing[student.id].write(vals)
            else:
                to_create.append(vals)

        if to_create:
            self.create(to_create)

        return {
            'type': 'ir.actions.client',
            'tag':  'display_notification',
            'params': {
                'title':   _('Recalculation Complete'),
                'message': _('Risk predictions updated for %d student(s).') % len(students),
                'sticky':  False,
            },
        }


class LmsPredictiveAnalyticsLine(models.Model):
    _name = 'lms.predictive.analytics.line'
    _description = 'Per-Course Risk Detail'
    _order = 'course_risk_score desc'

    prediction_id = fields.Many2one(
        'lms.predictive.analytics', required=True, ondelete='cascade', index=True,
    )
    course_id = fields.Many2one('lms.course', string='Course', readonly=True)

    # ── Per-course metrics ────────────────────────────────────────
    attendance_pct    = fields.Float(string='Attendance %', digits=(5, 1), readonly=True)
    avg_grade_pct     = fields.Float(string='Avg Grade %',  digits=(5, 1), readonly=True)
    low_score_count   = fields.Integer(string='Low Scores', readonly=True)
    absence_count     = fields.Integer(string='Absences',   readonly=True)

    # ── Per-course risk output ────────────────────────────────────
    course_risk_score = fields.Float(string='Risk Score', digits=(5, 1), readonly=True)
    course_risk_level = fields.Selection([
        ('low',    'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high',   'High Risk'),
    ], string='Risk Level', readonly=True)
