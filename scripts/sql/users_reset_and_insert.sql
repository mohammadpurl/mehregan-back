-- =============================================================================
-- Mehreagan ERP — reset users + insert (PostgreSQL)
-- Run:
--   Get-Content .\scripts\sql\users_reset_and_insert.sql -Raw -Encoding UTF8 |
--     docker compose exec -T postgres psql -U postgres -d task_management
-- =============================================================================

BEGIN;

DELETE FROM user_roles;
UPDATE users SET manager_id = NULL;
DELETE FROM users;
SELECT setval(pg_get_serial_sequence('users', 'id'), 1, false);

-- No trailing comma before ON CONFLICT
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
    ('mjyounesi',  'younesi@gmail.com',    '09128177521', 'محمدجلال',           'یونسی',    '$2b$12$EMwdoIevUMu3XkltccsFSeymFSCdsvQ0fkVP085YUMXygmjb3zGb2', true, NOW()),
    ('mardi',      'mardi@gmail.com',      '09123120953', 'محمدرضا',            'مردی',     '$2b$12$skCO7WzwXFft59KxAeXV8OtN72Uuru6/TOC/LBy0fx86BEc/MBeqa', true, NOW()),
    ('moniri',     'moniri@gmail.com',     '09120000003', 'مدیر پروژه',         'منیری',    '$2b$12$X4oosdmqRJDADHMRM9hBbuxla.MBPeIcj1n7jvhfZq.5nRCFyR4pS', true, NOW()),
    ('bagherian',  'bagherian@gmail.com',  '09120000004', 'مدیر پروژه',         'باقریان',  '$2b$12$evZRe1Bl.ECmwheXr0k1MOtGsmqgjR2RteCkVBxX7skhvJ/.TBEky', true, NOW()),
    ('rahimi',     'rahimi@gmail.com',     '09120000005', 'مدیرمالی',           'رحیمی',    '$2b$12$ClZE5iDTJjHzQbCXGufvS.3rJK4cTUt4xPLNsAHuJe3fcBbGKK4m.', true, NOW()),
    ('haghighi',   'haghighi@gmail.com',   '09120000006', 'مسئول خرید',         'حقیقی',    '$2b$12$/50UKMsMip3iVoI5PkV53OPGHIzpUi5yMf9AHMKPRtatsbMZAA0ji', true, NOW()),
    ('nazari',     'nazari@gmail.com',     '09120000007', 'کارشناس پروژه',      'نظری',     '$2b$12$cOZvkxE5ocgzGcM3NXB91OW6aW7A3LM.py.WBL7UrFP3UUb/.v9qq', true, NOW()),
    ('nikbin',     'nikbin@gmail.com',     '09120000008', 'امور اداری',         'نیک بین',  '$2b$12$7AlDrk45rjMx6bfMDdVvFOcn9Sec76XgK7rNDCse6tekuvxysCqr.', true, NOW()),
    ('hejazifar',  'hejazifar@gmail.com',  '09120000009', 'سرپرست مالی',        'حجازی فر', '$2b$12$d/33ZsGifs5wwIeza35LD.npiDPtNVK4Ky0rDy3tFJ56rqhPpXQzK', true, NOW()),
    ('alizadeh',   'alizadeh@gmail.com',   '09120000010', 'سرپرست انبار',       'الیزاده',  '$2b$12$3grq7.GjHnXXPvWAJPRlleIAKpqcZw7G8Jan4ZLxBrV4NKlun95Fy', true, NOW()),
    ('torkaman',   'torkaman@gmail.com',   '09120000011', 'کارشناس مالی',       'ترکمان',   '$2b$12$K/fliXGP.rhj4hgCbmveHOdM2CWtVBulEbJV9gRfqxsasWrX/cIZC', true, NOW()),
    ('mehrvarz',   'mehrvarz@gmail.com',   '09120000012', 'کارشناس دفتر مشهد',  'مهرورز',   '$2b$12$8B1pf5PnTVMD7vG9XHuus.2VuwATguyYU29ECdqt23HUyXPVrjwEK', true, NOW())
ON CONFLICT (username) DO UPDATE SET
    email = EXCLUDED.email,
    mobile = EXCLUDED.mobile,
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    hashed_password = EXCLUDED.hashed_password,
    is_active = true;

-- Role assignments (usernames must match VALUES above)
INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true FROM users u JOIN roles r ON r.name = 'ceo'
WHERE u.username = 'mjyounesi'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true FROM users u JOIN roles r ON r.name = 'managing_director'
WHERE u.username = 'mardi'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true FROM users u JOIN roles r ON r.name = 'requester'
WHERE u.username IN ('moniri', 'bagherian', 'nazari', 'nikbin', 'mehrvarz')
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true FROM users u JOIN roles r ON r.name = 'finance_manager'
WHERE u.username = 'rahimi'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true FROM users u JOIN roles r ON r.name = 'procurement_officer'
WHERE u.username = 'haghighi'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true FROM users u JOIN roles r ON r.name = 'accountant'
WHERE u.username IN ('hejazifar', 'torkaman')
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

INSERT INTO user_roles (user_id, role_id, is_active)
SELECT u.id, r.id, true FROM users u JOIN roles r ON r.name = 'warehouse_manager'
WHERE u.username = 'alizadeh'
ON CONFLICT ON CONSTRAINT uq_user_role_pair DO NOTHING;

-- Verify
SELECT u.id, u.username, u.first_name, u.last_name, u.is_active,
       COALESCE(string_agg(r.name, ', ' ORDER BY r.name), '') AS roles
FROM users u
LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.is_active = true
LEFT JOIN roles r ON r.id = ur.role_id
GROUP BY u.id
ORDER BY u.id;

COMMIT;
