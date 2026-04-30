{
    'name': 'LMS - Learning Management System',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Manage students, courses, enrollments and academic records',
    'description': """
        LMS Student Module
        ==================
        Features:
        - FR1: Create and manage student profiles
        - FR2: Enroll students into courses (admin)
        - FR3: Structured academic records per student
        - FR4: Edit/update student information
        - FR5: Lecturers must have the ability to record attendance by session.
        - FR6: Attendance records must be maintained historically in an ongoing manner.
        - FR7: Calculating percentage of attendance must occur automatically for each student.
        - FR8: Attendance results must also be shown within a student's profile.
    """,
    'author': 'Custom',
    'website': '',
    'depends': ['base', 'mail', 'im_livechat'],
    'data': [
        'security/lms_security.xml',
        'security/lms_sequence.xml',
        'security/ir.model.access.csv',
        'data/lms_chatbot_data.xml',
        'data/lms_email_templates.xml',
        'data/lms_demo_data.xml',
        'views/lms_dashboard_views.xml',
        'views/lms_student_views.xml',
        'views/lms_course_views.xml',
        'views/lms_enrollment_views.xml',
        'views/lms_academic_record_views.xml',
        'views/lms_academic_record_import_views.xml',
        'views/lms_attendance_views.xml',
        'views/lms_attendance_import_views.xml',
        'views/lms_attendance_wizard_views.xml',
        'views/lms_student_wizard_views.xml',
        'views/lms_assessment_views.xml',
        'views/lms_submission_views.xml',
        'views/lms_notice_views.xml',
        'views/lms_timetable_views.xml',
        'views/lms_fee_payment_views.xml',
        'views/lms_predictive_analytics_views.xml',
        'views/lms_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'lms_student/static/src/xml/lms_dashboard.xml',
            'lms_student/static/src/js/lms_dashboard.js',
            'lms_student/static/src/css/lms_dashboard.css',
            'lms_student/static/src/js/lms_ai_chat.js',
            'lms_student/static/src/css/lms_ai_chat.css',
        ],
    },

    'demo': [
        'demo/lms_demo_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
