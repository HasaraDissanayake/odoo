import json
import urllib.request
import urllib.error
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

GEMINI_API_KEY = 'AIzaSyB8BCLsEFTd73WHoxJA03mqWVx5zrTgP0A'
GEMINI_MODEL = 'gemini-2.5-flash'
GEMINI_URL = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    + GEMINI_MODEL + ':generateContent?key=' + GEMINI_API_KEY
)


class LmsAiChat(http.Controller):

    @http.route('/lms/ai/chat', type='json', auth='user', methods=['POST'])
    def chat(self, message='', history=None):
        if not message or not message.strip():
            return {'response': 'Please type a message.', 'error': False}

        history = history or []
        env = request.env
        user = env.user

        context_text = self._build_context(env, user)
        role_name = self._get_role(user)

        system_prompt = (
            "You are an intelligent AI assistant embedded in a university "
            "Learning Management System (LMS). You help students, teachers, "
            "and managers with academic information.\n\n"
            f"Current user: {user.name}\n"
            f"Role: {role_name}\n\n"
            f"{context_text}\n\n"
            "Guidelines:\n"
            "- Be helpful, concise, and friendly.\n"
            "- Base your answers strictly on the data provided above.\n"
            "- If asked about data not available, say you don't have access to it.\n"
            "- For students, be encouraging and supportive.\n"
            "- Keep responses brief (2-4 sentences) unless detail is requested.\n"
            "- Never invent or guess data — only use facts from the context above.\n"
        )

        contents = []
        for h in (history or [])[-8:]:
            contents.append({
                'role': h.get('role', 'user'),
                'parts': [{'text': h.get('text', '')}]
            })
        contents.append({'role': 'user', 'parts': [{'text': message.strip()}]})

        payload = json.dumps({
            'system_instruction': {'parts': [{'text': system_prompt}]},
            'contents': contents,
            'generationConfig': {
                'temperature': 0.7,
                'maxOutputTokens': 512,
            }
        }).encode('utf-8')

        try:
            req = urllib.request.Request(
                GEMINI_URL,
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                text = data['candidates'][0]['content']['parts'][0]['text']
                return {'response': text.strip(), 'error': False}

        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='ignore')
            _logger.error('Gemini HTTP %s error: %s', e.code, body)
            # Surface the real API error so it can be diagnosed
            try:
                err_data = json.loads(body)
                err_msg = err_data.get('error', {}).get('message', body[:200])
            except Exception:
                err_msg = body[:200]
            return {
                'response': f'AI service error ({e.code}): {err_msg}',
                'error': True
            }
        except urllib.error.URLError as e:
            _logger.error('Gemini URL error: %s', e.reason)
            return {
                'response': 'Cannot reach the AI service. Please check your internet connection.',
                'error': True
            }
        except Exception as e:
            _logger.error('Gemini unexpected error: %s', str(e))
            return {
                'response': 'Something went wrong. Please try again in a moment.',
                'error': True
            }

    # ─────────────────────────────────────────────────────────────────
    def _get_role(self, user):
        if user.has_group('lms_student.group_lms_manager'):
            return 'Manager / Administrator'
        if user.has_group('lms_student.group_lms_teacher'):
            return 'Teacher / Lecturer'
        return 'Student'

    def _build_context(self, env, user):
        lines = []
        try:
            if user.has_group('lms_student.group_lms_manager'):
                total = env['lms.student'].search_count([('state', '=', 'active')])
                at_risk = env['lms.student'].search_count([
                    ('low_attendance', '=', True), ('state', '=', 'active')
                ])
                courses = env['lms.course'].search_count([('state', '=', 'published')])
                enr_count = env['lms.enrollment'].search_count([('state', '=', 'enrolled')])
                lines += [
                    "=== LMS SYSTEM OVERVIEW ===",
                    f"Active students: {total}",
                    f"At-risk students (attendance <75%): {at_risk}",
                    f"Published courses: {courses}",
                    f"Active enrollments: {enr_count}",
                ]
                at_risk_list = env['lms.student'].search([
                    ('low_attendance', '=', True), ('state', '=', 'active')
                ], limit=10)
                if at_risk_list:
                    lines.append("At-risk student details:")
                    for s in at_risk_list:
                        lines.append(
                            f"  - {s.name} (ID: {s.student_id})"
                            f" — {s.overall_attendance_percent:.1f}%"
                        )

            elif user.has_group('lms_student.group_lms_teacher'):
                teacher_courses = env['lms.course'].search(
                    [('instructor_id', '=', user.id)]
                )
                lines.append("=== YOUR COURSES ===")
                for course in teacher_courses:
                    enrollments = env['lms.enrollment'].search([
                        ('course_id', '=', course.id), ('state', '=', 'enrolled')
                    ])
                    at_risk = [e for e in enrollments if e.attendance_percent < 75]
                    avg = (
                        sum(e.attendance_percent for e in enrollments) / len(enrollments)
                        if enrollments else 0.0
                    )
                    lines.append(
                        f"Course: {course.name} ({course.code}) | "
                        f"Enrolled: {len(enrollments)} | "
                        f"At-risk: {len(at_risk)} | Avg attendance: {avg:.1f}%"
                    )
                    for e in at_risk[:5]:
                        lines.append(
                            f"  At-risk: {e.student_id.name}"
                            f" — {e.attendance_percent:.1f}%"
                        )

            else:
                student = env['lms.student'].search(
                    [('user_id', '=', user.id)], limit=1
                )
                if student:
                    lines += [
                        "=== YOUR ACADEMIC PROFILE ===",
                        f"Name: {student.name}",
                        f"Student ID: {student.student_id}",
                        f"Status: {student.state}",
                        f"Overall Attendance: {student.overall_attendance_percent:.1f}%",
                        f"At-Risk: {'Yes — attendance below 75%' if student.low_attendance else 'No'}",
                        "Enrolled Courses:",
                    ]
                    for enr in student.enrollment_ids:
                        if enr.state == 'enrolled':
                            lines.append(
                                f"  - {enr.course_id.name}: "
                                f"Attendance {enr.attendance_percent:.1f}%, "
                                f"Grade: {enr.grade or 'Pending'}"
                            )
                    grades = env['lms.assessment.grade'].search(
                        [('student_id', '=', student.id)],
                        order='id desc', limit=5
                    )
                    if grades:
                        lines.append("Recent Assessment Grades:")
                        for g in grades:
                            flag = " [Below 75%]" if g.is_flagged else ""
                            lines.append(
                                f"  - {g.assessment_id.name}"
                                f" ({g.course_id.name}): "
                                f"{g.score}/{g.max_score}"
                                f" = {g.percentage:.1f}%{flag}"
                            )
                    records = env['lms.academic.record'].search(
                        [('student_id', '=', student.id)],
                        order='id desc', limit=1
                    )
                    if records:
                        r = records[0]
                        lines.append(
                            f"Latest Academic Record: {r.academic_year} "
                            f"Sem {r.semester}, GPA: {r.gpa:.2f}, "
                            f"Credits: {r.total_credits}"
                        )
                else:
                    lines.append("No student profile is linked to your account.")

        except Exception as e:
            _logger.error('AI context build error: %s', str(e))
            lines.append("(Academic data temporarily unavailable)")

        return '\n'.join(lines)
