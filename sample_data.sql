-- sample_data.sql
-- This file contains sample data for the tables defined in table.sql.
-- Note: Passwords are placeholders and should be replaced with actual hashed passwords.

-- 1. Prefectures
INSERT INTO Prefectures (prefecture_id, name, is_active) VALUES
(1, '東京都', TRUE),
(2, '大阪府', TRUE),
(3, '北海道', TRUE)
ON CONFLICT (prefecture_id) DO NOTHING;

-- 2. Organizations
-- Note: prefecture_id must exist in the Prefectures table.
INSERT INTO Organizations (organization_id, prefecture_id, name, application_date, is_active) VALUES
(1, 1, '渋谷区', '2024-01-10', TRUE),
(2, 1, '新宿区', '2024-02-05', TRUE),
(3, 2, '大阪市北区', '2024-03-15', TRUE),
(4, 3, '札幌市中央区', '2024-04-20', TRUE)
ON CONFLICT (organization_id) DO NOTHING;

-- 3. RecruitmentCategories
INSERT INTO RecruitmentCategories (category_id, category_name) VALUES
(1, '高齢者支援'),
(2, '子ども食堂'),
(3, '環境美化'),
(4, 'イベント手伝い'),
(5, '防災・災害支援')
ON CONFLICT (category_id) DO NOTHING;

-- 4. SuperAdmins
-- Note: Replace '<hashed_password_placeholder>' with a real bcrypt hash.
INSERT INTO SuperAdmins (super_admin_id, username, password_hash) VALUES
(1, 'superadmin', '$2b$12$fzo.TjSg3h.hYxJ4.2sA/eE5N5c.C/1xGz.iP3w.d.p.s.Q.w.z.K')
ON CONFLICT (super_admin_id) DO NOTHING;

-- 5. AdminUsers
-- Note: organization_id must exist in the Organizations table.
-- Note: Replace '<hashed_password_placeholder>' with a real bcrypt hash.
INSERT INTO AdminUsers (admin_id, organization_id, username, password_hash, role) VALUES
(1, 1, 'shibuya_admin', '$2b$12$fzo.TjSg3h.hYxJ4.2sA/eE5N5c.C/1xGz.iP3w.d.p.s.Q.w.z.K', 'OrgAdmin'),
(2, 1, 'shibuya_staff', '$2b$12$fzo.TjSg3h.hYxJ4.2sA/eE5N5c.C/1xGz.iP3w.d.p.s.Q.w.z.K', 'Staff'),
(3, 3, 'osaka_admin', '$2b$12$fzo.TjSg3h.hYxJ4.2sA/eE5N5c.C/1xGz.iP3w.d.p.s.Q.w.z.K', 'OrgAdmin')
ON CONFLICT (admin_id) DO NOTHING;

-- 6. Volunteers
-- Note: organization_id must exist in the Organizations table.
-- Note: Replace '<hashed_password_placeholder>' with a real bcrypt hash.
INSERT INTO Volunteers (volunteer_id, organization_id, username, password_hash, full_name, birth_year, gender, phone_number, email, postal_code, address) VALUES
(1, 1, 'tanaka_ichiro', '$2b$12$fzo.TjSg3h.hYxJ4.2sA/eE5N5c.C/1xGz.iP3w.d.p.s.Q.w.z.K', '田中 一郎', 1995, 'Male', '090-1111-2222', 'ichiro.tanaka@example.com', '150-0002', '東京都渋谷区渋谷1-1-1'),
(2, 2, 'suzuki_hanako', '$2b$12$fzo.TjSg3h.hYxJ4.2sA/eE5N5c.C/1xGz.iP3w.d.p.s.Q.w.z.K', '鈴木 花子', 2001, 'Female', '080-3333-4444', 'hanako.suzuki@example.com', '160-0022', '東京都新宿区新宿2-2-2'),
(3, 3, 'sato_jiro', '$2b$12$fzo.TjSg3h.hYxJ4.2sA/eE5N5c.C/1xGz.iP3w.d.p.s.Q.w.z.K', '佐藤 次郎', 1988, 'Male', '070-5555-6666', 'jiro.sato@example.com', '530-0001', '大阪府大阪市北区梅田3-3-3')
ON CONFLICT (volunteer_id) DO NOTHING;

-- 7. Recruitments
-- Note: organization_id must exist in the Organizations table.
INSERT INTO Recruitments (recruitment_id, organization_id, title, description, start_date, end_date, status, contact_phone_number, contact_email) VALUES
(1, 1, '公園の清掃ボランティア募集', '毎週土曜日の朝、代々木公園の清掃活動を行います。地域をきれいにする活動にぜひご参加ください。', '2025-04-01', '2025-12-31', 'Open', '03-1111-2222', 'shibuya-volunteer@example.com'),
(2, 1, '子ども食堂の配膳スタッフ', '毎週水曜日の夕方、子ども食堂での配膳や片付けをお手伝いいただける方を募集します。', '2025-04-01', '2025-09-30', 'Open', '03-1111-3333', 'shibuya-kids@example.com'),
(3, 3, '夏祭りイベントの運営サポート', '8月に開催される夏祭りの会場設営、当日の案内、後片付けなどをお手伝いいただくボランティアです。', '2025-07-01', '2025-07-31', 'Draft', '06-7777-8888', 'osaka-event@example.com'),
(4, 2, '防災訓練のサポートスタッフ', '地域の防災訓練で、参加者の誘導や資材の配布などを行うスタッフを募集します。', '2025-09-05', '2025-09-05', 'Open', '03-4444-5555', 'shinjuku-bousai@example.com')
ON CONFLICT (recruitment_id) DO NOTHING;

-- 8. Applications
-- Note: recruitment_id and volunteer_id must exist.
INSERT INTO Applications (application_id, recruitment_id, volunteer_id, status) VALUES
(1, 1, 1, 'Approved'),
(2, 1, 2, 'Pending'),
(3, 2, 1, 'Pending'),
(4, 4, 2, 'Approved')
ON CONFLICT (application_id) DO NOTHING;

-- 9. RecruitmentCategoryMap
-- Note: recruitment_id and category_id must exist.
INSERT INTO RecruitmentCategoryMap (recruitment_id, category_id) VALUES
(1, 3),
(2, 2),
(3, 4),
(4, 4),
(4, 5)
ON CONFLICT (recruitment_id, category_id) DO NOTHING;

-- 10. VolunteerCategoryInterests
-- Note: volunteer_id and category_id must exist.
INSERT INTO VolunteerCategoryInterests (volunteer_id, category_id) VALUES
(1, 1),
(1, 3),
(2, 2),
(2, 4),
(3, 5)
ON CONFLICT (volunteer_id, category_id) DO NOTHING;

-- Reset sequences to avoid conflicts with manually inserted IDs
-- This is useful if you want to insert new data via the application after running this script.
SELECT setval('prefectures_prefecture_id_seq', (SELECT MAX(prefecture_id) FROM Prefectures));
SELECT setval('organizations_organization_id_seq', (SELECT MAX(organization_id) FROM Organizations));
SELECT setval('recruitmentcategories_category_id_seq', (SELECT MAX(category_id) FROM RecruitmentCategories));
SELECT setval('superadmins_super_admin_id_seq', (SELECT MAX(super_admin_id) FROM SuperAdmins));
SELECT setval('adminusers_admin_id_seq', (SELECT MAX(admin_id) FROM AdminUsers));
SELECT setval('volunteers_volunteer_id_seq', (SELECT MAX(volunteer_id) FROM Volunteers));
SELECT setval('recruitments_recruitment_id_seq', (SELECT MAX(recruitment_id) FROM Recruitments));
SELECT setval('applications_application_id_seq', (SELECT MAX(application_id) FROM Applications));
