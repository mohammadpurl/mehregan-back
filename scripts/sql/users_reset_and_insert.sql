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
    ('mjyounesi',        'younesi@gmail.com',        '09128177521', 'محمدجلال', 'یونسی',   '$2b$12$EMwdoIevUMu3XkltccsFSeymFSCdsvQ0fkVP085YUMXygmjb3zGb2', true, NOW()),
    ('mardi',    'mardi@gmail.com',    '09123120953', 'محمدرضا', 'مردی',       '$2b$12$skCO7WzwXFft59KxAeXV8OtN72Uuru6/TOC/LBy0fx86BEc/MBeqa', true, NOW()),
    ('moniri',  'moniri@gmail.com',  '09120000003', 'مدیر پروژه', 'منیری',      '$2b$12$X4oosdmqRJDADHMRM9hBbuxla.MBPeIcj1n7jvhfZq.5nRCFyR4pS', true, NOW()),
    ('bagherian',    'bagherian@gmail.com',    '09120000004',  'مدیر پروژه', 'باقریان',    '$2b$12$evZRe1Bl.ECmwheXr0k1MOtGsmqgjR2RteCkVBxX7skhvJ/.TBEky', true, NOW()),
    ('rahimi',  'rahimi@gmail.com',  '09120000005', 'مدیرمالی', 'رحیمی', '$2b$12$ClZE5iDTJjHzQbCXGufvS.3rJK4cTUt4xPLNsAHuJe3fcBbGKK4m.', true, NOW()),
    ('haghighi',  'haghighi@gmail.com',  '09120000006', 'مسئول خرید', 'حقیقی', '$2b$12$/50UKMsMip3iVoI5PkV53OPGHIzpUi5yMf9AHMKPRtatsbMZAA0ji', true, NOW()),
    ('nazari',      'nazari@gmail.com',      '09120000006', 'کارشناس پروژه', 'نظری',      '$2b$12$cOZvkxE5ocgzGcM3NXB91OW6aW7A3LM.py.WBL7UrFP3UUb/.v9qq', true, NOW()),
    ('nikbin',      'nikbin@gmail.com',      '09120000006', 'اموراداری', 'نیک بین',      '$2b$12$7AlDrk45rjMx6bfMDdVvFOcn9Sec76XgK7rNDCse6tekuvxysCqr.', true, NOW()),
    ('hejazifar',      'hejazifar@gmail.com',      '09120000006', 'سرپرست مالی', 'حجازی فر',      '$2b$12$d/33ZsGifs5wwIeza35LD.npiDPtNVK4Ky0rDy3tFJ56rqhPpXQzK', true, NOW()),
    ('alizadeh',      'alizadeh@gmail.com',      '09120000006', 'سرپرست انبار', 'الیزاده',      '$2b$12$3grq7.GjHnXXPvWAJPRlleIAKpqcZw7G8Jan4ZLxBrV4NKlun95Fy', true, NOW()),
    ('torkaman',      'torkaman@gmail.com',      '09120000006', 'کارسناس مالی', 'ترکمان',      '$2b$12$K/fliXGP.rhj4hgCbmveHOdM2CWtVBulEbJV9gRfqxsasWrX/cIZC', true, NOW()),
    ('mehrvarz',      'mehrvarz@gmail.com',      '09120000006', 'کارسناس دفتر مشهد', 'مهرورز',      '$2b$12$8B1pf5PnTVMD7vG9XHuus.2VuwATguyYU29ECdqt23HUyXPVrjwEK', true, NOW()),
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
