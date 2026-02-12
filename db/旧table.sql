

-- 1. SuperAdmins (システム自体の管理人)
CREATE TABLE SuperAdmins (
    super_admin_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'システム管理者のID',
    username VARCHAR(100) NOT NULL UNIQUE COMMENT 'ログインユーザー名',
    password_hash CHAR(60) NOT NULL COMMENT 'パスワードのハッシュ値 (例: bcrypt)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='システム全体の管理者アカウント';

-- 2. Organizations (市区町村)
CREATE TABLE Organizations (
    organization_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '市区町村のID',
    name VARCHAR(255) NOT NULL UNIQUE COMMENT '市区町村名',
    application_date DATE COMMENT 'アプリ使用申請日',
    is_active BOOLEAN DEFAULT TRUE COMMENT 'アプリ使用状況 (TRUE: 使用中, FALSE: 停止中)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='アプリを利用する市区町村の情報';

-- 3. AdminUsers (市区町村の職員アカウント)
CREATE TABLE AdminUsers (
    admin_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '職員アカウントのID',
    organization_id INT UNSIGNED NOT NULL COMMENT '所属する市区町村ID',
    username VARCHAR(100) NOT NULL UNIQUE COMMENT 'ログインユーザー名',
    password_hash CHAR(60) NOT NULL COMMENT 'パスワードのハッシュ値',
    role ENUM('OrgAdmin', 'Staff') NOT NULL COMMENT '権限レベル (OrgAdmin: 市の管理者, Staff: 一般職員)',
    FOREIGN KEY (organization_id) REFERENCES Organizations(organization_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='市区町村職員のアカウント情報';

-- 4. Volunteers (ボランティア登録者)
CREATE TABLE Volunteers (
    volunteer_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'ボランティアのID',
    organization_id INT UNSIGNED NOT NULL COMMENT '登録を行った市区町村ID',
    username VARCHAR(100) NOT NULL UNIQUE COMMENT 'ログインユーザー名',
    password_hash CHAR(60) NOT NULL COMMENT 'パスワードのハッシュ値',
    full_name VARCHAR(100) NOT NULL COMMENT '氏名',
    birth_year SMALLINT UNSIGNED COMMENT '生年',
    gender ENUM('Male', 'Female', 'Other', 'Unspecified') COMMENT '性別',
    phone_number VARCHAR(20) COMMENT '電話番号',
    email VARCHAR(255) COMMENT 'メールアドレス',
    -- 追加: 郵便番号と住所
    postal_code VARCHAR(8) COMMENT '郵便番号 (ハイフン含む最大8桁)',
    address VARCHAR(500) COMMENT '住所',
    -- /追加
    registration_date DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '登録日時',
    FOREIGN KEY (organization_id) REFERENCES Organizations(organization_id),
    INDEX idx_name (full_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ボランティア個人の情報およびログイン情報';

-- 5. Recruitments (募集案件)
CREATE TABLE Recruitments (
    recruitment_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '募集案件のID',
    organization_id INT UNSIGNED NOT NULL COMMENT '募集を出した市区町村ID',
    title VARCHAR(255) NOT NULL COMMENT '募集タイトル',
    description TEXT COMMENT '募集詳細',
    start_date DATE NOT NULL COMMENT '募集開始日',
    end_date DATE COMMENT '募集終了日',
    status ENUM('Draft', 'Open', 'Closed') DEFAULT 'Draft' COMMENT '募集ステータス (Draft: 下書き, Open: 募集中, Closed: 終了)',
    contact_phone_number VARCHAR(20) COMMENT '募集詳細に表示する問い合わせ電話番号',
    FOREIGN KEY (organization_id) REFERENCES Organizations(organization_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='市区町村が掲載するボランティア募集の詳細';

-- 6. Applications (応募情報)
CREATE TABLE Applications (
    application_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '応募のID',
    recruitment_id INT UNSIGNED NOT NULL COMMENT '応募した募集案件ID',
    volunteer_id INT UNSIGNED NOT NULL COMMENT '応募したボランティアID',
    application_date DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '応募日時',
    status ENUM('Pending', 'Approved', 'Rejected') DEFAULT 'Pending' COMMENT '応募ステータス (Pending: 審査中, Approved: 承認, Rejected: 不承認)',
    UNIQUE KEY uk_recruitment_volunteer (recruitment_id, volunteer_id) COMMENT '同じ募集への重複応募を防ぐ',
    FOREIGN KEY (recruitment_id) REFERENCES Recruitments(recruitment_id),
    FOREIGN KEY (volunteer_id) REFERENCES Volunteers(volunteer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ボランティアが募集案件に応募した情報';

-- 7. Inquiries (問い合わせ)
CREATE TABLE Inquiries (
    inquiry_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '問い合わせのID',
    recruitment_id INT UNSIGNED NOT NULL COMMENT '問い合わせ対象の募集案件ID',
    volunteer_id INT UNSIGNED COMMENT '問い合わせを行ったボランティアID (未ログインユーザーからの問い合わせも考慮する場合はNULL可)',
    inquiry_text TEXT NOT NULL COMMENT '問い合わせ内容',
    inquiry_date DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '問い合わせ日時',
    response_text TEXT COMMENT '職員からの回答内容',
    response_date DATETIME COMMENT '回答日時',
    FOREIGN KEY (recruitment_id) REFERENCES Recruitments(recruitment_id),
    FOREIGN KEY (volunteer_id) REFERENCES Volunteers(volunteer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='募集案件ごとの問い合わせ履歴';


--カテゴリーテーブル
CREATE TABLE RecruitmentCategories (
    category_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT 'カテゴリID',
    category_name VARCHAR(100) NOT NULL UNIQUE COMMENT 'カテゴリ名 (例: 清掃, 事務作業, イベント運営)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '作成日時'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='募集案件を分類するためのカテゴリ';


--中間テーブル
CREATE TABLE RecruitmentCategoryMap (
    recruitment_id INT UNSIGNED NOT NULL COMMENT '募集案件のID',
    category_id INT UNSIGNED NOT NULL COMMENT 'カテゴリID',
    
    PRIMARY KEY (recruitment_id, category_id) COMMENT '複合主キー（重複登録を防止）',
    
    FOREIGN KEY (recruitment_id) REFERENCES Recruitments(recruitment_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES RecruitmentCategories(category_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='募集案件とカテゴリの多対多リレーション';

CREATE TABLE VolunteerCategoryInterests (
    volunteer_id INT UNSIGNED NOT NULL COMMENT 'ボランティアのID',
    category_id INT UNSIGNED NOT NULL COMMENT '興味のあるカテゴリID',

    PRIMARY KEY (volunteer_id, category_id) COMMENT '複合主キー（重複登録を防止）',

    -- ボランティアが削除されたら、関連する興味情報も削除
    FOREIGN KEY (volunteer_id) REFERENCES Volunteers(volunteer_id) ON DELETE CASCADE,
    -- カテゴリが削除されたら、関連する興味情報も削除
    FOREIGN KEY (category_id) REFERENCES RecruitmentCategories(category_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ボランティアと興味のあるカテゴリの多対多リレーション';




ALTER TABLE Recruitments
ADD COLUMN contact_email VARCHAR(255) NOT NULL DEFAULT '' COMMENT '募集詳細に表示する問い合わせメールアドレス' AFTER contact_phone_number;