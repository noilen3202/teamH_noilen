# このファイルを実行する前に、以下のライブラリをインストールしてください:
# pip install Flask mysql-connector-python python-dotenv google-cloud-language pandas Flask-Bcrypt Flask-Mail fpdf

import os
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, flash, send_from_directory, send_file
from flask_bcrypt import Bcrypt
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import pandas as pd
from google.cloud import language_v1
import smtplib
import ssl
from email.message import EmailMessage
from flask_mail import Mail, Message
import secrets
from datetime import datetime
from fpdf import FPDF
import io

# .envファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__, static_folder='.', template_folder='.')
app.secret_key = os.urandom(24) # セッション管理のための秘密鍵
bcrypt = Bcrypt(app) # Bcryptの初期化

def format_datetime(value, format_string='%Y-%m-%d'):
    """datetimeオブジェクトをJinja2テンプレート内でフォーマットするためのカスタムフィルタ"""
    if isinstance(value, datetime):
        return value.strftime(format_string)
    # datetimeオブジェクトでない場合は、そのまま返すか、エラーとして扱うこともできます
    return value

# フィルタをJinja環境に 'strftime' という名前で登録
app.jinja_env.filters['strftime'] = format_datetime

# Flask-Mail設定
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("GMAIL_USER")
app.config['MAIL_PASSWORD'] = os.getenv("GMAIL_APP_PASSWORD")
mail = Mail(app)

# アップロードフォルダの設定
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# データベース接続設定
def get_db_connection():
    """データベース接続を取得します。"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            dbname=os.getenv("DB_DATABASE") # PostgreSQL uses dbname instead of database
        )
        return conn
    except psycopg2.Error as err:
        print(f"データベース接続エラー: {err}")
        return None

# ------------------------------
# 公開ページ (HP)
# ------------------------------

@app.route("/")
def index():
    """hp/index.htmlをレンダリングします。"""
    return render_template("hp/index.html")

@app.route("/opportunity/<int:recruitment_id>")
def opportunity_detail(recruitment_id):
    """特定の募集案件の詳細をレンダリングします。"""
    conn = get_db_connection()
    if conn is None:
        return "データベースに接続できませんでした。", 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT recruitment_id, title, description, start_date, end_date, contact_phone_number, image_filename FROM Recruitments WHERE recruitment_id = %s", (recruitment_id,))
        opportunity = cursor.fetchone()
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return "データの取得に失敗しました。", 500
    finally:
        cursor.close()
        conn.close()

    if opportunity is None:
        return "募集案件が見つかりませんでした。", 404
    
    return render_template("hp/opportunity_detail.html", opportunity=opportunity)

@app.route("/hp/dounyu_moushikomi.html")
def dounyu_moushikomi_page():
    """hp/dounyu_moushikomi.htmlをレンダリングします。"""
    return render_template("hp/dounyu_moushikomi.html")

@app.route("/hp/toiawase.html")
def toiawase_page():
    """hp/toiawase.htmlをレンダリングします。"""
    return render_template("hp/toiawase.html")

# ------------------------------
# ユーザー (ボランティア) エリア
# ------------------------------

@app.route('/user/login')
def user_login_page():
    """ユーザーログインページを表示"""
    return render_template('user/userlogin.html')

@app.route('/user/login_process', methods=['POST'])
def user_login_process():
    """ユーザーのログイン処理"""
    email = request.form.get('email')
    password = request.form.get('password')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        cursor.execute("SELECT volunteer_id, full_name, email, phone_number, password_hash FROM Volunteers WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user:
            password_match = False
            try:
                # First, try to check as a hash
                password_match = bcrypt.check_password_hash(user['password_hash'], password)
            except ValueError:
                # If that fails, assume it's a plain text password
                password_match = (user['password_hash'] == password)

            if password_match:
                session['logged_in'] = True
                session['volunteer_id'] = user['volunteer_id']
                session['user_name'] = user['full_name']
                session['user_email'] = user['email']
                session['user_phone'] = user['phone_number']
                return jsonify({'success': True, 'message': 'ログインに成功しました。'})

        return jsonify({'success': False, 'message': 'メールアドレスまたはパスワードが正しくありません。'}), 401
            
    except Exception as e:
        print(f"Database error during login: {e}")
        return jsonify({'error': 'ログイン処理中にエラーが発生しました。'}), 500

@app.route('/user/logout', methods=['POST'])
def user_logout():
    """ユーザーのログアウト処理"""
    session.clear()
    return jsonify({'success': True, 'message': 'ログアウトしました。'})

@app.route('/user/create_account', methods=['POST'])
def user_create_account():
    """ユーザーアカウント作成処理"""
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    password_confirm = request.form.get('password_confirm')

    if not all([name, email, password, password_confirm]):
        return jsonify({'success': False, 'message': '必須フィールドを入力してください。'}), 400
    if password != password_confirm:
        return jsonify({'success': False, 'message': 'パスワードが一致しません。'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cursor.execute("SELECT volunteer_id FROM Volunteers WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'そのメールアドレスは既に使用されています。'}), 400

        # パスワードをハッシュ化して保存するのが望ましい
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        cursor.execute(
            "INSERT INTO Volunteers (organization_id, username, password_hash, full_name, email) VALUES (%s, %s, %s, %s, %s)",
            (1, email, hashed_password, name, email) # organization_idは仮, usernameにemailを仮使用
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'アカウント「{name}」さんを作成しました。'})

    except Exception as e:
        print(f"Database error during account creation: {e}")
        return jsonify({'error': 'アカウント作成中にエラーが発生しました。'}), 500

@app.route('/user/mypage')
def user_mypage():
    """ユーザーのマイページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/mypage.html')

@app.route('/mypage')
def mypage_redirect():
    """/mypageへのアクセスを/user/mypageにリダイレクト"""
    return redirect(url_for('user_mypage'))


@app.route('/user/activity_history')
def user_activity_history():
    """ユーザーの活動履歴ページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/activity_history.html')

@app.route('/user/recruitmentlist')
def user_recruitment_list():
    """ユーザー向けの募集一覧ページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/recruitmentlist.html')

@app.route('/user/recruitmentapply')
def user_recruitment_apply():
    """ユーザー向けの募集応募ページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    # recruitment_id = request.args.get('id') # id can be retrieved here if needed
    return render_template('user/recruitmentapply.html')

@app.route('/user/apply')
def user_apply():
    """ユーザー向けの応募確認ページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/apply.html')

@app.route('/user/applyquestion')
def user_apply_question():
    """ユーザー向けの問い合わせページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/applyquestion.html')

@app.route('/user/applyconfirm')
def user_apply_confirm():
    """ユーザー向けの応募確認ページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/applyconfirm.html')

@app.route('/user/complete')
def user_complete():
    """ユーザー向けの応募完了ページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/complete.html')

@app.route('/user/tiiki')
def user_tiiki():
    """ユーザー向けの絞り込み結果ページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))
    return render_template('user/tiiki.html')






# ------------------------------
# 管理者エリア
# ------------------------------

@app.route("/admin/login", methods=['GET', 'POST'])
def admin_login():
    """管理者ログインページとログイン処理"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            flash("データベースに接続できませんでした。", "error")
            return render_template("admin/login.html")

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM SuperAdmins WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and bcrypt.check_password_hash(user['password_hash'], password): 
            session['admin_user'] = user['username']
            return redirect(url_for('admin_dashboard'))
        else:
            flash("ユーザー名またはパスワードが正しくありません。", "error")
            return redirect(url_for('admin_login'))

    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    """管理者ログアウト処理"""
    session.pop('admin_user', None)
    return redirect(url_for('admin_login'))

@app.route("/admin/dashboard")
def admin_dashboard():
    """管理者ダッシュボード"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    return render_template("admin/platform-admin.html")

@app.route("/admin/analysis")
def admin_analysis():
    """AI分析レポートページ"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    return render_template("admin/analysis.html")

@app.route("/admin/org_register", methods=['GET', 'POST'])
def admin_org_register():
    """市町村登録ページと登録処理"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        org_name = request.form['org_name']
        app_date = request.form['app_date']

        if not org_name or not app_date:
            flash("市町村名と利用申請日の両方を入力してください。", "error")
            return redirect(url_for('admin_org_register'))

        conn = get_db_connection()
        if conn is None:
            flash("データベースに接続できませんでした。", "error")
            return redirect(url_for('admin_org_register'))

        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO Organizations (name, application_date) VALUES (%s, %s)", (org_name, app_date))
            conn.commit()
            flash(f"市町村「{org_name}」を登録しました。", "success")
        except psycopg2.Error as err:
            if err.errno == 1062:
                flash(f"市町村「{org_name}」は既に登録されています。", "error")
            else:
                flash(f"登録中にエラーが発生しました: {err}", "error")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('admin_org_register'))

    return render_template("admin/org_register.html")

@app.route("/admin/org_admin_management", methods=['GET', 'POST'])
def admin_org_admin_management():
    """市町村管理者アカウント管理ページ"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("admin/org_admin_management.html", admins=[], orgs=[])

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        org_id = request.form['org_id']
        role = request.form['role']

        if not all([username, password, org_id, role]):
            flash("すべてのフィールドを入力してください。", "error")
        else:
            pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            try:
                cursor.execute("INSERT INTO AdminUsers (organization_id, username, password_hash, role) VALUES (%s, %s, %s, %s)",
                               (org_id, username, pw_hash, role))
                conn.commit()
                flash(f"管理者アカウント「{username}」を作成しました。", "success")
            except psycopg2.Error as err:
                if err.errno == 1062:
                    flash(f"ユーザー名「{username}」は既に使用されています。", "error")
                else:
                    flash(f"アカウント作成中にエラーが発生しました: {err}", "error")
                conn.rollback()
        
        cursor.close()
        conn.close()
        return redirect(url_for('admin_org_admin_management'))

    cursor.execute("""
        SELECT u.username, u.role, o.name as organization_name
        FROM AdminUsers u
        JOIN Organizations o ON u.organization_id = o.organization_id
        ORDER BY u.username
    """)
    admins = cursor.fetchall()
    cursor.execute("SELECT organization_id, name FROM Organizations ORDER BY name")
    orgs = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("admin/org_admin_management.html", admins=admins, orgs=orgs)

@app.route('/admin/org_admin/delete/<string:username>', methods=['POST'])
def admin_org_admin_delete(username):
    """市町村管理者アカウントを削除する"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return redirect(url_for('admin_org_admin_management'))

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM AdminUsers WHERE username = %s", (username,))
        conn.commit()
        flash(f"アカウント「{username}」を削除しました。", "success")
    except psycopg2.Error as err:
        flash(f"削除中にエラーが発生しました: {err}", "error")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('admin_org_admin_management'))

@app.route('/admin/org_admin/edit/<string:username>', methods=['GET', 'POST'])
def admin_org_admin_edit(username):
    """市町村管理者アカウントを編集する"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return redirect(url_for('admin_org_admin_management'))

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == 'POST':
        org_id = request.form['org_id']
        role = request.form['role']
        password = request.form.get('password')

        if password:
            pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            cursor.execute("UPDATE AdminUsers SET organization_id = %s, role = %s, password_hash = %s WHERE username = %s",
                           (org_id, role, pw_hash, username))
        else:
            cursor.execute("UPDATE AdminUsers SET organization_id = %s, role = %s WHERE username = %s",
                           (org_id, role, username))
        
        conn.commit()
        flash(f"アカウント「{username}」を更新しました。", "success")
        cursor.close()
        conn.close()
        return redirect(url_for('admin_org_admin_management'))

    cursor.execute("SELECT * FROM AdminUsers WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.execute("SELECT organization_id, name FROM Organizations ORDER BY name")
    orgs = cursor.fetchall()
    cursor.close()
    conn.close()

    if not user:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for('admin_org_admin_management'))

    return render_template("admin/org_admin_edit.html", user=user, orgs=orgs)

@app.route("/admin/category_management", methods=['GET', 'POST'])
def admin_category_management():
    """カテゴリー管理ページ"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("admin/category_management.html", categories=[])

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == 'POST':
        category_name = request.form.get('category_name')
        if not category_name:
            flash("カテゴリー名を入力してください。", "error")
        else:
            try:
                cursor.execute("INSERT INTO RecruitmentCategories (category_name) VALUES (%s)", (category_name,))
                conn.commit()
                flash(f"カテゴリー「{category_name}」を追加しました。", "success")
            except psycopg2.Error as err:
                if err.errno == 1062:
                    flash(f"カテゴリー「{category_name}」は既に存在します。", "error")
                else:
                    flash(f"登録中にエラーが発生しました: {err}", "error")
                conn.rollback()
        
        cursor.close()
        conn.close()
        return redirect(url_for('admin_category_management'))

    cursor.execute("SELECT * FROM RecruitmentCategories ORDER BY category_name")
    categories = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("admin/category_management.html", categories=categories)

@app.route('/admin/category/delete/<int:category_id>', methods=['POST'])
def admin_category_delete(category_id):
    """カテゴリーを削除する"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return redirect(url_for('admin_category_management'))

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM RecruitmentCategories WHERE category_id = %s", (category_id,))
        conn.commit()
        flash(f"カテゴリーを削除しました。", "success")
    except psycopg2.Error as err:
        flash(f"削除中にエラーが発生しました: {err}", "error")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('admin_category_management'))

@app.route('/admin/category/edit/<int:category_id>', methods=['GET', 'POST'])
def admin_category_edit(category_id):
    """カテゴリーを編集する"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return redirect(url_for('admin_category_management'))

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == 'POST':
        category_name = request.form.get('category_name')
        if not category_name:
            flash("カテゴリー名を入力してください。", "error")
            return redirect(url_for('admin_category_edit', category_id=category_id))
        
        try:
            cursor.execute("UPDATE RecruitmentCategories SET category_name = %s WHERE category_id = %s", (category_name, category_id))
            conn.commit()
            flash(f"カテゴリー名を「{category_name}」に更新しました。", "success")
            return redirect(url_for('admin_category_management'))
        except psycopg2.Error as err:
            if err.errno == 1062:
                flash(f"カテゴリー「{category_name}」は既に存在します。", "error")
            else:
                flash(f"更新中にエラーが発生しました: {err}", "error")
            conn.rollback()
            return redirect(url_for('admin_category_edit', category_id=category_id))
        finally:
            cursor.close()
            conn.close()

    cursor.execute("SELECT * FROM RecruitmentCategories WHERE category_id = %s", (category_id,))
    category = cursor.fetchone()
    cursor.close()
    conn.close()

    if not category:
        flash("指定されたカテゴリーが見つかりません。", "error")
        return redirect(url_for('admin_category_management'))

    return render_template("admin/category_edit.html", category=category)

@app.route("/admin/superadmin_management", methods=['GET', 'POST'])
def admin_superadmin_management():
    """SuperAdminアカウントの管理ページ"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("admin/superadmin_management.html", superadmins=[])

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        if not all([username, password, password_confirm]):
            flash("すべてのフィールドを入力してください。", "error")
        elif password != password_confirm:
            flash("パスワードが一致しません。", "error")
        else:
            pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            try:
                cursor.execute("INSERT INTO SuperAdmins (username, password_hash) VALUES (%s, %s)", (username, pw_hash))
                conn.commit()
                flash(f"SuperAdminアカウント「{username}」を作成しました。", "success")
            except psycopg2.Error as err:
                if err.errno == 1062:
                    flash(f"ユーザー名「{username}」は既に使用されています。", "error")
                else:
                    flash(f"アカウント作成中にエラーが発生しました: {err}", "error")
                conn.rollback()
        
        cursor.close()
        conn.close()
        return redirect(url_for('admin_superadmin_management'))

    cursor.execute("SELECT super_admin_id, username FROM SuperAdmins ORDER BY username")
    superadmins = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("admin/superadmin_management.html", superadmins=superadmins)

@app.route('/admin/superadmin/delete/<string:username>', methods=['POST'])
def admin_superadmin_delete(username):
    """SuperAdminアカウントを削除する"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    
    if username == session['admin_user']:
        flash("自分自身のアカウントは削除できません。", "error")
        return redirect(url_for('admin_superadmin_management'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return redirect(url_for('admin_superadmin_management'))

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM SuperAdmins WHERE username = %s", (username,))
        conn.commit()
        flash(f"アカウント「{username}」を削除しました。", "success")
    except psycopg2.Error as err:
        flash(f"削除中にエラーが発生しました: {err}", "error")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('admin_superadmin_management'))

# ------------------------------
# API エンドポイント
# ------------------------------

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """アップロードされたファイルを配信するためのルート"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/api/opportunities")
def get_opportunities():
    """募集中のボランティア情報をデータベースから取得してJSONで返します。"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("""
            SELECT 
                r.recruitment_id, r.title, r.description, r.start_date, r.end_date,
                MIN(rc.category_name) as category_name
            FROM Recruitments r
            LEFT JOIN RecruitmentCategoryMap rcm ON r.recruitment_id = rcm.recruitment_id
            LEFT JOIN RecruitmentCategories rc ON rcm.category_id = rc.category_id
            WHERE r.status = 'Open'
            GROUP BY r.recruitment_id
        """)
        opportunities = cursor.fetchall()
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": "データの取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(opportunities)

@app.route("/api/send_inquiry", methods=["POST"])
def send_inquiry():
    """問い合わせフォームのデータを処理し、指定されたGmailアドレスにメールを送信します。"""
    data = request.json
    required_fields = ["municipality_name", "contact_person_name", "inquiry_content", "reply_email"]
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": "必須項目が不足しています。"}), 400

    gmail_user = os.getenv("GMAIL_USER")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
    recipient_email = gmail_user

    if not gmail_user or not gmail_app_password:
        return jsonify({"error": "メール送信設定が不完全です。"}), 500

    msg = EmailMessage()
    inquiry_type = data.get("inquiry_type")
    if inquiry_type == 'adoption':
        msg["Subject"] = f"【導入申し込み】: {data['municipality_name']}"
        body_intro = "以下の内容で導入申し込みがありました。"
        content_label = "ご要望・ご質問など"
    else:
        msg["Subject"] = f"地域支援Hubからのお問い合わせ: {data['municipality_name']}"
        body_intro = "以下の内容でお問い合わせがありました。"
        content_label = "お問い合わせ内容"

    msg["From"] = gmail_user
    msg["To"] = recipient_email
    msg["Reply-To"] = data["reply_email"]
    body = f"""
{body_intro}
--------------------------------
市町村の役場などの名前: {data["municipality_name"]}
担当者の名前: {data["contact_person_name"]}
返答用メールアドレス: {data["reply_email"]}
電話番号: {data.get("phone_number", "N/A")}

{content_label}:
{data["inquiry_content"]}
"""
    msg.set_content(body)
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg)
        return jsonify({"message": "お問い合わせが正常に送信されました。"}), 200
    except Exception as e:
        print(f"メール送信エラー: {e}")
        return jsonify({"error": f"メールの送信中にエラーが発生しました: {str(e)}"}), 500

@app.route("/api/categories")
def get_categories():
    """カテゴリの一覧をデータベースから取得してJSONで返します。"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT category_id, category_name FROM RecruitmentCategories ORDER BY category_id")
        categories = cursor.fetchall()
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": "カテゴリの取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(categories)

@app.route("/api/organizations")
def get_organizations():
    """導入市町村の一覧をデータベースから取得してJSONで返します。"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT name FROM Organizations WHERE is_active = TRUE ORDER BY name")
        organizations = cursor.fetchall()
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": "市町村一覧の取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(organizations)

@app.route('/api/current_user')
def current_user():
    """ログイン中のユーザー情報を返す"""
    if session.get('logged_in'):
        return jsonify({
            'volunteer_id': session.get('volunteer_id'),
            'name': session.get('user_name'),
            'email': session.get('user_email'),
            'phone': session.get('user_phone')
        })
    return jsonify({'error': 'Not logged in'}), 401

@app.route('/api/recruitments')
def get_recruitments_api():
    """ユーザー向けに募集一覧をJSONで返す。住所（市町村名）での絞り込みに対応。"""
    address = request.args.get('address') # 住所パラメータを取得
    recruitments = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        params = []
        query = """
            SELECT
                r.recruitment_id, r.title, r.description, o.name as organization_name,
                (SELECT c.category_name FROM RecruitmentCategories c
                 JOIN RecruitmentCategoryMap cm ON c.category_id = cm.category_id
                 WHERE cm.recruitment_id = r.recruitment_id LIMIT 1) AS category
            FROM Recruitments r
            JOIN Organizations o ON r.organization_id = o.organization_id
            WHERE r.status = 'Open'
        """
        
        if address:
            query += " AND o.name LIKE %s"
            params.append(f"%{address}%")
            
        query += " ORDER BY r.start_date DESC"
        
        cursor.execute(query, tuple(params))
        recruitments = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"error": "データベースの取得に失敗しました。"}), 500
    return jsonify(recruitments)


@app.route('/api/recruitments/<int:recruitment_id>')
def get_recruitment_detail_json(recruitment_id):
    """募集詳細をJSONで返す"""
    recruitment = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = """
            SELECT 
                r.recruitment_id, r.title, r.description, r.start_date, r.end_date, r.contact_phone_number, r.contact_email,
                (SELECT c.category_name FROM RecruitmentCategories c
                 JOIN RecruitmentCategoryMap cm ON c.category_id = cm.category_id
                 WHERE cm.recruitment_id = r.recruitment_id LIMIT 1) AS category
            FROM Recruitments r
            WHERE r.recruitment_id = %s
        """
        cursor.execute(query, (recruitment_id,))
        recruitment = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"error": "データベースの取得に失敗しました。"}), 500
    if recruitment is None:
        return jsonify({"error": "指定された募集が見つかりません。"}), 404
    if recruitment.get('start_date'):
        recruitment['start_date'] = recruitment['start_date'].strftime('%Y年%m月%d日')
    if recruitment.get('end_date'):
        recruitment['end_date'] = recruitment['end_date'].strftime('%Y年%m月%d日')
    return jsonify(recruitment)

@app.route('/api/my_activities')
def get_my_activities():
    """ログイン中のユーザーの活動履歴を返す"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'error': 'ログインしていません。'}), 401

    volunteer_id = session.get('volunteer_id')
    activities = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = """
            SELECT
                a.application_id, r.recruitment_id, r.title, r.description, r.start_date, r.end_date,
                a.application_date, a.status AS application_status
            FROM Applications a
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id
            JOIN Recruitments r ON a.recruitment_id = r.recruitment_id
            WHERE a.volunteer_id = %s
            ORDER BY a.application_date DESC
        """
        cursor.execute(query, (volunteer_id,))
        activities = cursor.fetchall()
        
        for activity in activities:
            if activity.get('start_date'):
                activity['start_date'] = activity['start_date'].strftime('%Y年%m月%d日')
            if activity.get('end_date'):
                activity['end_date'] = activity['end_date'].strftime('%Y年%m月%d日')
            if activity.get('application_date'):
                activity['application_date'] = activity['application_date'].strftime('%Y年%m月%d日 %H:%M')

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database error fetching activities: {e}")
        return jsonify({'error': '活動履歴の取得に失敗しました。'}), 500
    
    return jsonify(activities)

@app.route('/api/apply', methods=['POST'])
def apply_for_recruitment():
    """ボランティア募集への応募"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'success': False, 'message': '応募するにはログインが必要です。'}), 401

    data = request.get_json()
    recruitment_id = data.get('recruitment_id')
    volunteer_id = session.get('volunteer_id')

    if not recruitment_id:
        return jsonify({'success': False, 'message': '募集IDが指定されていません。'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO Applications (recruitment_id, volunteer_id, application_date, status) VALUES (%s, %s, %s, %s)",
            (recruitment_id, volunteer_id, datetime.now(), 'Pending')
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': '応募が完了しました。'})

    except psycopg2.IntegrityError:
        return jsonify({'success': False, 'message': 'この募集には既に応募済みです。'}), 409
    except Exception as e:
        print(f"Database error during application: {e}")
        return jsonify({'success': False, 'message': '応募処理中にエラーが発生しました。'}), 500

@app.route('/api/inquiries', methods=['POST'])
def post_inquiry():
    """募集に関する問い合わせ"""
    data = request.get_json()
    recruitment_id = data.get('recruitment_id')
    inquiry_text = data.get('inquiry_text')
    inquirer_name = data.get('inquirer_name')
    inquirer_email = data.get('inquirer_email')
    inquirer_phone = data.get('inquirer_phone')
    volunteer_id = session.get('volunteer_id')

    if not all([recruitment_id, inquiry_text, inquirer_name, inquirer_email]):
        return jsonify({'success': False, 'message': '募集ID、問い合わせ内容、お名前、メールアドレスは必須です。'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cursor.execute(
            "INSERT INTO Inquiries (recruitment_id, volunteer_id, inquiry_text, inquiry_date) VALUES (%s, %s, %s, %s)",
            (recruitment_id, volunteer_id, inquiry_text, datetime.now())
        )
        conn.commit()

        cursor.execute("SELECT organization_id, title FROM Recruitments WHERE recruitment_id = %s", (recruitment_id,))
        recruitment_info = cursor.fetchone()
        
        if not recruitment_info:
            raise Exception("Recruitment not found.")

        organization_id = recruitment_info['organization_id']
        recruitment_title = recruitment_info['title']

        cursor.execute("SELECT username FROM AdminUsers WHERE organization_id = %s AND role = 'OrgAdmin' LIMIT 1", (organization_id,))
        admin_user = cursor.fetchone()

        if admin_user and admin_user['username']:
            recipient_email = admin_user['username']
            email_body = f"""
募集案件「{recruitment_title}」に関する新しい問い合わせがあります。

--- 問い合わせ内容 ---
問い合わせ者: {inquirer_name}
メールアドレス: {inquirer_email}
電話番号: {inquirer_phone or '記載なし'}

内容:
{inquiry_text}
--------------------
"""
            msg = Message(
                subject=f"[地域支援Hub] 募集「{recruitment_title}」に関する問い合わせ",
                sender=app.config['MAIL_USERNAME'],
                recipients=[recipient_email],
                body=email_body
            )
            mail.send(msg)
        else:
            print(f"No OrgAdmin email found for organization {organization_id}. Email not sent.")

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': '問い合わせを送信しました。'})

    except Exception as e:
        print(f"Database error during inquiry or email sending: {e}")
        return jsonify({'success': False, 'message': '問い合わせの送信中にエラーが発生しました。'}), 500

@app.route('/api/issue_certificate')
def issue_certificate():
    """ボランティア活動証明書をPDFで発行する"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'error': 'ログインしていません。'}), 401

    application_id = request.args.get('application_id', type=int)
    recruitment_id = request.args.get('recruitment_id', type=int)
    volunteer_id = session.get('volunteer_id')

    if not application_id or not recruitment_id:
        return jsonify({'error': 'application_idとrecruitment_idが必要です。'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        query = """
            SELECT
                v.full_name AS volunteer_name, r.title AS recruitment_title,
                r.description AS recruitment_description, r.start_date AS activity_start_date,
                r.end_date AS activity_end_date, a.application_date
            FROM Applications a
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id
            JOIN Recruitments r ON a.recruitment_id = r.recruitment_id
            WHERE a.application_id = %s AND a.recruitment_id = %s AND a.volunteer_id = %s
        """
        cursor.execute(query, (application_id, recruitment_id, volunteer_id))
        activity_data = cursor.fetchone()
        cursor.close()
        conn.close()

        if not activity_data:
            return jsonify({'error': '指定された活動履歴が見つかりません。'}), 404

        pdf = FPDF()
        # 日本語フォントの追加（絶対パスを使用）
        font_path = os.path.join(app.root_path, 'fonts', 'NotoSansJP-Regular.ttf')
        if not os.path.exists(font_path):
            raise FileNotFoundError("Font file not found at " + font_path)
        pdf.add_font('NotoSansJP', '', font_path, uni=True)
        pdf.set_font('NotoSansJP', '', 12)
        pdf.add_page()
        pdf.rect(5, 5, pdf.w - 10, pdf.h - 10)
        pdf.rect(7, 7, pdf.w - 14, pdf.h - 14)
        pdf.set_font('NotoSansJP', '', 24)
        pdf.ln(15)
        pdf.cell(0, 10, "ボランティア活動証明書", ln=1, align="C")
        pdf.ln(10)
        pdf.set_font('NotoSansJP', '', 14)
        pdf.cell(0, 10, "氏名", ln=1)
        pdf.set_font('NotoSansJP', '', 20)
        pdf.cell(0, 15, f"  {activity_data['volunteer_name']} 様", ln=1)
        pdf.ln(5)
        pdf.set_font('NotoSansJP', '', 12)
        description_text = activity_data['recruitment_description']
        description_width = pdf.w - pdf.l_margin - pdf.r_margin - 50
        lines = pdf.get_string_width(description_text) / description_width
        description_lines = max(1, int(lines) + (1 if lines > int(lines) else 0))
        description_height = description_lines * 10
        if description_height < 15:
            description_height = 15
        pdf.cell(50, description_height, "活動内容:", border=1, ln=0)
        pdf.multi_cell(0, description_height / description_lines, description_text, border=1)
        pdf.cell(50, 10, "活動期間:", border=1, ln=0)
        pdf.multi_cell(0, 10, f"{activity_data['activity_start_date'].strftime('%Y年%m月%d日')} - {activity_data['activity_end_date'].strftime('%Y年%m月%d日')}", border=1)
        pdf.cell(50, 10, "活動時間:", border=1, ln=0)
        pdf.multi_cell(0, 10, "別途記載", border=1)
        pdf.ln(10)
        pdf.set_font('NotoSansJP', '', 12)
        pdf.cell(0, 10, f"発行日: {datetime.now().strftime('%Y年%m月%d日')}", ln=1, align="R")
        pdf.ln(5)
        pdf.cell(0, 10, "地域支援 Hub", ln=1, align="R")
        pdf.cell(0, 10, "[公印]", ln=1, align="R")

        # PDFをメモリ上で生成し、直接送信
        pdf_output = pdf.output(dest='S').encode('latin-1')
        return send_file(
            io.BytesIO(pdf_output),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"ボランティア活動証明書_{activity_data['volunteer_name']}.pdf"
        )

    except Exception as e:
        print(f"Error generating PDF certificate: {e}")
        return jsonify({'error': '証明書の生成に失敗しました。'}), 500

# ------------------------------
# AI分析機能
# ------------------------------

# Google Cloud Natural Language APIの認証情報を環境変数から読み込む
# ai_key/borantelia-ca0b9d410b20.json はリポジリから除外されているため、環境変数から読み込む
if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
    # 環境変数からJSON文字列を読み込み、一時ファイルとして保存
    credentials_json = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
    temp_credentials_path = os.path.join(app.root_path, "temp_google_credentials.json")
    with open(temp_credentials_path, "w") as f:
        f.write(credentials_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_credentials_path
else:
    # ローカル開発環境など、環境変数がない場合は既存のファイルパスを使用
    # ただし、ai_keyディレクトリは.gitignoreで除外されているため、このパスはローカルでのみ有効
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(app.root_path, 'ai_key', 'borantelia-ca0b9d410b20.json')

# Google Cloud Natural Language APIクライアントを初期化
# 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されているため、自動的に認証される
language_client = language_v1.LanguageServiceClient()

def analyze_recruitment_text(text):
    """Google Cloud Natural Language APIを使用して、テキストの感情分析を行います。"""
    try:
        # ここでは既に初期化済みの language_client を使用
        document = language_v1.Document(content=text, type_=language_v1.Document.Type.PLAIN_TEXT, language='ja')
        sentiment = language_client.analyze_sentiment(request={'document': document}).document_sentiment
        return {'sentiment_score': sentiment.score, 'sentiment_magnitude': sentiment.magnitude}
    except Exception as e:
        print(f"Natural Language API Error: {e}")
        return {'sentiment_score': 0, 'sentiment_magnitude': 0, 'error': str(e)}

@app.route('/analyze_popular_factors')
def analyze_popular_factors():
    """DBから求人テキストと応募者数を取得し、相関を分析して結果をJSONで返すAPI"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        query = """
            SELECT 
                r.recruitment_id, r.title, r.description,
                COUNT(a.application_id) AS applicants
            FROM Recruitments r
            LEFT JOIN Applications a ON r.recruitment_id = a.recruitment_id
            GROUP BY r.recruitment_id, r.title, r.description
            ORDER BY applicants DESC;
        """
        cursor.execute(query)
        db_data = cursor.fetchall()
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": "データ取得中にエラーが発生しました。"}), 500
    finally:
        cursor.close()
        conn.close()

    if not db_data:
        return jsonify({"summary": "分析対象のデータがありません。", "details": []})

    analysis_results = []
    for row in db_data:
        recruitment_text = f"{row['title']} {row['description']}"
        nl_result = analyze_recruitment_text(recruitment_text)
        analysis_results.append({
            "id": row['recruitment_id'], "title": row['title'], "description": row['description'],
            "applicants": row['applicants'], "sentiment_score": nl_result.get('sentiment_score', 0),
            "sentiment_magnitude": nl_result.get('sentiment_magnitude', 0)
        })

    df_analysis = pd.DataFrame(analysis_results)
    df_filtered = df_analysis[df_analysis['applicants'] > 0]
    if len(df_filtered) > 1:
        correlation = df_filtered['sentiment_score'].corr(df_filtered['applicants'])
        correlation_summary = f"感情スコアと応募数の相関: {correlation:.2f}"
    else:
        correlation_summary = "相関を計算するにはデータが不十分です。"

    report = {
        "summary": "AIによる人気募集の傾向分析レポート",
        "correlation_sentiment_applicants": correlation_summary,
        "details": df_analysis.to_dict('records')
    }
    return jsonify(report)


# ------------------------------
# 市町村職員（AdminUsers）エリア
# ------------------------------

def check_org_login():
    """市町村職員のログイン状態をチェックするヘルパー関数"""
    # SuperAdminと区別するため、'org_user'セッションキーを使用
    return 'org_user' in session

@app.route("/staff/login", methods=['GET', 'POST'])
def staff_login():
    """市町村職員ログインページとログイン処理"""
    # 既にログイン済みであればメニューにリダイレクト
    if check_org_login():
        return redirect(url_for('staff_menu'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            flash("データベースに接続できませんでした。", "error")
            return render_template("staff/re/staff_login.html")

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # AdminUsersテーブルからユーザーを検索
        cursor.execute("SELECT admin_id, organization_id, username, password_hash, role FROM AdminUsers WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        # bcryptを使用してハッシュ化されたパスワードを比較
        is_password_correct = False
        if user and user.get('password_hash'):
            try:
                is_password_correct = bcrypt.check_password_hash(user['password_hash'], password)
            except ValueError:
                # ハッシュが不正な形式の場合（例：DBに平文パスワードが保存されている）
                # このエラーを握りつぶし、ログイン失敗として扱う
                is_password_correct = False

        if is_password_correct:
            # 認証成功: 必要な情報をセッションに保存
            session['org_user'] = user['username']      # 職員のユーザー名
            session['org_id'] = user['organization_id'] # 所属組織ID
            session['org_role'] = user['role']          # 権限 (OrgAdmin/Staff)
            flash(f"ようこそ、{user['username']}様。", "success")
            return redirect(url_for('staff_menu'))
        else:
            flash("ユーザー名またはパスワードが正しくありません。", "error")
            # ログイン失敗時はフォームを再表示
            return render_template("staff/re/staff_login.html")

    # GETリクエスト: ログインページを表示
    return render_template("staff/re/staff_login.html")

@app.route("/staff/logout")
def staff_logout():
    """職員のログアウト処理。セッションをクリアし、ログイン画面へリダイレクトします。"""
    
    # 🚨 修正: 確実にセッション全体をクリアする 🚨
    session.clear() # これにより、全てのセッションキー（'org_user', 'org_id'など）が削除されます。

    # 「ログアウトしました」というメッセージを flash する
    # Flash Messageはセッションに保存されますが、session.clear()後に再度flashすることで機能します
    flash("ログアウトしました。", "info") 
    
    # ログイン画面へリダイレクト
    return redirect(url_for('staff_login'))

@app.route("/staff/menu")
def staff_menu():
    """市町村職員メニュー（ダッシュボード）。組織名を取得して表示する。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    username = session.get('org_user')
    org_id = session.get('org_id')
    org_role = session.get('org_role')
    org_name = "所属組織不明" # デフォルト値

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        # データベース接続エラーでも、セッション情報だけは表示できるようにする
        context = {
            'username': username,
            'org_id': org_id,
            'org_role': org_role,
            'org_name': org_name
        }
        return render_template("staff/re/staff_menu.html", **context)

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # Organizationsテーブルから組織名を取得
        cursor.execute("SELECT name FROM Organizations WHERE organization_id = %s", (org_id,))
        org_data = cursor.fetchone()
        if org_data:
            org_name = org_data['name']
    except psycopg2.Error as err:
        flash(f"組織情報の取得中にエラーが発生しました: {err}", "error")
    finally:
        cursor.close()
        conn.close()

    # テンプレートに渡す情報に組織名(org_name)を追加
    context = {
        'username': username,
        'org_id': org_id,
        'org_role': org_role,
        'org_name': org_name 
    }
    return render_template("staff/re/staff_menu.html", **context)

@app.route("/staff/recruitment/list")
def staff_opportunity_list_page():
    """職員向けの募集案件一覧ページをレンダリングします。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    # 【修正点】: テンプレートのパスを他のスタッフページに合わせて 'staff/re/' を追記
    return render_template("staff/re/opportunity_list_staff.html")

@app.route("/staff/recruitment/create")
def staff_opportunity_create_page():
    """
    案件作成ページ (opportunity_create.html) を表示します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    # 【修正点】: テンプレートのパスを他のスタッフページに合わせて 'staff/re/' を追記
    return render_template("staff/re/opportunity_create.html")


@app.route("/staff/api/opportunities/all") 
def get_staff_opportunities():
    """
    ログインしている職員の組織IDに紐づく募集案件の一覧をJSONで返します。
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401

    # 【重要修正】: session['organization_id']ではなく、staff_loginで設定された 'org_id' を使用
    org_id = session.get('org_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # 募集人数に関するカラムの取得を削除済み
        cursor.execute("""
            SELECT 
                r.recruitment_id AS id, 
                r.title, 
                r.start_date AS date,     -- 募集開始日を活動日(date)として表示
                r.end_date AS deadline,   -- 募集終了日を締切日(deadline)として表示
                r.status,                 -- DBのステータス (Draft, Open, Closed)
                COUNT(a.application_id) AS applied_count -- 応募レコードの総数
            FROM Recruitments r
            LEFT JOIN Applications a ON r.recruitment_id = a.recruitment_id
            WHERE r.organization_id = %s -- ログインしている職員の組織IDで絞り込み
            GROUP BY r.recruitment_id, r.title, r.start_date, r.end_date, r.status 
            ORDER BY r.end_date DESC
        """, (org_id,))
        
        opportunities = cursor.fetchall()

        # HTML側のJSで使われる status の値に変換 ('published', 'draft', 'closed')
        # DBの status: 'Draft', 'Open', 'Closed'
        for op in opportunities:

            if op['status'] == 'Open':
                op['status'] = 'published'
            elif op['status'] == 'Draft':
                op['status'] = 'draft'
            elif op['status'] == 'Closed':
                op['status'] = 'closed'
            # 日付オブジェクトを文字列に変換 (HTML側で表示するため)
            op['date'] = op['date'].isoformat() if op['date'] else ''
            op['deadline'] = op['deadline'].isoformat() if op['deadline'] else ''

        
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": f"募集案件の取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(opportunities)


@app.route("/staff/user/edit/<string:username>", methods=['GET', 'POST'])
def staff_user_edit(username):
    """職員自身、またはOrgAdminによる職員アカウント編集ページ（OrgAdmin権限のチェックは未実装）"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("user_edit_staff.html") 

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    user_to_edit = None

    if request.method == 'POST':
        # 編集処理（OrgAdmin権限による他ユーザー編集、または本人による編集）
        # パスワード更新処理などを実装する必要がありますが、ここでは省略します。
        
        flash("編集処理が実行されました。（機能未実装）", "success")
        return redirect(url_for('staff_menu'))

    # GETリクエストの処理: 編集対象ユーザーの情報を取得
    try:
        # AdminUsersテーブルとOrganizationsテーブルを結合して組織名も取得
        cursor.execute("""
            SELECT 
                u.admin_id, u.username, u.role, u.organization_id,
                o.name as organization_name
            FROM AdminUsers u
            JOIN Organizations o ON u.organization_id = o.organization_id
            WHERE u.username = %s
        """, (username,))
        user_to_edit = cursor.fetchone()
    except psycopg2.Error as err:
        flash(f"ユーザー情報の取得中にエラーが発生しました: {err}", "error")
    finally:
        cursor.close()
        conn.close()

    if not user_to_edit:
        flash("指定されたユーザーが見つかりません。", "error")
        return redirect(url_for('staff_menu'))

    # テンプレートにユーザー情報を渡してレンダリング
    return render_template("staff/re/user_edit_staff.html", user=user_to_edit)

@app.route("/staff/recruitment/edit/<int:recruitment_id>")
def staff_opportunity_edit_page(recruitment_id):
    """
    案件編集ページ (opportunity_edit.html) を表示します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    # テンプレートをレンダリング。
    # 案件IDはURLから取得され、HTML/JavaScript側で利用されます。
    return render_template("staff/re/opportunity_edit.html", recruitment_id=recruitment_id)

@app.route("/staff/api/opportunities/<int:recruitment_id>", methods=['GET'])
def get_staff_opportunity_detail(recruitment_id):
    """
    特定の募集案件の詳細データと全カテゴリー情報をJSONで返します。
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401

    org_id = session.get('org_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # 1. 案件詳細を取得
        cursor.execute("""
            SELECT 
                r.recruitment_id AS id, 
                r.title, 
                r.description, 
                # スキーマ変更により削除されたカラムはここではSELECTしない
                # r.location,             
                # r.required_count,       
                # r.required_skills,      
                # ----------------------------------------------------
                r.start_date AS activity_date,  # 活動日
                r.end_date AS deadline,         # 募集締切日 (旧スキーマのdeadlineに相当)
                r.contact_phone_number AS phone_number, # 問い合わせ電話番号
                r.contact_email AS email,               # 問い合わせメールアドレス
                r.status,                       # ステータス
                (SELECT COUNT(*) FROM Applications a WHERE a.recruitment_id = r.recruitment_id) AS applied_count
            FROM Recruitments r
            WHERE r.recruitment_id = %s AND r.organization_id = %s
        """, (recruitment_id, org_id))
        
        opportunity = cursor.fetchone()

        if not opportunity:
            # 案件が見つからない場合は 404 を返します
            return jsonify({"error": "案件が見つからないか、アクセス権がありません。"}), 404

        # 日付オブジェクトをISO形式の文字列に変換
        opportunity['activity_date'] = opportunity['activity_date'].isoformat() if opportunity['activity_date'] else ''
        opportunity['deadline'] = opportunity['deadline'].isoformat() if opportunity['deadline'] else ''
        
        # 2. 案件に紐づくカテゴリーIDを取得
        cursor.execute("""
            SELECT category_id FROM RecruitmentCategoryMap WHERE recruitment_id = %s
        """, (recruitment_id,))
        
        selected_categories = [row['category_id'] for row in cursor.fetchall()]
        opportunity['categories'] = selected_categories 
        
        # 3. 全カテゴリー情報を取得
        cursor.execute("SELECT category_id, category_name FROM RecruitmentCategories ORDER BY category_id")
        all_categories = cursor.fetchall()

    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": f"データの取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

    # HTML側のJSで使われる time_frame を暫定的に空文字として追加 (スキーマ変更対応)
    opportunity['time_frame'] = '' 
    # HTML側のJSで使われる required_count, location, required_skills の代替値 (スキーマ変更対応)
    # SQLでSELECTしていないため、ここで明示的にキーを追加し、暫定値を設定する
    opportunity['required_count'] = 1
    opportunity['location'] = '未指定'
    opportunity['required_skills'] = '特になし'

    return jsonify({
        "opportunity": opportunity,
        "all_categories": all_categories
    })

@app.route('/staff/api/opportunities', methods=['POST'])
def staff_api_create_opportunity():
    """
    新しい募集案件をデータベースに登録するAPIエンドポイント。
    （opportunity_create.htmlのフォームから呼ばれます）
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401
    
    org_id = session.get('org_id')
    data = request.get_json()

    # 必須データのバリデーション (HTML: title, description, location, required_count, activity_date, deadline, email)
    required_fields = ['title', 'description', 'location', 'required_count', 'activity_date', 'deadline', 'email', 'status']
    if not all(field in data and data[field] for field in required_fields):
        # required_count は数値0も許容したい場合は調整が必要ですが、ここでは必須項目とします。
        return jsonify({"error": "必須項目が不足しているか、空です。"}, 400)
    
    # HTML: 'published', 'draft' -> DB: 'Open', 'Draft'
    db_status = data['status']
    if db_status == 'published':
        db_status = 'Open'
    elif db_status == 'draft':
        db_status = 'Draft'
    else:
        # 想定外のステータス値
        db_status = 'Draft'

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベース接続エラー"}, 500)

    cursor = conn.cursor()
    
    try:
        # 1. Recruitmentsテーブルに新しい案件を挿入
        insert_query = """
            INSERT INTO Recruitments (
                organization_id, title, description, 
                start_date, end_date, contact_phone_number, contact_email, 
                status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            org_id,
            data['title'],
            data['description'],
            data['activity_date'],
            data['deadline'],
            data.get('phone_number'),      # phone_number はオプション
            data['email'],                 # email は必須
            db_status
        ))
        
        # 挿入された案件のIDを取得
        new_recruitment_id = cursor.lastrowid
        
        # 2. カテゴリーの紐付け (RecruitmentCategoryMap)
        selected_categories = data.get('categories', [])
        if selected_categories:
            insert_map_query = "INSERT INTO RecruitmentCategoryMap (recruitment_id, category_id) VALUES (%s, %s)"
            # DBに渡すcategory_idは文字列ではなく数値である必要があるため、int()で型変換
            category_values = [(new_recruitment_id, int(cat_id)) for cat_id in selected_categories]
            cursor.executemany(insert_map_query, category_values)
        
        conn.commit()
        return jsonify({"message": f"新しい案件ID: {new_recruitment_id} が正常に作成されました。", "recruitment_id": new_recruitment_id}), 201

    except psycopg2.Error as err:
        conn.rollback() 
        print(f"案件作成クエリエラー: {err}")
        return jsonify({"error": f"案件の作成中にデータベースエラーが発生しました: {err}"}), 500
    except Exception as e:
        conn.rollback() 
        print(f"予期せぬエラー: {e}")
        return jsonify({"error": f"予期せぬエラーが発生しました: {e}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# ------------------------------------------------------------------
# 案件情報更新 API (POST)
# ------------------------------------------------------------------
@app.route('/staff/api/opportunities/<int:recruitment_id>', methods=['POST'])
def staff_api_update_opportunity(recruitment_id):
    """
    既存の募集案件を更新するAPIエンドポイント。
    （HTMLのform.addEventListenerから呼ばれます）
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}, 401)
    
    org_id = session.get('org_id')
    data = request.get_json()

    # 必須データのバリデーション
    # contact_email (HTML: email) のチェックを含める
    required_fields = ['title', 'description', 'activity_date', 'deadline', 'email', 'status']
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"error": "必須項目が不足しているか、空です。"}, 400)

    # HTML側のJSで使われる status の値に変換
    # HTML: 'published', 'draft', 'closed' -> DB: 'Open', 'Draft', 'Closed'
    db_status = data['status']
    if db_status == 'published':
        db_status = 'Open'
    elif db_status == 'draft':
        db_status = 'Draft'
    elif db_status == 'closed':
        db_status = 'Closed'

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベース接続エラー"}, 500)

    cursor = conn.cursor()
    
    try:
        # 1. Recruitmentsテーブルの案件を更新 (organization_idとrecruitment_idで所有権をチェック)
        # ★ updated_at = NOW() を削除 (DBにカラムが存在しないため)
        update_query = """
            UPDATE Recruitments SET
                title = %s,
                description = %s,
                start_date = %s,        -- 活動日 (HTML: activity_date)
                end_date = %s,          -- 募集締切日 (HTML: deadline)
                contact_email = %s,     -- 問い合わせメールアドレス (DBスキーマの追加)
                contact_phone_number = %s,
                status = %s
            WHERE recruitment_id = %s AND organization_id = %s
        """
        cursor.execute(update_query, (
            data['title'],
            data['description'],
            data['activity_date'],
            data['deadline'],
            data['email'],
            data.get('phone_number'), # phone_number はオプション
            db_status,
            recruitment_id,
            org_id
        ))
        
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "案件が見つからないか、更新する権限がありません。"}, 403)

        # 2. カテゴリーの更新 (RecruitmentCategoryMapを一度クリアし、再挿入する)
        
        # 既存のカテゴリーを削除
        cursor.execute("DELETE FROM RecruitmentCategoryMap WHERE recruitment_id = %s", (recruitment_id,))
        
        # 新しいカテゴリーを挿入
        selected_categories = data.get('categories', [])
        if selected_categories:
            insert_map_query = "INSERT INTO RecruitmentCategoryMap (recruitment_id, category_id) VALUES (%s, %s)"
            # DBに渡すcategory_idは文字列ではなく数値である必要があるため、int()で型変換
            category_values = [(recruitment_id, int(cat_id)) for cat_id in selected_categories]
            cursor.executemany(insert_map_query, category_values)
        
        conn.commit()
        return jsonify({"message": f"案件ID: {recruitment_id} が正常に更新されました。"}, 200)

    except psycopg2.Error as err:
        conn.rollback() 
        print(f"案件更新クエリエラー: {err}")
        return jsonify({"error": f"案件の更新中にデータベースエラーが発生しました: {err}"}), 500
    except Exception as e:
        conn.rollback() 
        print(f"予期せぬエラー: {e}")
        return jsonify({"error": f"予期せぬエラーが発生しました: {e}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route("/staff/re/management")
def staff_management_menu():
    """ユーザー管理メニュー（manage.html）をレンダリングします。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    # 修正: テンプレートのパスを 'staff/re/manage.html' に変更します。
    return render_template("staff/re/manage.html") # <--- ここを修正

@app.route("/staff/re/user_list")
def staff_user_list():
    """職員向けのユーザー一覧・編集（user_list_staff.html）をレンダリングします。"""
    # 職員のログイン状態をチェック
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    # user_list_staff.html テンプレートをレンダリング
    # ※ファイルが 'staff/re/' ディレクトリ内にあることを想定しています。
    return render_template("staff/re/user_list_staff.html")

@app.route("/api/staff/users", methods=["GET"])
def api_get_staff_users():
    """職員向けのユーザー一覧をAdminUsersとVolunteersから結合して取得し、JSONで返却するAPI。"""
    # 職員のログイン状態をチェック (認証ガード)
    if not check_org_login():
        return jsonify({"error": "認証されていません。"}, 401)

    org_id = session.get('org_id') # この行を追加

    conn = get_db_connection()
    if conn is None:
        # データベース接続エラーを返す
        return jsonify({"error": "データベースに接続できません。"}, 500)

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # AdminUsers (職員) と Volunteers (ボランティア) の情報を結合するクエリを修正
        query = """
        -- 職員アカウント (AdminUsers) の情報
        (SELECT
            admin_id AS id,
            admin_id AS display_id, -- フロントエンド互換のためのID
            username,
            role AS name, -- 職員は氏名がないため、roleを仮の表示名として使用
            NULL AS email, -- AdminUsersにはemailがないためNULL
            organization_id AS org_id,
            NULL AS created_at, -- 作成日時がないためNULL
            'active' AS status,
            CASE role WHEN 'OrgAdmin' THEN '管理者職員' ELSE '一般職員' END AS status_text,
            TRUE AS is_org_staff -- 職員である
        FROM AdminUsers
        WHERE organization_id = %s)

        UNION ALL

        -- ボランティアアカウント (Volunteers) の情報
        (SELECT
            volunteer_id AS id,
            volunteer_id AS display_id, -- フロントエンド互換のためのID
            username,
            full_name AS name,
            email,
            organization_id AS org_id,
            registration_date AS created_at,
            'active' AS status, -- Volunteersテーブルには活動状況カラムがないため、一旦 'active' を仮定
            'ボランティア' AS status_text, 
            FALSE AS is_org_staff -- 職員ではない
        FROM Volunteers
        WHERE organization_id = %s)

        ORDER BY created_at DESC, id DESC;
        """
        cursor.execute(query, (org_id, org_id))
        users = cursor.fetchall()
        
        return jsonify(users)

    except psycopg2.Error as err:
        # エラーメッセージを分かりやすく出力し、フロントエンドに返す
        print(f"ユーザー一覧取得クエリエラー: {err}") 
        return jsonify({"error": f"データベースクエリ実行中にエラーが発生しました: {err}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route("/staff/re/user_edit", methods=["GET"])
# 関数名を変更しました
def staff_user_edit_page(): 
    """職員向けのユーザー編集画面（user_edit_staff.html）をレンダリングします。"""
    # 職員のログイン状態をチェック
    if not check_org_login():
        # staff_login関数が定義されていることを前提とします
        return redirect(url_for('staff_login'))
    
    # user_edit_staff.html テンプレートをレンダリング
    # ※ファイルが 'staff/re/' ディレクトリ内にあることを想定しています。
    return render_template("staff/re/user_edit_staff.html")

@app.route("/api/user/<int:user_id>", methods=["GET"])
def api_get_single_user(user_id):
    """
    指定されたIDのユーザー情報をAdminUsersまたはVolunteersテーブルから取得するAPI。
    """
    # 職員のログイン状態をチェック (認証ガード)
    if not check_org_login():
        return jsonify({"error": "認証されていません。"}, 401)

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できません。"}, 500)

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        user_data = None
        
        # 1. 職員アカウント (AdminUsers) から検索
        cursor.execute("""
            SELECT 
                admin_id AS id, 
                username, 
                role, 
                organization_id AS org_id
            FROM AdminUsers 
            WHERE admin_id = %s
        """, (user_id,))
        admin_user = cursor.fetchone()

        if admin_user:
            # 職員のデータを整形
            user_data = {
                "id": admin_user['id'],
                "username": admin_user['username'],
                "is_org_staff": True,
                "role": admin_user['role'],
                "name": admin_user['role'], # フロントエンド表示用
                "email": None,
                "org_id": admin_user['org_id'],
                "is_active": True,
                # 編集フォームのためにボランティアのフィールドをNULLで埋める
                "full_name": f"{admin_user['role']} ({admin_user['username']})",
                "birth_year": None,
                "gender": None,
                "phone_number": None,
                "postal_code": None,
                "address": None,
            }

        # 2. ボランティアアカウント (Volunteers) から検索 (職員で見つからなかった場合のみ)
        if not user_data:
            cursor.execute("""
                SELECT 
                    volunteer_id AS id, 
                    username, 
                    full_name, 
                    email, 
                    organization_id AS org_id,
                    birth_year,
                    gender,
                    phone_number,
                    postal_code,
                    address
                FROM Volunteers 
                WHERE volunteer_id = %s
            """, (user_id,))
            volunteer_user = cursor.fetchone()

            if volunteer_user:
                # ボランティアのデータを整形
                user_data = {
                    "id": volunteer_user['id'],
                    "username": volunteer_user['username'],
                    "is_org_staff": False,
                    "name": volunteer_user['full_name'],
                    "email": volunteer_user['email'],
                    "org_id": volunteer_user['org_id'],
                    "is_active": True,
                    # 編集フォームに必要なフィールド
                    "full_name": volunteer_user['full_name'],
                    "birth_year": volunteer_user['birth_year'],
                    "gender": volunteer_user['gender'],
                    "phone_number": volunteer_user['phone_number'],
                    "postal_code": volunteer_user['postal_code'],
                    "address": volunteer_user['address'],
                }
        
        # 3. 結果の返却
        if user_data:
            return jsonify(user_data), 200
        else:
            return jsonify({"error": f"ユーザーID {user_id} は見つかりませんでした。"}, 404)

    except psycopg2.Error as err:
        print(f"単一ユーザー取得クエリエラー: {err}")
        return jsonify({"error": f"データベースクエリ実行中にエラーが発生しました: {err}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route("/api/user/<int:user_id>", methods=["PUT"])
def api_update_user(user_id):
    """
    指定されたIDのユーザー情報をAdminUsersまたはVolunteersテーブルで更新するAPI。
    """
    # 職員のログイン状態をチェック (認証ガード)
    if not check_org_login():
        return jsonify({"error": "認証されていません。"}, 401)

    data = request.get_json()
    if not data:
        return jsonify({"error": "リクエストボディが空です。"}, 400)
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できません。"}, 500)

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        update_success = False
        is_org_staff = data.get('is_org_staff', False)

        if is_org_staff:
            # 職員アカウントの更新 (AdminUsers)
            # 編集対象: role
            role = data.get('staffRole') # 'OrgAdmin' or 'Staff'
            
            update_query = """
                UPDATE AdminUsers
                SET role = %s
                WHERE admin_id = %s
            """
            cursor.execute(update_query, (role, user_id))
            if cursor.rowcount > 0:
                update_success = True

        else:
            # ボランティアアカウントの更新 (Volunteers)
            # 編集対象: full_name, email, phone_number, birth_year, gender, postal_code, address
            full_name = data.get('fullName')
            email = data.get('email')
            phone_number = data.get('phoneNumber')
            # birthYearが空の場合、None (NULL) を設定
            birth_year = data.get('birthYear') if data.get('birthYear') else None 
            gender = data.get('gender')
            postal_code = data.get('postalCode')
            address = data.get('address')
            
            update_query = """
                UPDATE Volunteers
                SET full_name = %s,
                    email = %s,
                    phone_number = %s,
                    birth_year = %s,
                    gender = %s,
                    postal_code = %s,
                    address = %s
                WHERE volunteer_id = %s
            """
            cursor.execute(update_query, (
                full_name, email, phone_number, birth_year, gender, 
                postal_code, address, user_id
            ))
            if cursor.rowcount > 0:
                update_success = True
        
        # 3. 結果の返却
        if update_success:
            conn.commit()
            return jsonify({"success": True, "message": "ユーザー情報が正常に更新されました。"}, 200)
        else:
            # rowcountが0の場合、データが変更されていないかIDが見つからない
            conn.rollback()
            return jsonify({"success": False, "error": "更新対象のユーザーが見つからないか、データが変更されていません。"}, 404)

    except psycopg2.Error as err:
        conn.rollback()
        print(f"ユーザー更新クエリエラー: {err}")
        return jsonify({"success": False, "error": f"データベースエラーが発生しました: {err}"}), 500
    except Exception as e:
        conn.rollback()
        print(f"予期せぬエラー: {e}")
        return jsonify({"success": False, "error": f"予期せぬエラーが発生しました: {e}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route("/api/user/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    """
    指定されたIDのボランティアユーザーアカウントを削除するAPIエンドポイント。
    ユーザー編集画面 (user_edit_staff.html) のDELETEリクエストに対応。
    """
    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "error": "データベース接続に失敗しました。"}, 500)

    try:
        cursor = conn.cursor()
        
        # 1. Volunteersテーブルからユーザーを削除する
        # （AdminUsersの削除はここでは行わない前提とする）
        delete_query = """
        DELETE FROM Volunteers
        WHERE volunteer_id = %s
        """
        
        cursor.execute(delete_query, (user_id,))
        
        if cursor.rowcount > 0:
            # 削除成功
            conn.commit()
            return jsonify({"success": True, "message": f"ユーザーID {user_id} のアカウントを正常に削除しました。"})
        else:
            # ユーザーが見つからない
            conn.rollback()
            return jsonify({"success": False, "message": "削除対象のボランティアユーザーが見つかりませんでした。"}, 404)

    except psycopg2.Error as err:
        conn.rollback()
        print(f"ユーザー削除クエリエラー: {err}")
        return jsonify({"success": False, "error": f"データベースエラーが発生しました: {err}"}), 500
    except Exception as e:
        conn.rollback()
        print(f"予期せぬエラー: {e}")
        return jsonify({"success": False, "error": f"予期せぬエラーが発生しました: {e}"}), 500
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor:
                cursor.close()
            conn.close()

@app.route("/staff/re/user_invite", methods=["GET"])
def staff_user_invite():
    """職員向けの新規ユーザー招待入力画面を表示します。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    # user_invite.html をレンダリング
    return render_template("staff/user/user_invite.html")

@app.route("/staff/re/user_invite_confirm", methods=["GET"])
def staff_user_invite_confirm():
    """職員向けの新規ユーザー招待確認画面を表示します。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    # user_invite_confirm.html をレンダリング
    return render_template("staff/user/user_invite_confirm.html")

@app.route("/staff/re/user_invite_complete", methods=["GET"])
def staff_user_invite_complete():
    """職員向けの新規ユーザー招待完了画面を表示します。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    # user_invite_complete.html をレンダリング
    return render_template("staff/user/user_invite_complete.html")

@app.route("/api/register_volunteer", methods=["POST"])
def register_volunteer():
    """新規ボランティアユーザーをデータベースに登録するAPIエンドポイント"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベース接続に失敗しました。"}, 500)

    try:
        data = request.get_json()
        
        # 1. 必須フィールドの取得とチェック
        username = data.get('username')
        password = data.get('password')
        full_name = data.get('full_name')
        email = data.get('email')
        phone_number = data.get('phone_number') # 電話番号はオプションとして処理
        
        if not all([username, password, full_name, email]):
            return jsonify({"error": "必須フィールドが不足しています。"}, 400)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 2. ユーザー名の重複チェック
        # ユーザー名（ログインID）は一意である必要がある
        cursor.execute("SELECT username FROM Volunteers WHERE username = %s", (username,))
        if cursor.fetchone():
            return jsonify({"error": "このユーザー名（ログインID）は既に使われています。"}, 409)

        # 3. パスワードのハッシュ化 (bcryptを使用)
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # 4. ユーザー情報をデータベースに挿入
        # organization_idは、現在の実装で取得できないため、一時的に定数 'ORG-0001' を使用
         
        organization_id = 1 # ← この行を修正 
        
        insert_query = """
        INSERT INTO Volunteers 
            (username, password_hash, full_name, email, phone_number, organization_id, registration_date) 
        VALUES 
            (%s, %s, %s, %s, %s, %s, NOW())
        """
        
        cursor.execute(insert_query, (
            username, 
            hashed_password, 
            full_name, 
            email, 
            phone_number,
            organization_id 
        ))
        
        conn.commit()
        
        # 成功レスポンス。完了画面に表示するため氏名を返却。
        return jsonify({"success": True, "username": full_name}), 200

    except psycopg2.Error as err:
        conn.rollback() 
        print(f"ボランティア登録クエリエラー: {err}")
        return jsonify({"error": f"データベースエラーが発生しました: {err}"}), 500
    except Exception as e:
        conn.rollback()
        print(f"予期せぬエラー: {e}")
        return jsonify({"error": f"予期せぬエラーが発生しました: {e}"}), 500
    finally:
        if conn and conn.is_connected():
            if 'cursor' in locals() and cursor:
                cursor.close()
            conn.close()

@app.route('/staff/account/create', methods=['GET', 'POST'])

def create_staff_account():

    """(OrgAdmin専用) 新しい職員(Staff)アカウントを作成する"""

    if not check_org_login() or session.get('org_role') != 'OrgAdmin':

        flash("この操作を行う権限がありません。", "error")

        return redirect(url_for('staff_menu'))



    if request.method == 'POST':

        username = request.form.get('username')

        password = request.form.get('password')

        password_confirm = request.form.get('password_confirm')

        org_id = session.get('org_id')



        if not all([username, password, password_confirm]):

            flash("すべてのフィールドを入力してください。", "error")

            return redirect(url_for('create_staff_account'))

        

        if password != password_confirm:

            flash("パスワードが一致しません。", "error")

            return redirect(url_for('create_staff_account'))



        conn = get_db_connection()

        if conn is None:

            flash("データベースに接続できませんでした。", "error")

            return redirect(url_for('create_staff_account'))



        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        try:

            # ユーザー名の重複チェック

            cursor.execute("SELECT admin_id FROM AdminUsers WHERE username = %s", (username,))

            if cursor.fetchone():

                flash(f"ユーザー名「{username}」は既に使用されています。", "error")

                return redirect(url_for('create_staff_account'))



            # パスワードをハッシュ化して新しいアカウントを登録

            pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')

            cursor.execute("""

                INSERT INTO AdminUsers (organization_id, username, password_hash, role) 

                VALUES (%s, %s, %s, 'Staff')

            """, (org_id, username, pw_hash))

            conn.commit()

            flash(f"職員アカウント「{username}」を正常に作成しました。", "success")

        

        except psycopg2.Error as err:

            conn.rollback()

            flash(f"データベースエラーが発生しました: {err}", "error")

        finally:

            cursor.close()

            conn.close()

        

        return redirect(url_for('create_staff_account'))



    # GETリクエストの場合

    return render_template("staff/re/staff_create.html")



@app.route('/staff/account/list')

def list_staff_accounts():

    """(OrgAdmin専用) 職員アカウントの一覧を表示する"""

    if not check_org_login() or session.get('org_role') != 'OrgAdmin':

        flash("この操作を行う権限がありません。", "error")

        return redirect(url_for('staff_menu'))



    org_id = session.get('org_id')

    accounts = []

    conn = get_db_connection()

    if conn is None:

        flash("データベースに接続できませんでした。", "error")

        return render_template("staff/re/staff_list.html", accounts=accounts)



    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    try:

        cursor.execute("""

            SELECT u.username, u.role, o.name as organization_name

            FROM AdminUsers u

            JOIN Organizations o ON u.organization_id = o.organization_id

            WHERE u.organization_id = %s

            ORDER BY u.role, u.username

        """, (org_id,))

        accounts = cursor.fetchall()

    except psycopg2.Error as err:

        flash(f"アカウント一覧の取得中にエラーが発生しました: {err}", "error")

    finally:

        cursor.close()

        conn.close()



    return render_template("staff/re/staff_list.html", accounts=accounts)



@app.route("/staff/applications")
def staff_applications():
    """職員が管轄組織の募集案件への応募者一覧を確認する"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    org_id = session.get('org_id')
    
    if not org_id:
        flash("セッションから組織IDを取得できませんでした。再度ログインしてください。", "error")
        return redirect(url_for('staff_login'))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        # テンプレートに空のリストを渡す
        return render_template("staff/re/applicant_list.html", applications=[], org_name="所属組織不明") 

    applications = []
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # SQLクエリをRecruitments, Volunteersテーブルに合わせて修正
        sql_query = """
            SELECT 
                v.full_name AS applicant_name,          -- Volunteersテーブルの氏名
                v.username AS applicant_username,        -- Volunteersテーブルのユーザー名
                r.title AS opportunity_title,            -- Recruitmentsテーブルの募集タイトル
                a.status AS application_status,
                a.application_date,
                a.application_id,
                r.recruitment_id AS opportunity_id       -- recruitment_idをテンプレートに合わせるため opportunity_id としてエイリアス
            FROM 
                Applications a
            JOIN 
                Recruitments r ON a.recruitment_id = r.recruitment_id  -- RecruitmentsにJOIN
            JOIN 
                Volunteers v ON a.volunteer_id = v.volunteer_id        -- VolunteersにJOIN
            WHERE 
                r.organization_id = %s
            ORDER BY 
                a.application_date DESC
        """
        cursor.execute(sql_query, (org_id,))
        applications = cursor.fetchall()
        
    except psycopg2.Error as err:
        flash(f"応募者情報の取得中にデータベースエラーが発生しました: {err}", "error")
        print(f"SQL Error in staff_applications: {err}")
        # エラーが発生した場合もテンプレートはレンダリングし、エラーメッセージをユーザーに表示する
        context = {
            'applications': [],
            'org_name': session.get('org_name', '所属組織'), 
            'error_message': f"データベースエラーが発生しました: {err.msg}"
        }
        return render_template("staff/re/applicant_list.html", **context)

    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        
    context = {
        'applications': applications,
        'org_name': session.get('org_name', '所属組織'), 
    }
    
    return render_template("staff/re/applicant_list.html", **context)

@app.route("/staff/applications/<int:application_id>/detail")
def staff_application_detail(application_id):
    """個別の応募詳細情報を表示し、ステータス変更を可能にする"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    org_id = session.get('org_id')
    
    if not org_id:
        flash("セッションから組織IDを取得できませんでした。再度ログインしてください。", "error")
        return redirect(url_for('staff_login'))
    
    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("staff/re/application_detail.html", detail={}, org_name=session.get('org_name', '所属組織'), not_found=True)

    detail = None
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # SQLクエリ: 応募、募集、ボランティアの全詳細情報を取得
        # さらに、この応募がログイン中の職員の管轄組織のものであるかも確認する (r.organization_id = %s)
        sql_query = """
            SELECT 
                a.application_id, a.status AS application_status, a.application_date,
                r.recruitment_id, r.title AS recruitment_title, r.description AS recruitment_description,
                r.start_date, r.end_date, r.contact_phone_number, r.contact_email,
                v.volunteer_id, v.full_name AS applicant_name, v.username AS applicant_username,
                v.phone_number AS applicant_phone, v.email AS applicant_email, v.address, v.postal_code,
                v.birth_year, v.gender
            FROM 
                Applications a
            JOIN 
                Recruitments r ON a.recruitment_id = r.recruitment_id
            JOIN 
                Volunteers v ON a.volunteer_id = v.volunteer_id
            WHERE 
                a.application_id = %s AND r.organization_id = %s
        """
        cursor.execute(sql_query, (application_id, org_id))
        detail = cursor.fetchone()
        
        if not detail:
            flash("指定された応募情報が見つからないか、管轄外の情報です。", "error")
            return render_template("staff/re/application_detail.html", detail={}, org_name=session.get('org_name', '所属組織'), not_found=True)

    except psycopg2.Error as err:
        flash(f"応募詳細の取得中にデータベースエラーが発生しました: {err}", "error")
        print(f"SQL Error in staff_application_detail: {err}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        
    context = {
        'detail': detail,
        'org_name': session.get('org_name', '所属組織'),
    }
    
    # 新しいテンプレートファイル staff/re/application_detail.html をレンダリング
    return render_template("staff/re/application_detail.html", **context)

@app.route("/staff/applications/<int:application_id>/update_status", methods=['POST'])
def update_application_status(application_id):
    """
    応募ステータスを更新する（Pending -> Approved/Rejected）。
    セキュリティチェックとして、職員の管轄組織の応募であるかを確認する。
    """
    # 1. ログインチェック
    if not check_org_login():
        flash("セッションが切れました。再度ログインしてください。", "error")
        return redirect(url_for('staff_login'))

    org_id = session.get('org_id')
    
    # 2. POSTデータから新しいステータスを取得
    new_status = request.form.get('new_status')
    if new_status not in ['Approved', 'Rejected']:
        flash("無効なステータスが指定されました。", "error")
        return redirect(url_for('staff_application_detail', application_id=application_id))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return redirect(url_for('staff_application_detail', application_id=application_id))

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # 3. 応募情報と管轄組織のチェック（二重チェック）
        # ステータスを更新する前に、その応募がログイン中の職員の管轄組織の案件であることを確認します。
        
        # 応募がどの募集案件に紐づいているか、その募集案件がどの組織に紐づいているかをJOINでチェック
        check_query = """
            SELECT a.application_id
            FROM Applications a
            JOIN Recruitments r ON a.recruitment_id = r.recruitment_id
            WHERE a.application_id = %s AND r.organization_id = %s
        """
        cursor.execute(check_query, (application_id, org_id))
        is_authorized = cursor.fetchone()
        
        if not is_authorized:
            flash("この応募情報はあなたの組織の管轄外であるか、存在しません。", "error")
            return redirect(url_for('staff_applications'))

        # 4. ステータスの更新を実行
        update_query = """
            UPDATE Applications
            SET status = %s
            WHERE application_id = %s
        """
        cursor.execute(update_query, (new_status, application_id))
        conn.commit()
        
        # 5. 成功メッセージ
        status_name = "承認" if new_status == 'Approved' else "不承認"
        flash(f"応募ID: {application_id} のステータスを「{status_name}」に更新しました。", "success")
        
    except psycopg2.Error as err:
        conn.rollback()
        flash(f"ステータスの更新中にデータベースエラーが発生しました: {err}", "error")
        print(f"SQL Error in update_application_status: {err}")
        
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        
    # 6. 詳細ページにリダイレクト
    return redirect(url_for('staff_application_detail', application_id=application_id))

@app.route("/staff/applications/<int:recruitment_id>")
# ※ ログインチェックのデコレータ(@login_required)を適宜追加してください
def staff_applicant_list_by_recruitment(recruitment_id):
    # テンプレートパスをフォルダ構造に合わせて修正
    return render_template("staff/re/applicant_list_staff.html", recruitment_id=recruitment_id)

@app.route("/staff/api/applications/by_recruitment/<int:recruitment_id>")
def get_applications_by_recruitment(recruitment_id):
    org_id = session.get('org_id') 
    
    if not org_id:
        return jsonify({"error": "このエンドポイントへのアクセスには職員としてのログインが必要です。"}), 401 

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベース接続エラーが発生しました。設定(.env)を確認してください。"}), 500

    # 💡 修正 1: UnboundLocalErrorを回避するため、ここでapplicationsを初期化する
    applications = None
    cursor = None
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) 
        
        # 💡 修正: VolunteersテーブルをJOINし、氏名とメールアドレスを取得する
        query = """
            SELECT 
                a.application_id, 
                v.full_name AS applicant_name,  -- Volunteersテーブルから氏名を取得
                v.email AS applicant_email,      -- Volunteersテーブルからメールアドレスを取得
                a.status AS application_status,
                r.title AS recruitment_title,
                r.recruitment_id
            FROM Applications a
            JOIN Recruitments r ON a.recruitment_id = r.recruitment_id
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id  -- Volunteersテーブルと結合
            WHERE r.organization_id = %s AND a.recruitment_id = %s
            ORDER BY a.application_id DESC
        """
        cursor.execute(query, (org_id, recruitment_id))
        applications = cursor.fetchall()

        return jsonify(applications)

    # データベースエラーを捕捉
    except psycopg2.Error as err:
        print(f"SQL Error in get_applications_by_recruitment: {err}") 
        return jsonify({"error": "データベース操作中にエラーが発生しました。"}), 500
    
    # その他の予期せぬPythonエラーを捕捉
    except Exception as e:
        print(f"Unexpected Python Error in get_applications_by_recruitment: {e}") 
        return jsonify({"error": "サーバー内部で予期せぬエラーが発生しました。"}), 500
        
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

        return jsonify(applications)

if __name__ == '__main__':
    # サーバーをネットワーク上でアクセス可能にするために host='0.0.0.0' を指定
    app.run(host='0.0.0.0', port=5000, debug=True)
