import odoo
from odoo import api, SUPERUSER_ID

def check_lms_models(db):
    registry = odoo.modules.registry.Registry(db)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        models = env['ir.model'].search([('model', 'like', 'lms.attendance')])
        print(f"Found {len(models)} attendance models:")
        for m in models:
            print(f" - {m.model}: {m.name}")
            
        access = env['ir.model.access'].search([('model_id.model', 'like', 'lms.attendance')])
        print(f"Found {len(access)} attendance access rules:")
        for a in access:
            print(f" - {a.name} ({a.group_id.name})")

if __name__ == "__main__":
    db_name = "odoo_test" # From the user's objective in conversation summary
    try:
        check_lms_models(db_name)
    except Exception as e:
        print(f"Error: {e}")
