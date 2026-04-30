import base64
import csv
import io
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LmsAttendanceImport(models.TransientModel):
    _name = 'lms.attendance.import'
    _description = 'Import Attendance from File'

    session_id = fields.Many2one(
        'lms.attendance.session', string='Session', required=True, readonly=True
    )
    file_data = fields.Binary(string='Upload File', required=True)
    file_name = fields.Char(string='File Name')
    result_message = fields.Html(string='Result', readonly=True)

    # ── Actions ────────────────────────────────────────────────────────

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("Please upload a file before importing."))

        name = (self.file_name or '').lower()
        if name.endswith('.csv'):
            rows = self._parse_csv()
        elif name.endswith(('.xlsx', '.xls')):
            rows = self._parse_excel()
        else:
            raise UserError(_(
                "Unsupported file format. Please upload a .csv or .xlsx file."
            ))

        updated, skipped, errors = self._apply_rows(rows)

        msg_parts = [
            '<p><b>Import complete:</b></p><ul>',
            '<li><span style="color:green;">%d student(s) updated</span></li>' % updated,
        ]
        if skipped:
            msg_parts.append('<li>%d row(s) skipped (already set)</li>' % skipped)
        if errors:
            msg_parts.append(
                '<li><span style="color:red;">%d row(s) not matched:</span> %s</li>'
                % (len(errors), ', '.join(errors[:10]))
            )
        msg_parts.append('</ul>')
        self.result_message = ''.join(msg_parts)

        # Stay open to show the result
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download_template(self):
        """Return a CSV template the teacher can fill in."""
        self.ensure_one()
        session = self.session_id
        lines = ['Student ID,Student Name,Status']
        enrollments = self.env['lms.enrollment'].search([
            ('course_id', '=', session.course_id.id),
            ('state', '=', 'enrolled'),
        ])
        for enr in enrollments:
            lines.append('%s,%s,Present' % (
                enr.student_id.student_id or '',
                enr.student_id.name or '',
            ))
        csv_content = '\n'.join(lines)
        csv_bytes = base64.b64encode(csv_content.encode('utf-8'))
        attachment = self.env['ir.attachment'].sudo().create({
            'name': 'attendance_template_%s.csv' % (session.course_id.code or 'course'),
            'datas': csv_bytes,
            'mimetype': 'text/csv',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }

    # ── Parsers ────────────────────────────────────────────────────────

    def _parse_csv(self):
        raw = base64.b64decode(self.file_data)
        try:
            text = raw.decode('utf-8-sig')   # handles BOM
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        reader = csv.DictReader(io.StringIO(text))
        return self._normalise_rows(reader)

    def _parse_excel(self):
        try:
            import openpyxl
        except ImportError:
            raise UserError(_("openpyxl is required for Excel import."))
        raw = base64.b64decode(self.file_data)
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h).strip().lower() if h else '' for h in next(rows_iter, [])]
        result = []
        for row in rows_iter:
            if not any(row):
                continue
            result.append({headers[i]: (str(v).strip() if v is not None else '')
                            for i, v in enumerate(row) if i < len(headers)})
        return self._normalise_rows(result)

    def _normalise_rows(self, rows):
        """Return list of dicts with keys: student_id_str, name_str, status_str."""
        result = []
        for row in rows:
            # Normalise header names — accept slight variations
            row_lower = {k.strip().lower().replace(' ', '_'): v
                         for k, v in row.items() if k}
            result.append({
                'student_id_str': row_lower.get('student_id', row_lower.get('id', '')).strip(),
                'name_str':       row_lower.get('student_name', row_lower.get('name', '')).strip(),
                'status_str':     row_lower.get('status', row_lower.get('attendance', 'present')).strip().lower(),
            })
        return result

    # ── Apply ──────────────────────────────────────────────────────────

    def _apply_rows(self, rows):
        session = self.session_id
        updated = skipped = 0
        errors = []

        # Build lookup: student_id code → lms.student record
        all_students = self.env['lms.student'].search([])
        by_sid = {s.student_id.upper(): s for s in all_students if s.student_id}
        by_name = {s.name.upper(): s for s in all_students if s.name}

        # Build lookup of existing lines on this session
        line_map = {line.student_id.id: line for line in session.attendance_line_ids}

        for row in rows:
            sid = row['student_id_str'].upper()
            name = row['name_str'].upper()
            raw_status = row['status_str']

            # Resolve status
            if raw_status in ('present', 'p', '1', 'yes', 'true'):
                status = 'present'
            elif raw_status in ('absent', 'a', '0', 'no', 'false'):
                status = 'absent'
            else:
                status = 'present'  # default

            # Find student
            student = by_sid.get(sid) or by_name.get(name)
            if not student:
                errors.append(sid or name or '(empty)')
                continue

            existing = line_map.get(student.id)
            if existing:
                if existing.status != status:
                    existing.status = status
                    updated += 1
                else:
                    skipped += 1
            else:
                self.env['lms.attendance.line'].create({
                    'session_id': session.id,
                    'student_id': student.id,
                    'status': status,
                })
                updated += 1

        return updated, skipped, errors
