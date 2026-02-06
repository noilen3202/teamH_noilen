-- 権限レベル
CREATE TYPE admin_role AS ENUM ('OrgAdmin', 'Staff');

-- 性別
CREATE TYPE volunteer_gender AS ENUM ('Male', 'Female', 'Other', 'Unspecified');

-- 募集ステータス
CREATE TYPE recruitment_status AS ENUM ('Draft', 'Open', 'Closed');

-- 応募ステータス
CREATE TYPE application_status AS ENUM ('Pending', 'Approved', 'Rejected');

-- 1. SuperAdmins (システム自体の管理人)
CREATE TABLE SuperAdmins (
    super_admin_id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash CHAR(60) NOT NULL
);

-- 2. Prefectures (県の情報)
CREATE TABLE Prefectures (
    prefecture_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE
);

-- 3. Organizations (市区町村の情報)
CREATE TABLE Organizations (
    organization_id SERIAL PRIMARY KEY,
    prefecture_id INTEGER NOT NULL REFERENCES Prefectures(prefecture_id), -- 所属する県ID
    name VARCHAR(255) NOT NULL UNIQUE,
    application_date DATE,
    is_active BOOLEAN DEFAULT TRUE
);

-- 4. AdminUsers (組織の職員アカウント)
CREATE TABLE AdminUsers (
    admin_id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES Organizations(organization_id),
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash CHAR(60) NOT NULL,
    role admin_role NOT NULL
);

-- 5. Volunteers (ボランティア登録者)
CREATE TABLE Volunteers (
    volunteer_id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES Organizations(organization_id),
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash CHAR(60) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    mynumber VARCHAR(12), -- マイナンバー用のカラム
    birth_year SMALLINT,
    gender volunteer_gender,
    phone_number VARCHAR(20),
    email VARCHAR(255),
    postal_code VARCHAR(8),
    address VARCHAR(500),
    registration_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_volunteers_full_name ON Volunteers (full_name);

-- 6. Recruitments (募集案件)
CREATE TABLE Recruitments (
    recruitment_id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES Organizations(organization_id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_date DATE NOT NULL,
    end_date DATE,
    status recruitment_status DEFAULT 'Draft',
    contact_phone_number VARCHAR(20),
    contact_email VARCHAR(255) NOT NULL DEFAULT ''
);
CREATE INDEX idx_recruitments_status ON Recruitments (status);

-- 7. Applications (応募情報)
CREATE TABLE Applications (
    application_id SERIAL PRIMARY KEY,
    recruitment_id INTEGER NOT NULL REFERENCES Recruitments(recruitment_id),
    volunteer_id INTEGER NOT NULL REFERENCES Volunteers(volunteer_id),
    application_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status application_status DEFAULT 'Pending',
    UNIQUE (recruitment_id, volunteer_id) 
);

-- 8. RecruitmentCategories (カテゴリテーブル)
CREATE TABLE RecruitmentCategories (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. RecruitmentCategoryMap (募集案件とカテゴリの中間テーブル)
CREATE TABLE RecruitmentCategoryMap (
    recruitment_id INTEGER NOT NULL REFERENCES Recruitments(recruitment_id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES RecruitmentCategories(category_id) ON DELETE CASCADE,
    PRIMARY KEY (recruitment_id, category_id)
);

-- 10. VolunteerCategoryInterests (ボランティアと興味カテゴリの中間テーブル)
CREATE TABLE VolunteerCategoryInterests (
    volunteer_id INTEGER NOT NULL REFERENCES Volunteers(volunteer_id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES RecruitmentCategories(category_id) ON DELETE CASCADE,
    PRIMARY KEY (volunteer_id, category_id)
);

-- 11. VolunteerFavoriteOrganizations (ボランティアのお気に入り市区町村)
CREATE TABLE VolunteerFavoriteOrganizations (
    volunteer_id INTEGER NOT NULL REFERENCES Volunteers(volunteer_id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES Organizations(organization_id) ON DELETE CASCADE,
    PRIMARY KEY (volunteer_id, organization_id)
);
