-- =============================================================================
-- Mehreagan ERP — reset users + insert template (PostgreSQL)
--
-- 1) Generate password hash (inside backend container):
--      docker compose exec backend python scripts/hash_password.py "MyStrongPass"
--
-- 2) Replace :HASH below with the printed bcrypt string.
--
-- 3) Run inside postgres container, e.g.:
--      docker compose exec -T postgres psql -U erp_user -d task_management -f - < scripts/sql/users_reset_and_insert.sql
--    or copy/paste into any SQL client connected to task_management.
--
-- Role names (from reset_rbac): super-admin, admin, system_admin, ceo,
--   managing_director, finance_manager, accountant, warehouse_manager,
--   procurement_officer, requester, ...
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- A) Optional: wipe role links + soft-clear nullable FKs (staging / empty ERP)
--    Skip this block if you only want INSERT without deleting anyone.
-- -----------------------------------------------------------------------------

DELETE FROM user_roles;

UPDATE users SET manager_id = NULL;

-- Uncomment if these tables exist and you accept clearing soft refs:
-- UPDATE departments SET head_user_id = NULL WHERE head_user_id IS NOT NULL;
-- UPDATE organizations SET manager_id = NULL WHERE manager_id IS NOT NULL;
-- UPDATE inbox SET user_id = NULL WHERE user_id IS NOT NULL;
-- UPDATE workflow_steps SET assigned_user_id = NULL WHERE assigned_user_id IS NOT NULL;
-- DELETE FROM notifications;
-- DELETE FROM inbox;
-- DELETE FROM audit_logs;

-- Hard delete users (fails if business rows still reference users.id)
DELETE FROM users;

-- Reset id sequence
SELECT setval(pg_get_serial_sequence('users', 'id'), 1, false);

-- -----------------------------------------------------------------------------
-- B) Insert users
--    Columns match app.models.user.User
--    hashed_password MUST be bcrypt from hash_password.py (not plain text)
-- -----------------------------------------------------------------------------

-- One shared password hash for all sample users (change in production!)
-- Example hash for password "123456" — REGENERATE with hash_password.py:
-- \set HASH '''$2b$12$..............................................'''

INSERT INTO users (
    username,
    email,
    mobile,
    first_name,
    last_name,
    hashed_password,
    is_active,
    created_at
) VALUES
    ('ceo1',        'ceo@example.com',        '09120000001', 'نام', 'مدیرعامل',   '<PASTE_BCRYPT_HASH>', true, NOW()),
    ('finance1',    'finance@example.com',    '09120000002', 'نام', 'مالی',       '<PASTE_BCRYPT_HASH>', true, NOW()),
    ('warehouse1',  'warehouse@example.com',  '09120000003', 'نام', 'انبار',      '<PASTE_BCRYPT_HASH>', true, NOW()),
    ('procure1',    'procure@example.com',    '09120000004', 'نام', 'تدارکات',    '<PASTE_BCRYPT_HASH>', true, NOW()),
    ('requester1',  'requester@example.com',  '09120000005', 'نام', 'درخواست‌کننده', '<PASTE_BCRYPT_HASH>', true, NOW()),
    ('admin1',      'admin@example.com',      '09120000006', 'نام', 'ادمین',      '<PASTE_BCRYPT_HASH>', true, NOW())
ON CONFLICT (username) DO UPDATE SET
    email = EXCLUDED.email,
    mobile = EXCLUDED.mobile,
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    hashed_password = EXCLUDED.hashed_password,
    is_active = true;

-- -----------------------------------------------------------------------------
-- C) Assign roles (by username → role.name)
-- -----------------------------------------------------------------------------

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true
FROM users u
JOIN roles r ON r.name = 'ceo'
WHERE u.username = 'ceo1'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true
FROM users u
JOIN roles r ON r.name = 'finance_manager'
WHERE u.username = 'finance1'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true
FROM users u
JOIN roles r ON r.name = 'warehouse_manager'
WHERE u.username = 'warehouse1'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true
FROM users u
JOIN roles r ON r.name = 'procurement_officer'
WHERE u.username = 'procure1'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true
FROM users u
JOIN roles r ON r.name = 'requester'
WHERE u.username = 'requester1'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true
FROM users u
JOIN roles r ON r.name = 'admin'
WHERE u.username = 'admin1'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

-- Optional: grant super-admin to admin1 as well
-- INSERT INTO user_roles (user_id, role_id, is_active)
-- SELECT u.id, r.id, true
-- FROM users u
-- JOIN roles r ON r.name = 'super-admin'
-- WHERE u.username = 'admin1'
-- ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------------
-- D) Verify
-- -----------------------------------------------------------------------------

SELECT u.id, u.username, u.first_name, u.last_name, u.is_active,
       COALESCE(string_agg(r.name, ', ' ORDER BY r.name), '') AS roles
FROM users u
LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.is_active = true
LEFT JOIN roles r ON r.id = ur.role_id
GROUP BY u.id
ORDER BY u.id;

COMMIT;
