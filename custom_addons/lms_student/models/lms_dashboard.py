from odoo import models, api, fields


class LmsDashboard(models.AbstractModel):
    _name = 'lms.dashboard'
    _description = 'LMS Dashboard Data Provider'

    # ── Unified entry point ──────────────────────────────────────

    @api.model
    def get_dashboard_data(self):
        """Resolve the caller's role server-side and return the appropriate data.

        Doing the group check in Python (rather than in JavaScript) avoids
        problems with Odoo 19's privilege_id-based group model where
        implied-group membership may not propagate correctly when queried via
        has_group() from the browser.
        """
        env = self.env
        is_teacher = (
            env.user.has_group('lms_student.group_lms_manager')
            or env.user.has_group('lms_student.group_lms_teacher')
            or env.user.has_group('base.group_system')
        )
        if is_teacher:
            data = self.get_teacher_dashboard_data()
            data['role'] = 'teacher'
            return data

        student = env['lms.student'].search([('user_id', '=', env.uid)], limit=1)
        if not student:
            return {'role': 'no_profile', 'kpis': {}, 'charts': {}, 'at_risk': []}

        data = self.get_student_dashboard_data()
        data['role'] = 'student'
        return data

    # ── Teacher / Manager Dashboard ──────────────────────────────

    @api.model
    def get_teacher_dashboard_data(self):
        """Return KPIs, chart data, and at-risk table for teacher/manager view."""
        env = self.env

        # ── KPIs ────────────────────────────────────────────────
        active_students = env['lms.student'].search_count([('state', '=', 'active')])
        published_courses = env['lms.course'].search_count([('state', '=', 'published')])
        pending_enrollments = env['lms.enrollment'].search_count([('state', '=', 'pending')])

        # Distinct students with at least one flagged assessment grade
        flagged_student_ids = env['lms.assessment.grade'].search(
            [('is_flagged', '=', True)]
        ).mapped('student_id').ids
        flagged_students = len(set(flagged_student_ids))

        confirmed_records = env['lms.academic.record'].search([('state', '=', 'confirmed')])
        avg_gpa = (
            round(sum(r.gpa for r in confirmed_records) / len(confirmed_records), 2)
            if confirmed_records else 0.0
        )

        # ── Chart: Enrollments by course ────────────────────────
        groups = env['lms.enrollment']._read_group(
            [('state', '!=', 'dropped')],
            ['course_id'],
            ['__count'],
        )
        enroll_items = sorted(
            [(course.name, count) for course, count in groups],
            key=lambda x: x[0],
        )
        enroll_labels = [name for name, val in enroll_items]
        enroll_values = [val for name, val in enroll_items]

        # ── Chart: Student status distribution ──────────────────
        STATE_LABELS = {
            'draft': 'Draft',
            'active': 'Active',
            'graduated': 'Graduated',
            'suspended': 'Suspended',
        }
        groups = env['lms.student']._read_group([], ['state'], ['__count'])
        status_labels = [STATE_LABELS.get(state, state) for state, count in groups]
        status_values = [count for state, count in groups]

        # ── Chart: Avg attendance per course ────────────────────
        groups = env['lms.enrollment']._read_group(
            [('state', '=', 'enrolled')],
            ['course_id'],
            ['attendance_percent:avg'],
        )
        attend_items = sorted(
            [(course.name, round(avg or 0.0, 1)) for course, avg in groups],
            key=lambda x: x[0],
        )
        attend_labels = [name for name, val in attend_items]
        attend_values = [val for name, val in attend_items]

        # ── Chart: Grade distribution (bucketed) ─────────────────
        grade_records = env['lms.assessment.grade'].search_read([], ['percentage'])
        buckets = {'0–50': 0, '50–75': 0, '75–90': 0, '90–100': 0}
        for g in grade_records:
            p = g['percentage']
            if p < 50:
                buckets['0–50'] += 1
            elif p < 75:
                buckets['50–75'] += 1
            elif p < 90:
                buckets['75–90'] += 1
            else:
                buckets['90–100'] += 1
        grade_dist_labels = list(buckets.keys())
        grade_dist_values = list(buckets.values())

        # ── Chart: Assessment score trend (avg score, by date) ───
        groups = env['lms.assessment.grade']._read_group(
            [],
            ['assessment_id'],
            ['score:avg'],
        )
        items = sorted(
            [(assessment, round(avg or 0.0, 1)) for assessment, avg in groups],
            key=lambda x: x[0].date or fields.Date.today(),
        )
        trend_labels = [a.name for a, v in items]
        trend_values = [v for a, v in items]

        # ── At-risk table ────────────────────────────────────────
        at_risk_enrollments = env['lms.enrollment'].search([
            '|',
            ('attendance_percent', '<', 75.0),
            ('student_id.assessment_grade_ids.is_flagged', '=', True),
        ], limit=25)

        at_risk_data = []
        seen = set()
        for enr in at_risk_enrollments:
            key = (enr.student_id.id, enr.course_id.id)
            if key in seen:
                continue
            seen.add(key)
            flagged_count = len(
                enr.student_id.assessment_grade_ids.filtered('is_flagged')
            )
            at_risk_data.append({
                'student_id': enr.student_id.id,
                'student_name': enr.student_id.name,
                'course_name': enr.course_id.name,
                'attendance': round(enr.attendance_percent, 1),
                'flagged': flagged_count,
            })

        # ── Risk prediction counts ───────────────────────────────
        predictions = env['lms.predictive.analytics'].search([])
        risk_high    = len(predictions.filtered(lambda p: p.risk_level == 'high'))
        risk_medium  = len(predictions.filtered(lambda p: p.risk_level == 'medium'))
        risk_total   = risk_high + risk_medium

        return {
            'kpis': {
                'active_students': active_students,
                'published_courses': published_courses,
                'flagged_students': flagged_students,
                'avg_gpa': avg_gpa,
                'pending_enrollments': pending_enrollments,
                'risk_high': risk_high,
                'risk_medium': risk_medium,
                'risk_total': risk_total,
            },
            'charts': {
                'enrollments_by_course': {
                    'labels': enroll_labels,
                    'values': enroll_values,
                },
                'student_status': {
                    'labels': status_labels,
                    'values': status_values,
                },
                'attendance_by_course': {
                    'labels': attend_labels,
                    'values': attend_values,
                },
                'grade_distribution': {
                    'labels': grade_dist_labels,
                    'values': grade_dist_values,
                },
                'score_trend': {
                    'labels': trend_labels,
                    'values': trend_values,
                },
            },
            'at_risk': at_risk_data,
        }

    # ── Student Dashboard ────────────────────────────────────────

    @api.model
    def get_student_dashboard_data(self):
        """Return KPIs and chart data scoped to the currently logged-in student."""
        env = self.env
        uid = env.uid

        student = env['lms.student'].search([('user_id', '=', uid)], limit=1)
        if not student:
            return {'no_profile': True, 'kpis': {}, 'charts': {}, 'risk': {}}

        # ── Risk prediction for this student ─────────────────────
        prediction = env['lms.predictive.analytics'].search(
            [('student_id', '=', student.id)], limit=1
        )
        risk = {
            'level':  prediction.risk_level  if prediction else False,
            'score':  prediction.risk_score  if prediction else 0.0,
            'suggestion': prediction.suggestion if prediction else '',
        }

        # ── KPIs ────────────────────────────────────────────────
        active_enrollments = env['lms.enrollment'].search([
            ('student_id', '=', student.id),
            ('state', '=', 'enrolled'),
        ])
        enrolled_count = len(active_enrollments)
        avg_attendance = (
            round(
                sum(e.attendance_percent for e in active_enrollments) / enrolled_count,
                1,
            )
            if enrolled_count else 0.0
        )

        latest_record = env['lms.academic.record'].search([
            ('student_id', '=', student.id),
            ('state', '=', 'confirmed'),
        ], order='academic_year desc, semester desc', limit=1)
        latest_gpa = round(latest_record.gpa, 2) if latest_record else 0.0

        flagged_count = env['lms.assessment.grade'].search_count([
            ('student_id', '=', student.id),
            ('is_flagged', '=', True),
        ])

        # ── Chart: My grades by course (avg %) ──────────────────
        groups = env['lms.assessment.grade']._read_group(
            [('student_id', '=', student.id)],
            ['course_id'],
            ['percentage:avg'],
        )
        grade_items = sorted(
            [(course.name, round(avg or 0.0, 1)) for course, avg in groups],
            key=lambda x: x[0],
        )
        grade_labels = [name for name, val in grade_items]
        grade_values = [val for name, val in grade_items]

        # ── Chart: My attendance by course ───────────────────────
        attend_items = sorted(
            [(e.course_id.name, round(e.attendance_percent, 1)) for e in active_enrollments],
            key=lambda x: x[0],
        )
        attend_labels = [name for name, val in attend_items]
        attend_values = [val for name, val in attend_items]

        # ── Chart: GPA by semester ───────────────────────────────
        records = env['lms.academic.record'].search([
            ('student_id', '=', student.id),
            ('state', '=', 'confirmed'),
        ], order='academic_year asc, semester asc')
        sem_labels = {1: 'Sem 1', 2: 'Sem 2', 3: 'Sem 3'}
        gpa_labels = [
            f"{r.academic_year} {sem_labels.get(int(r.semester), r.semester)}"
            for r in records
        ]
        gpa_values = [round(r.gpa, 2) for r in records]

        return {
            'no_profile': False,
            'student_name': student.name,
            'risk': risk,
            'kpis': {
                'enrolled_courses': enrolled_count,
                'avg_attendance': avg_attendance,
                'latest_gpa': latest_gpa,
                'flagged_assessments': flagged_count,
            },
            'charts': {
                'grades_by_course': {
                    'labels': grade_labels,
                    'values': grade_values,
                },
                'attendance_by_course': {
                    'labels': attend_labels,
                    'values': attend_values,
                },
                'gpa_by_semester': {
                    'labels': gpa_labels,
                    'values': gpa_values,
                },
            },
        }
