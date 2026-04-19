import base64
import csv
import io

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LmsAcademicRecordImportWizard(models.TransientModel):
    _name = 'lms.academic.record.import.wizard'
    _description = 'Academic Record CSV Import Wizard'

    csv_file = fields.Binary(string='CSV File')
    filename = fields.Char(string='Filename')
    state = fields.Selection([
        ('upload', 'Upload'),
        ('preview', 'Preview'),
        ('done', 'Done'),
    ], default='upload')
    preview_line_ids = fields.One2many(
        'lms.academic.record.import.line', 'wizard_id', string='Preview'
    )
    error_count = fields.Integer(compute='_compute_counts', string='Errors')
    success_count = fields.Integer(compute='_compute_counts', string='Valid Rows')
    import_count = fields.Integer(string='Records Created', default=0)

    @api.depends('preview_line_ids.status')
    def _compute_counts(self):
        for rec in self:
            rec.error_count = len(rec.preview_line_ids.filtered(lambda l: l.status == 'error'))
            rec.success_count = len(rec.preview_line_ids.filtered(lambda l: l.status == 'valid'))

    # ── Step 1: Parse ────────────────────────────────────────────────────────

    def action_parse_csv(self):
        self.ensure_one()
        if not self.csv_file:
            raise UserError(_('Please upload a CSV file before continuing.'))

        # Decode file
        try:
            raw = base64.b64decode(self.csv_file).decode('utf-8-sig')
        except Exception as e:
            raise UserError(_('Could not read file: %s') % str(e))

        reader = csv.DictReader(io.StringIO(raw))

        if not reader.fieldnames:
            raise UserError(_('The CSV file appears to be empty.'))

        # Normalise header names (strip whitespace)
        fieldnames = [f.strip() for f in reader.fieldnames]
        required_cols = {'student_id', 'academic_year', 'semester', 'course_code', 'marks_obtained'}
        missing = required_cols - set(fieldnames)
        if missing:
            raise UserError(_('Missing required columns: %s') % ', '.join(sorted(missing)))

        # Clear any previous preview lines
        self.preview_line_ids.unlink()

        lines_to_create = []
        seen = {}  # (student_id_raw, academic_year, semester, course_code) → row_num

        for row_num, row in enumerate(reader, start=2):
            row = {k.strip(): (v.strip() if v else '') for k, v in row.items() if k}

            student_id_raw = row.get('student_id', '')
            academic_year  = row.get('academic_year', '')
            semester       = row.get('semester', '')
            course_code    = row.get('course_code', '')
            marks_raw      = row.get('marks_obtained', '')
            total_raw      = row.get('total_marks', '') or '100'

            errors = []
            student_rec = None
            course_rec  = None
            marks_obtained = 0.0
            total_marks    = 100.0

            # ── Validate student ───────────────────────────────────────────
            if not student_id_raw:
                errors.append(_('student_id is empty'))
            else:
                student_rec = self.env['lms.student'].search(
                    [('student_id', '=', student_id_raw)], limit=1
                )
                if not student_rec:
                    errors.append(_("Student '%s' not found") % student_id_raw)

            # ── Validate course ────────────────────────────────────────────
            if not course_code:
                errors.append(_('course_code is empty'))
            else:
                course_rec = self.env['lms.course'].search(
                    [('code', '=', course_code)], limit=1
                )
                if not course_rec:
                    errors.append(_("Course '%s' not found") % course_code)

            # ── Validate semester ──────────────────────────────────────────
            if semester not in ('1', '2', '3'):
                errors.append(_("Semester must be 1, 2, or 3 (got '%s')") % semester)

            # ── Validate marks ─────────────────────────────────────────────
            try:
                marks_obtained = float(marks_raw)
            except ValueError:
                errors.append(_("Invalid marks_obtained value: '%s'") % marks_raw)

            try:
                total_marks = float(total_raw)
            except ValueError:
                errors.append(_("Invalid total_marks value: '%s'") % total_raw)
                total_marks = 100.0

            if not errors and marks_obtained > total_marks:
                errors.append(
                    _('marks_obtained (%.1f) cannot exceed total_marks (%.1f)')
                    % (marks_obtained, total_marks)
                )

            # ── Duplicate within file ──────────────────────────────────────
            dup_key = (student_id_raw, academic_year, semester, course_code)
            if dup_key in seen:
                errors.append(_('Duplicate of row %d in this file') % seen[dup_key])
            else:
                seen[dup_key] = row_num

            # ── Locked record check ────────────────────────────────────────
            if not errors and student_rec and semester in ('1', '2', '3'):
                existing = self.env['lms.academic.record'].search([
                    ('student_id', '=', student_rec.id),
                    ('academic_year', '=', academic_year),
                    ('semester', '=', semester),
                ], limit=1)
                if existing and existing.state == 'locked':
                    errors.append(
                        _('Academic record for this student/year/semester is locked')
                    )

            lines_to_create.append({
                'wizard_id':       self.id,
                'row_number':      row_num,
                'student_id_raw':  student_id_raw,
                'academic_year':   academic_year,
                'semester':        semester,
                'course_code':     course_code,
                'marks_obtained':  marks_obtained,
                'total_marks':     total_marks,
                'student_id':      student_rec.id if student_rec else False,
                'course_id':       course_rec.id if course_rec else False,
                'status':          'error' if errors else 'valid',
                'error_message':   '; '.join(errors) if errors else '',
            })

        if not lines_to_create:
            raise UserError(_('The CSV file contains no data rows.'))

        self.env['lms.academic.record.import.line'].create(lines_to_create)
        self.state = 'preview'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Step 2: Import ───────────────────────────────────────────────────────

    def action_import(self):
        self.ensure_one()
        valid_lines = self.preview_line_ids.filtered(lambda l: l.status == 'valid')

        if not valid_lines:
            raise UserError(_('No valid rows to import.'))

        # Group rows by (student, academic_year, semester) to create/find parent records
        groups = {}
        for line in valid_lines:
            key = (line.student_id.id, line.academic_year, line.semester)
            groups.setdefault(key, []).append(line)

        created_records = 0
        updated_records = 0

        for (student_id, academic_year, semester), lines in groups.items():
            record = self.env['lms.academic.record'].search([
                ('student_id', '=', student_id),
                ('academic_year', '=', academic_year),
                ('semester', '=', semester),
            ], limit=1)

            if not record:
                record = self.env['lms.academic.record'].create({
                    'student_id':    student_id,
                    'academic_year': academic_year,
                    'semester':      semester,
                })
                created_records += 1
            else:
                updated_records += 1

            for line in lines:
                self.env['lms.academic.record.line'].create({
                    'record_id':      record.id,
                    'course_id':      line.course_id.id,
                    'marks_obtained': line.marks_obtained,
                    'total_marks':    line.total_marks,
                })

        self.import_count = created_records + updated_records
        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Navigation helpers ───────────────────────────────────────────────────

    def action_back_to_upload(self):
        self.preview_line_ids.unlink()
        self.state = 'upload'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset(self):
        self.preview_line_ids.unlink()
        self.write({'csv_file': False, 'filename': False, 'state': 'upload', 'import_count': 0})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_view_records(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Academic Records'),
            'res_model': 'lms.academic.record',
            'view_mode': 'list,form',
            'target': 'current',
        }

    # ── Template download ────────────────────────────────────────────────────

    def action_download_template(self):
        template = (
            'student_id,academic_year,semester,course_code,marks_obtained,total_marks\n'
            'STU0001,2024-2025,1,CS101,85,100\n'
            'STU0001,2024-2025,1,MATH201,72,100\n'
            'STU0002,2024-2025,2,ENG301,90,100\n'
        )
        attachment = self.env['ir.attachment'].create({
            'name': 'academic_records_template.csv',
            'datas': base64.b64encode(template.encode('utf-8')).decode('utf-8'),
            'mimetype': 'text/csv',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'new',
        }


class LmsAcademicRecordImportLine(models.TransientModel):
    _name = 'lms.academic.record.import.line'
    _description = 'Academic Record Import Preview Line'

    wizard_id = fields.Many2one(
        'lms.academic.record.import.wizard', required=True, ondelete='cascade'
    )
    row_number     = fields.Integer(string='Row #')
    student_id_raw = fields.Char(string='Student ID')
    academic_year  = fields.Char(string='Academic Year')
    semester       = fields.Char(string='Semester')
    course_code    = fields.Char(string='Course Code')
    marks_obtained = fields.Float(string='Marks')
    total_marks    = fields.Float(string='Total Marks')
    student_id     = fields.Many2one('lms.student', string='Resolved Student')
    course_id      = fields.Many2one('lms.course', string='Resolved Course')
    status         = fields.Selection([
        ('valid', 'Valid'),
        ('error', 'Error'),
    ], string='Status')
    error_message  = fields.Char(string='Error Details')
