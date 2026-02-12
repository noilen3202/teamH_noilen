# このファイルを実行する前に、以下のライブラリをインストールしてください:
# pip install Flask mysql-connector-python python-dotenv google-cloud-language pandas Flask-Bcrypt Flask-Mail fpdf

import os
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, flash, send_from_directory, send_file
from flask_bcrypt import Bcrypt
from functools import wraps
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import pandas as pd
# from google.cloud import language_v1
import smtplib
import ssl
from email.message import EmailMessage
from flask_mail import Mail, Message
import secrets
from datetime import datetime
from fpdf import FPDF
import io
import csv
import threading

# .envファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__, static_folder='.', template_folder='.')


app.config['SERVER_NAME'] = 'teamh-noilen.onrender.com'
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24)) # セッション管理のための秘密鍵。環境変数から取得、なければランダム生成
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
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("環境変数 DATABASE_URL が設定されていません。")
            return None
        conn = psycopg2.connect(database_url)
        return conn
    except psycopg2.Error as err:
        print(f"データベース接続エラー: {err}")
        return None

def login_required(f):
    """市区町村職員のログイン状態をチェックするデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'org_user' not in session:
            flash("この操作にはログインが必要です。", "error")
            return redirect(url_for('staff_login'))
        return f(*args, **kwargs)
    return decorated_function

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
        cursor.execute("SELECT recruitment_id, title, description, start_date, end_date, contact_phone_number FROM Recruitments WHERE recruitment_id = %s", (recruitment_id,))
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
    next_url = request.args.get('next', '')
    return render_template('user/userlogin.html', next_url=next_url)

@app.route('/user/login_process', methods=['POST'])
def user_login_process():
    """ユーザーのログイン処理"""
    email = request.form.get('email')
    password = request.form.get('password')
    next_url = request.form.get('next')
    
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

                # 安全なリダイレクト先の決定
                if next_url and next_url.startswith('/'):
                    redirect_url = next_url
                else:
                    redirect_url = url_for('user_recruitment_list')
            
                return jsonify({'success': True, 'message': 'ログインに成功しました。', 'redirect_url': redirect_url})

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
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('full_name')
    mynumber = data.get('mynumber')
    email = data.get('email')
    phone_number = data.get('phone_number')

    if not all([username, password, full_name, mynumber, email]):
        return jsonify({'success': False, 'message': '必須フィールドが不足しています。'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # ユーザー名またはメールアドレスの重複を確認
        cursor.execute("SELECT volunteer_id FROM Volunteers WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'そのユーザー名またはメールアドレスは既に使用されています。'}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # 招待した職員の組織IDを割り当てる
        org_id_to_assign = session.get('org_id', 1) # デフォルトは1(公開)

        cursor.execute(
            """
            INSERT INTO Volunteers (organization_id, username, password_hash, full_name, mynumber, email, phone_number) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (org_id_to_assign, username, hashed_password, full_name, mynumber, email, phone_number)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': f'アカウント「{full_name}」さんを作成しました。'})

    except psycopg2.Error as e:
        print(f"Database error during account creation: {e}")
        return jsonify({'success': False, 'message': 'データベースエラーによりアカウントを作成できませんでした。'}), 500
    except Exception as e:
        print(f"Unexpected error during account creation: {e}")
        return jsonify({'success': False, 'message': 'アカウント作成中に予期せぬエラーが発生しました。'}), 500


@app.route('/user/mypage')
def user_mypage():
    """ユーザーのマイページ"""
    if not session.get('logged_in'):
        return redirect(url_for('user_login_page'))

    # 関連機能が削除されたため、お気に入り・都道府県・市区町村のデータ取得処理を削除しました。
    # 「興味のあるカテゴリ」セクションは、JavaScriptを介して自身のデータをAPIから取得します。

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
        next_url = request.form.get('next') # Capture next_url from form

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
            # Redirect to next_url if available and safe, otherwise to dashboard
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('admin_dashboard'))
        else:
            flash("ユーザー名またはパスワードが正しくありません。", "error")
            return redirect(url_for('admin_login', next=next_url)) # Pass next_url on failed login

    # For GET request, capture next_url from query parameters
    next_url = request.args.get('next')
    return render_template("admin/login.html", next_url=next_url)

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
    
    conn = get_db_connection()
    locations = []
    if conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("""
                SELECT
                    p.name AS prefecture_name,
                    o.name AS organization_name
                FROM
                    Prefectures p
                JOIN
                    Organizations o ON p.prefecture_id = o.prefecture_id
                ORDER BY
                    p.name, o.name;
            """)
            locations = cursor.fetchall()
        except psycopg2.Error as err:
            flash(f"地域情報の取得中にエラーが発生しました: {err}", "error")
        finally:
            cursor.close()
            conn.close()

    username = session.get('admin_user')
    return render_template("admin/platform-admin.html", username=username)

@app.route("/admin/registered_regions")
def admin_registered_regions():
    """登録済み地域一覧ページ"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    
    prefecture_filter = request.args.get('prefecture_name', '').strip()
    
    conn = get_db_connection()
    locations = []
    if conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            query = """
                SELECT
                    p.name AS prefecture_name,
                    o.name AS organization_name,
                    o.organization_id -- organization_idも取得
                FROM
                    Prefectures p
                JOIN
                    Organizations o ON p.prefecture_id = o.prefecture_id
                WHERE
                    o.is_active = TRUE -- 論理削除されていないもののみ表示
            """
            params = []
            if prefecture_filter:
                query += " AND p.name ILIKE %s" # AND に変更
                params.append(f"%{prefecture_filter}%")
            
            query += " ORDER BY p.name, o.name;"
            
            cursor.execute(query, tuple(params))
            locations = cursor.fetchall()
        except psycopg2.Error as err:
            flash(f"地域情報の取得中にエラーが発生しました: {err}", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template("admin/registered_regions.html", locations=locations)


@app.route("/admin/analysis")
def admin_analysis():
    """AI分析レポートページ"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    return render_template("admin/analysis.html")

# ------------------------------
# API エンドポイント
# ------------------------------

@app.route("/admin/org_register", methods=['GET', 'POST'])
def admin_org_register():
    """市区町村登録ページと登録処理"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        prefecture_name = request.form['prefecture']
        org_name = request.form['org_name']
        app_date = request.form['app_date']

        if not org_name or not app_date or not prefecture_name:
            flash("すべてのフィールドを入力してください。", "error")
            return redirect(url_for('admin_org_register'))

        conn = get_db_connection()
        if conn is None:
            flash("データベースに接続できませんでした。", "error")
            return redirect(url_for('admin_org_register'))

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT prefecture_id FROM Prefectures WHERE name = %s", (prefecture_name,))
            prefecture = cursor.fetchone()
            if not prefecture:
                flash("選択された都道府県が見つかりません。", "error")
                return redirect(url_for('admin_org_register'))
            
            prefecture_id = prefecture['prefecture_id']
            
            cursor.execute("INSERT INTO Organizations (prefecture_id, name, application_date, is_active) VALUES (%s, %s, %s, TRUE)", (prefecture_id, org_name, app_date))
            conn.commit()
            flash(f"「{prefecture_name} {org_name}」を登録しました。", "success")
        except psycopg2.Error as err:
            conn.rollback()
            if hasattr(err, 'pgcode') and err.pgcode == '23505': # unique_violation
                flash(f"市区町村区「{org_name}」は既に登録されています。", "error")
            else:
                flash(f"登録中にエラーが発生しました: {err}", "error")
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('admin_org_register'))

    # GET request
    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("admin/org_register.html", prefectures=[])
    
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT name FROM Prefectures ORDER BY prefecture_id")
        prefectures = [row['name'] for row in cursor.fetchall()]
    except psycopg2.Error as err:
        flash(f"都道府県リストの取得中にエラーが発生しました: {err}", "error")
        prefectures = []
    finally:
        cursor.close()
        conn.close()

    return render_template("admin/org_register.html", prefectures=prefectures)

@app.route("/admin/add_prefecture", methods=['POST'])
def admin_add_prefecture():
    """新しい都道府県を追加するAPIエンドポイント"""
    if 'admin_user' not in session:
        return jsonify({'success': False, 'message': '認証が必要です。'}), 401

    prefecture_name = request.form.get('prefecture_name')

    if not prefecture_name:
        return jsonify({'success': False, 'message': '都道府県名を入力してください。'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'データベースに接続できませんでした。'}), 500

    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO Prefectures (name) VALUES (%s) RETURNING prefecture_id, name", (prefecture_name,))
        new_prefecture = cursor.fetchone()
        conn.commit()
        return jsonify({'success': True, 'message': f"都道府県「{prefecture_name}」を追加しました。", 'prefecture': {'id': new_prefecture[0], 'name': new_prefecture[1]}}), 200
    except psycopg2.Error as err:
        conn.rollback()
        if hasattr(err, 'pgcode') and err.pgcode == '23505': # unique_violation
            return jsonify({'success': False, 'message': f"都道府県「{prefecture_name}」は既に存在します。"}), 409
        else:
            return jsonify({'success': False, 'message': f"登録中にエラーが発生しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/admin/organization/delete/<int:organization_id>", methods=['POST'])
def admin_organization_delete(organization_id):
    """
    指定された市区町村を論理削除（is_activeをFALSEに設定）します。
    """
    if 'admin_user' not in session:
        return jsonify({'success': False, 'message': '認証が必要です。'}), 401

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'データベースに接続できませんでした。'}), 500

    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Organizations SET is_active = FALSE WHERE organization_id = %s", (organization_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': '指定された市区町村が見つかりませんでした。'}), 404
        return jsonify({'success': True, 'message': '市区町村を削除しました。'}), 200
    except psycopg2.Error as err:
        conn.rollback()
        return jsonify({'success': False, 'message': f"削除中にエラーが発生しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/admin/org_admin_management", methods=['GET', 'POST'])
def admin_org_admin_management():
    """市区町村管理者アカウント管理ページ"""
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
            except psycopg2.Error as err:
                conn.rollback()
                if hasattr(err, 'pgcode') and err.pgcode == '23505': # unique_violation
                    flash(f"ユーザー名「{username}」は既に使用されています。", "error")
                else:
                    flash(f"アカウント作成中にエラーが発生しました: {err}", "error")
        
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
    cursor.execute("SELECT organization_id, name FROM Organizations WHERE is_active = TRUE ORDER BY name")
    orgs = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("admin/org_admin_management.html", admins=admins, orgs=orgs)

@app.route('/admin/org_admin/delete/<string:username>', methods=['POST'])
def admin_org_admin_delete(username):
    """市区町村管理者アカウントを削除する"""
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
    """市区町村管理者アカウントを編集する"""
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
                conn.rollback()
                if hasattr(err, 'pgcode') and err.pgcode == '23505': # unique_violation
                    flash(f"カテゴリー「{category_name}」は既に存在します。", "error")
                else:
                    flash(f"登録中にエラーが発生しました: {err}", "error")
        
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
            conn.rollback()
            if hasattr(err, 'pgcode') and err.pgcode == '23505': # unique_violation
                flash(f"カテゴリー「{category_name}」は既に存在します。", "error")
            else:
                flash(f"更新中にエラーが発生しました: {err}", "error")
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
                conn.rollback()
                if hasattr(err, 'pgcode') and err.pgcode == '23505': # unique_violation
                    flash(f"ユーザー名「{username}」は既に使用されています。", "error")
                else:
                    flash(f"アカウント作成中にエラーが発生しました: {err}", "error")
        
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

@app.route("/admin/reply_to_inquiry")
def admin_reply_to_inquiry():
    """導入申請メール返信ページを表示します。"""
    if 'admin_user' not in session:
        return redirect(url_for('admin_login'))
    return render_template("admin/reply_to_inquiry.html")

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
                        GROUP BY r.recruitment_id, r.title, r.description, r.start_date, r.end_date        """)
        opportunities = [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": f"データの取得に失敗しました: {err}"}), 500
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
市区町村の役場などの名前: {data["municipality_name"]}
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
        categories = [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": "カテゴリの取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(categories)

@app.route("/api/organizations")
def get_organizations():
    """導入市区町村の一覧をデータベースから取得してJSONで返します。"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT organization_id, name FROM Organizations WHERE is_active = TRUE ORDER BY name")
        organizations = [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": f"市区町村一覧の取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(organizations)

@app.route("/api/prefectures")
def get_prefectures_api():
    """都道府県の一覧をデータベースから取得してJSONで返します。"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT prefecture_id, name FROM Prefectures ORDER BY prefecture_id")
        prefectures = [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": "都道府県の取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()
    return jsonify(prefectures)

@app.route("/api/municipalities")
def get_municipalities_api():
    """指定された都道府県に属する市区町村の一覧をデータベースから取得してJSONで返します。"""
    prefecture_id = request.args.get('prefecture_id', type=int)
    if not prefecture_id:
        return jsonify({"error": "prefecture_idが必要です。"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cursor.execute("SELECT organization_id, name FROM Organizations WHERE prefecture_id = %s ORDER BY name", (prefecture_id,))
        municipalities = [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": "市区町村の取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()
    return jsonify(municipalities)

@app.route('/api/current_user')
def current_user():
    """ログイン中のユーザー情報を返す"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'error': 'Not logged in'}), 401

    volunteer_id = session.get('volunteer_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT full_name, email, phone_number, mynumber FROM Volunteers WHERE volunteer_id = %s", (volunteer_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        # セッション情報も最新に保つ（任意だが推奨）
        session['user_name'] = user_data['full_name']
        session['user_email'] = user_data['email']
        session['user_phone'] = user_data['phone_number']
        # mynumberは機微情報なのでセッションには保存しない

        return jsonify({
            'volunteer_id': volunteer_id,
            'name': user_data['full_name'],
            'email': user_data['email'],
            'phone': user_data['phone_number'],
            'mynumber': user_data['mynumber']
        })
    except psycopg2.Error as e:
        print(f"Error fetching current user data: {e}")
        return jsonify({"error": "ユーザー情報の取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/user/update_profile', methods=['POST'])
def update_user_profile():
    """ログイン中のユーザーが自身のプロフィール（メール、電話番号、パスワード）を更新する"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'success': False, 'message': 'ログインが必要です。'}), 401

    volunteer_id = session.get('volunteer_id')
    data = request.get_json()
    
    email = data.get('email')
    phone_number = data.get('phone_number')
    mynumber = data.get('mynumber') # Get mynumber
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password:
        return jsonify({'success': False, 'message': '現在のパスワードは必須です。'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'データベースに接続できませんでした。'}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # 1. 現在のパスワードを確認
        cursor.execute("SELECT password_hash FROM Volunteers WHERE volunteer_id = %s", (volunteer_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'success': False, 'message': 'ユーザーが見つかりません。'}), 404

        password_match = False
        try:
            password_match = bcrypt.check_password_hash(user['password_hash'], current_password)
        except ValueError:
            password_match = (user['password_hash'] == current_password) # Plain text fallback

        if not password_match:
            return jsonify({'success': False, 'message': '現在のパスワードが正しくありません。'}), 403

        # 2. 情報を更新
        fields_to_update = []
        params = []
        
        # email and phone_number are always present in the form, so update them
        fields_to_update.append("email = %s")
        params.append(email)
        fields_to_update.append("phone_number = %s")
        params.append(phone_number)
        
        # mynumberの更新処理を追加
        if mynumber:
            # 簡単なバリデーション（12桁の数字か）
            if mynumber.isdigit() and len(mynumber) == 12:
                fields_to_update.append("mynumber = %s")
                params.append(mynumber)
            else:
                # エラーを返すか、単に無視するかは仕様による
                # ここではバリデーションエラーを返す
                return jsonify({'success': False, 'message': 'マイナンバーの形式が正しくありません。'}), 400

        if new_password:
            new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
            fields_to_update.append("password_hash = %s")
            params.append(new_password_hash)

        query = f"UPDATE Volunteers SET {', '.join(fields_to_update)} WHERE volunteer_id = %s"
        params.append(volunteer_id)
        
        cursor.execute(query, tuple(params))
        conn.commit()

        # セッション情報を更新
        session['user_email'] = email
        session['user_phone'] = phone_number

        return jsonify({'success': True, 'message': 'プロフィールが更新されました。'})

    except psycopg2.IntegrityError as e:
        conn.rollback()
        # emailの重複エラーをハンドリング
        if 'volunteers_email_key' in str(e):
             return jsonify({'success': False, 'message': 'そのメールアドレスは既に使用されています。'}), 409
        return jsonify({'success': False, 'message': '更新中にエラーが発生しました。'}), 500
    except Exception as e:
        conn.rollback()
        print(f"Profile update error: {e}")
        return jsonify({'success': False, 'message': 'プロフィールの更新中に予期せぬエラーが発生しました。'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/recruitments')
def get_recruitments_api():
    """ユーザー向けに募集一覧をJSONで返す。都道府県と市区町村区での絞り込みに対応。"""
    prefecture_id = request.args.get('prefecture_id', type=int)
    organization_id = request.args.get('organization_id', type=int)
    category_filter = request.args.get('category', '').strip()

    recruitments = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Corrected Query Structure
        base_query = """
            FROM Recruitments r
            JOIN Organizations o ON r.organization_id = o.organization_id
            LEFT JOIN RecruitmentCategoryMap rcm ON r.recruitment_id = rcm.recruitment_id
            LEFT JOIN RecruitmentCategories rc ON rcm.category_id = rc.category_id
        """
        
        where_clauses = ["r.status = 'Open'"]
        params = [] # Initialize params here
        
        if organization_id:
            where_clauses.append("o.organization_id = %s")
            params.append(organization_id)
        elif prefecture_id:
            where_clauses.append("o.prefecture_id = %s")
            params.append(prefecture_id)

        if category_filter and category_filter != 'all':
            where_clauses.append("r.recruitment_id IN (SELECT rcm.recruitment_id FROM RecruitmentCategoryMap rcm JOIN RecruitmentCategories rc ON rcm.category_id = rc.category_id WHERE rc.category_name = %s)")
            params.append(category_filter)

        query = f"""
            SELECT
                r.recruitment_id, r.title, r.description, o.name as organization_name,
                (SELECT string_agg(rc_sub.category_name, ', ')
                 FROM RecruitmentCategoryMap rcm_sub
                 JOIN RecruitmentCategories rc_sub ON rcm_sub.category_id = rc_sub.category_id
                 WHERE rcm_sub.recruitment_id = r.recruitment_id) AS category
            {base_query}
            WHERE {' AND '.join(where_clauses)}
            GROUP BY r.recruitment_id, o.name
            ORDER BY r.start_date DESC
        """
        
        cursor.execute(query, tuple(params))
        recruitments = [dict(row) for row in cursor.fetchall()]
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
    return jsonify(dict(recruitment))

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
        activities_rows = cursor.fetchall()
        activities = [dict(row) for row in activities_rows]
        
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

        # volunteer_idがNoneの場合はDBにNULLを挿入
        volunteer_id_to_insert = volunteer_id if volunteer_id is not None else None
        cursor.execute(
            "INSERT INTO Inquiries (recruitment_id, volunteer_id, inquiry_text, inquiry_date) VALUES (%s, %s, %s, %s)",
            (recruitment_id, volunteer_id_to_insert, inquiry_text, datetime.now())
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

@app.route('/api/user/interests', methods=['GET'])
def get_user_interests():
    """ログイン中のユーザーが興味を持つカテゴリIDのリストを返す"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'error': 'ログインしていません。'}), 401

    volunteer_id = session.get('volunteer_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    try:
        # 修正: DictCursorを使用して、プロジェクトの他の部分と一貫性を保つ
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT category_id FROM VolunteerCategoryInterests WHERE volunteer_id = %s", (volunteer_id,))
        # 修正: DictCursorの結果からデータを正しく抽出する
        interest_ids = [row['category_id'] for row in cursor.fetchall()]
        return jsonify(interest_ids)
    except psycopg2.Error as err:
        print(f"興味カテゴリの取得エラー: {err}")
        return jsonify({"error": "データの取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/user/interests', methods=['POST'])
def update_user_interests():
    """ログイン中のユーザーの興味カテゴリを更新する"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'success': False, 'message': 'ログインが必要です。'}), 401

    volunteer_id = session.get('volunteer_id')
    data = request.get_json()
    category_ids = data.get('category_ids', [])

    # 型チェック: category_idsがリストであることを確認
    if not isinstance(category_ids, list):
        return jsonify({'success': False, 'message': '無効なデータ形式です。'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'データベースに接続できませんでした。'}), 500

    cursor = conn.cursor()
    try:
        # 既存の興味カテゴリをすべて削除
        cursor.execute("DELETE FROM VolunteerCategoryInterests WHERE volunteer_id = %s", (volunteer_id,))

        # 新しい興味カテゴリを追加
        if category_ids:
            # executemanyを使用して複数の値を効率的に挿入
            insert_data = [(volunteer_id, int(cat_id)) for cat_id in category_ids]
            psycopg2.extras.execute_values(
                cursor,
                "INSERT INTO VolunteerCategoryInterests (volunteer_id, category_id) VALUES %s",
                insert_data
            )

        conn.commit()
        return jsonify({'success': True, 'message': '興味のあるカテゴリを更新しました。'})
    except (psycopg2.Error, ValueError) as err: # ValueErrorはint(cat_id)の失敗をキャッチ
        conn.rollback()
        print(f"興味カテゴリの更新エラー: {err}")
        return jsonify({'success': False, 'message': '更新中にエラーが発生しました。'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/user/favorites', methods=['GET'])
def get_user_favorites():
    """ログイン中のユーザーがお気に入り登録している市区町村IDのリストを返す"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'error': 'ログインしていません。'}), 401

    volunteer_id = session.get('volunteer_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT organization_id FROM VolunteerFavoriteOrganizations WHERE volunteer_id = %s", (volunteer_id,))
        favorite_ids = [row['organization_id'] for row in cursor.fetchall()]
        return jsonify(favorite_ids)
    except psycopg2.Error as err:
        print(f"お気に入り市区町村の取得エラー: {err}")
        return jsonify({"error": "データの取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/user/favorites', methods=['POST'])
def update_user_favorites():
    """ログイン中のユーザーのお気に入り市区町村を更新する"""
    if not session.get('logged_in') or not session.get('volunteer_id'):
        return jsonify({'success': False, 'message': 'ログインが必要です。'}), 401

    volunteer_id = session.get('volunteer_id')
    data = request.get_json()
    organization_ids = data.get('organization_ids', [])

    if not isinstance(organization_ids, list):
        return jsonify({'success': False, 'message': '無効なデータ形式です。'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'データベースに接続できませんでした。'}), 500

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM VolunteerFavoriteOrganizations WHERE volunteer_id = %s", (volunteer_id,))

        if organization_ids:
            insert_data = [(volunteer_id, int(org_id)) for org_id in organization_ids]
            psycopg2.extras.execute_values(
                cursor,
                "INSERT INTO VolunteerFavoriteOrganizations (volunteer_id, organization_id) VALUES %s",
                insert_data
            )

        conn.commit()
        return jsonify({'success': True, 'message': 'お気に入りの市区町村を更新しました。'})
    except (psycopg2.Error, ValueError) as err:
        conn.rollback()
        print(f"お気に入り市区町村の更新エラー: {err}")
        return jsonify({'success': False, 'message': '更新中にエラーが発生しました。'}), 500
    finally:
        cursor.close()
        conn.close()



# ------------------------------
# AI分析機能
# ------------------------------

# # Google Cloud Natural Language APIの認証情報を環境変数から読み込む
# # ai_key/borantelia-ca0b9d410b20.json はリポジリから除外されているため、環境変数から読み込む
# if "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
#     # 環境変数からJSON文字列を読み込み、一時ファイルとして保存
#     credentials_json = os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"]
#     temp_credentials_path = os.path.join(app.root_path, "temp_google_credentials.json")
#     with open(temp_credentials_path, "w") as f:
#         f.write(credentials_json)
#     os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_credentials_path
# else:
#     # ローカル開発環境など、環境変数がない場合は既存のファイルパスを使用
#     # ただし、ai_keyディレクトリは.gitignoreで除外されているため、このパスはローカルでのみ有効
#     os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(app.root_path, 'ai_key', 'borantelia-ca0b9d410b20.json')

# # Google Cloud Natural Language APIクライアントを初期化
# # 環境変数 GOOGLE_APPLICATION_CREDENTIALS が設定されているため、自動的に認証される
# language_client = language_v1.LanguageServiceClient()

# def analyze_recruitment_text(text):
#     """Google Cloud Natural Language APIを使用して、テキストの感情分析を行います。"""
#     try:
#         # ここでは既に初期化済みの language_client を使用
#         document = language_v1.Document(content=text, type_=language_v1.Document.Type.PLAIN_TEXT, language='ja')
#         sentiment = language_client.analyze_sentiment(request={'document': document}).document_sentiment
#         return {'sentiment_score': sentiment.score, 'sentiment_magnitude': sentiment.magnitude}
#     except Exception as e:
#         print(f"Natural Language API Error: {e}")
#         return {'sentiment_score': 0, 'sentiment_magnitude': 0, 'error': str(e)}

# @app.route('/analyze_popular_factors')
# def analyze_popular_factors():
#     """DBから求人テキストと応募者数を取得し、相関を分析して結果をJSONで返すAPI"""
#     conn = get_db_connection()
#     if conn is None:
#         return jsonify({"error": "データベースに接続できませんでした。"}), 500

#     cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
#     try:
#         query = """
#             SELECT 
#                 r.recruitment_id, r.title, r.description,
#                 COUNT(a.application_id) AS applicants
#             FROM Recruitments r
#             LEFT JOIN Applications a ON r.recruitment_id = a.recruitment_id
#             GROUP BY r.recruitment_id, r.title, r.description
#             ORDER BY applicants DESC;
#         """
#         cursor.execute(query)
#         db_data = cursor.fetchall()
#     except psycopg2.Error as err:
#         print(f"クエリエラー: {err}")
#         return jsonify({"error": "データ取得中にエラーが発生しました。"}), 500
#     finally:
#         cursor.close()
#         conn.close()

#     if not db_data:
#         return jsonify({"summary": "分析対象のデータがありません。", "details": []})

#     analysis_results = []
#     for row in db_data:
#         recruitment_text = f"{row['title']} {row['description']}"
#         nl_result = analyze_recruitment_text(recruitment_text)
#         analysis_results.append({
#             "id": row['recruitment_id'], "title": row['title'], "description": row['description'],
#             "applicants": row['applicants'], "sentiment_score": nl_result.get('sentiment_score', 0),
#             "sentiment_magnitude": nl_result.get('sentiment_magnitude', 0)
#         })

#     df_analysis = pd.DataFrame(analysis_results)
#     df_filtered = df_analysis[df_analysis['applicants'] > 0]
#     if len(df_filtered) > 1:
#         correlation = df_filtered['sentiment_score'].corr(df_filtered['applicants'])
#         correlation_summary = f"感情スコアと応募数の相関: {correlation:.2f}"
#     else:
#         correlation_summary = "相関を計算するにはデータが不十分です。"

#     report = {
#         "summary": "AIによる人気募集の傾向分析レポート",
#         "correlation_sentiment_applicants": correlation_summary,
#         "details": df_analysis.to_dict('records')
#     }
#     return jsonify(report)


# ------------------------------
# 市区町村職員（AdminUsers）エリア
# ------------------------------

def check_org_login():
    """市区町村職員のログイン状態をチェックするヘルパー関数"""
    # SuperAdminと区別するため、'org_user'セッションキーを使用
    return 'org_user' in session

@app.route("/staff/login", methods=['GET', 'POST'])
def staff_login():
    """市区町村職員ログインページとログイン処理"""
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
    
    # 関連するセッションキーのみを削除
    session.pop('org_user', None)
    session.pop('org_id', None)
    session.pop('org_role', None)

    # ログアウト時に既存のflashメッセージをクリア
    # これにより、ログイン成功時の「ようこそ、〇様」メッセージがログアウト後に表示されるのを防ぐ
    if '_flashes' in session:
        session['_flashes'].clear()

    # 「ログアウトしました」というメッセージを flash する
    flash("ログアウトしました。", "info") 
    
    # ログイン画面へリダイレクト
    return redirect(url_for('staff_login'))

@app.route("/staff/menu")
def staff_menu():
    """市区町村職員メニュー（ダッシュボード）。組織名を取得して表示する。"""
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

@app.route('/staff/user/create_volunteer_process', methods=['POST'])
@login_required
def create_volunteer_process():
    """職員がボランティアユーザーを作成する処理"""
    if not check_org_login():
        return jsonify({'success': False, 'message': 'この操作には職員としてのログインが必要です。'}), 403

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('full_name')
    mynumber = data.get('mynumber')
    email = data.get('email')
    phone_number = data.get('phone_number')

    # バリデーション
    if not all([username, password, full_name, mynumber, email]):
        return jsonify({'success': False, 'message': 'ユーザー名、パスワード、氏名、マイナンバー、メールアドレスは必須です。'}), 400

    # マイナンバーの形式チェック（12桁の数字）
    if not (mynumber.isdigit() and len(mynumber) == 12):
        return jsonify({'success': False, 'message': 'マイナンバーは12桁の数字で入力してください。'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'message': 'データベースに接続できませんでした。'}), 500
    
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # ユーザー名またはメールアドレスの重複を確認
        cursor.execute("SELECT volunteer_id FROM Volunteers WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'そのユーザー名またはメールアドレスは既に使用されています。'}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # 招待した職員の組織IDを割り当てる
        org_id = session.get('org_id')
        if not org_id:
            return jsonify({'success': False, 'message': 'セッションから組織IDが取得できませんでした。再度ログインしてください。'}), 400

        cursor.execute(
            """
            INSERT INTO Volunteers (organization_id, username, password_hash, full_name, mynumber, email, phone_number) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (org_id, username, hashed_password, full_name, mynumber, email, phone_number)
        )
        conn.commit()
        
        return jsonify({'success': True, 'message': 'ユーザーアカウントが正常に作成されました。'})

    except psycopg2.Error as e:
        conn.rollback()
        print(f"Database error during volunteer creation by staff: {e}")
        return jsonify({'success': False, 'message': f'データベースエラーが発生しました: {e}'}), 500
    except Exception as e:
        conn.rollback()
        print(f"Unexpected error during volunteer creation by staff: {e}")
        return jsonify({'success': False, 'message': '予期せぬエラーが発生しました。'}), 500
    finally:
        cursor.close()
        conn.close()



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

@app.route("/staff/re/applicant_list_staff")
def staff_applicant_list_page():
    """
    職員向けの応募者一覧ページをレンダリングします。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))
    return render_template("staff/re/applicant_list_staff.html")

@app.route("/staff/re/applicant_list/<int:recruitment_id>")
@login_required
def staff_applicant_list_by_recruitment(recruitment_id):
    """
    特定の募集案件の応募者一覧ページをレンダリングします。
    """
    return render_template("staff/re/applicant_list_staff.html", recruitment_id=recruitment_id)

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
        
        opportunities = [dict(row) for row in cursor.fetchall()]

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

@app.route("/staff/api/applications/by_recruitment/<int:recruitment_id>")
@login_required
def get_applications_by_recruitment(recruitment_id):
    """
    特定の募集案件に対する応募者リストと募集案件タイトルをJSONで返します。
    """
    org_id = session.get('org_id')
    if not org_id:
        return jsonify({"error": "組織情報が見つかりません。再ログインしてください。"}), 401

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # 募集案件のタイトルを取得し、その案件がログイン中の組織に属しているか確認
        cursor.execute(
            "SELECT title FROM Recruitments WHERE recruitment_id = %s AND organization_id = %s",
            (recruitment_id, org_id)
        )
        recruitment = cursor.fetchone()
        if not recruitment:
            return jsonify({"error": "指定された募集案件が見つからないか、アクセス権がありません。"}), 404
        
        recruitment_title = recruitment['title']

        # 応募者情報を取得
        cursor.execute(
            """
            SELECT 
                a.application_id AS id,
                v.full_name AS name,
                v.email,
                a.status
            FROM Applications a
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id
            WHERE a.recruitment_id = %s
            ORDER BY a.application_date DESC
            """,
            (recruitment_id,)
        )
        applications = [dict(row) for row in cursor.fetchall()]

        return jsonify({
            "recruitment_title": recruitment_title,
            "applications": applications
        })

    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": f"応募者データの取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

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

@app.route("/staff/recruitment/detail/<int:recruitment_id>")
def staff_opportunity_detail_page(recruitment_id):
    """
    案件詳細ページ (opportunity_detail_staff.html) を表示します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))
    
    return render_template("staff/re/opportunity_detail_staff.html", recruitment_id=recruitment_id)

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
                r.start_date AS activity_date,
                r.end_date AS deadline,
                r.contact_phone_number AS phone_number,
                r.contact_email AS email,
                r.status,
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
        
        # 3. 全カテゴリー情報を取得
        cursor.execute("SELECT category_id, category_name FROM RecruitmentCategories ORDER BY category_id")
        # Explicitly convert all_categories to a list of dictionaries
        all_categories = [dict(row) for row in cursor.fetchall()]

    except psycopg2.Error as err:
        print(f"クエリエラー: {err}")
        return jsonify({"error": f"データの取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

    # Convert DictRow to a regular dictionary to add new keys
    opportunity_dict = dict(opportunity)
    opportunity_dict['categories'] = selected_categories
    
    # HTML側のJSで使われる time_frame を暫定的に空文字として追加 (スキーマ変更対応)
    opportunity_dict['time_frame'] = '' 
    # HTML側のJSで使われる required_count, location, required_skills の代替値 (スキーマ変更対応)
    # SQLでSELECTしていないため、ここで明示的にキーを追加し、暫定値を設定する
    opportunity_dict['required_count'] = 1
    opportunity_dict['location'] = '未指定'
    opportunity_dict['required_skills'] = '特になし'

    return jsonify({
        "opportunity": opportunity_dict,
        "all_categories": all_categories
    })

@app.route('/staff/opportunity/bulk_upload', methods=['POST'])
@login_required
def bulk_upload_opportunities():
    """
    CSVファイルを受け取り、募集情報を一括でデータベースに登録します。
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'ファイルがありません。'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'ファイルが選択されていません。'}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({'success': False, 'error': 'CSVファイルを選択してください。'}), 400

    org_id = session.get('org_id')
    if not org_id:
        return jsonify({'success': False, 'error': '組織情報が見つかりません。ログインし直してください。'}), 401

    publish_immediately = request.form.get('publish') == 'true'
    status = 'Open' if publish_immediately else 'Draft'

    conn = get_db_connection()
    if conn is None:
        return jsonify({'success': False, 'error': 'データベースに接続できませんでした。'}), 500

    success_count = 0
    failure_count = 0
    errors = []

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # 事前に全カテゴリをメモリに読み込む
            cursor.execute("SELECT category_id, category_name FROM RecruitmentCategories")
            category_map = {row['category_name'].strip(): row['category_id'] for row in cursor.fetchall()}

            # ファイルストリームをデコード
            try:
                # BOM付きUTF-8に対応するため 'utf-8-sig' を使用
                content = file.stream.read().decode('utf-8-sig')
                stream = io.StringIO(content)
                reader = csv.DictReader(stream)
            except (UnicodeDecodeError, csv.Error) as e:
                 return jsonify({'success': False, 'error': f'CSVファイルの読み込みに失敗しました。文字コードがUTF-8であることを確認してください。エラー: {e}'}), 400


            for row_num, row in enumerate(reader, start=2):
                try:
                    # 必須項目のチェック
                    required_fields = ['title', 'description', 'start_date', 'end_date', 'contact_email']
                    if not all(field in row and row[field] for field in required_fields):
                        raise ValueError("必須項目が不足しています。")

                    title = row['title'].strip()
                    description = row['description'].strip()
                    start_date_str = row['start_date'].strip()
                    end_date_str = row['end_date'].strip()
                    contact_email = row['contact_email'].strip()
                    contact_phone_number = row.get('contact_phone_number', '').strip() or None
                    categories_str = row.get('categories', '').strip()

                    # 日付の検証
                    try:
                        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        raise ValueError("日付のフォーマットが不正です (YYYY-MM-DD形式である必要があります)。")

                    # 募集情報の登録
                    cursor.execute(
                        """
                        INSERT INTO Recruitments 
                        (organization_id, title, description, start_date, end_date, status, contact_email, contact_phone_number)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING recruitment_id;
                        """,
                        (org_id, title, description, start_date, end_date, status, contact_email, contact_phone_number)
                    )
                    recruitment_id = cursor.fetchone()['recruitment_id']

                    # カテゴリーの処理
                    if categories_str:
                        category_names = [name.strip() for name in categories_str.split(',') if name.strip()]
                        category_ids_to_insert = []
                        for name in category_names:
                            if name in category_map:
                                category_ids_to_insert.append(category_map[name])
                            else:
                                # 存在しないカテゴリは無視するか、エラーとして扱う
                                errors.append(f"行 {row_num}: 未知のカテゴリ '{name}' は無視されました。")
                        if category_ids_to_insert:
                            # 中間テーブルへの登録
                            insert_values = [(recruitment_id, cat_id) for cat_id in category_ids_to_insert]
                            psycopg2.extras.execute_values(
                                cursor,
                                "INSERT INTO RecruitmentCategoryMap (recruitment_id, category_id) VALUES %s",
                                insert_values
                            )
                    
                    conn.commit()
                    success_count += 1

                except (ValueError, psycopg2.Error) as e:
                    conn.rollback()
                    failure_count += 1
                    errors.append(f"行 {row_num}: {e}")

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': f'予期せぬエラーが発生しました: {e}'}), 500
    finally:
        conn.close()

    message = f'{success_count}件の募集を登録しました。'
    if failure_count > 0:
        message += f' {failure_count}件は失敗しました。'

    return jsonify({'success': True, 'message': message, 'errors': errors})

@app.route('/staff/api/recruitment/<int:rec_id>/applicants', methods=['GET'])
def get_recruitment_applicants(rec_id):
    """特定の募集案件に応募したユーザーの一覧をJSONで返す"""
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401

    sort_by = request.args.get('sort_by', 'application_date')
    sort_order = request.args.get('sort_order', 'desc')

    # Whitelist for sortable columns and their corresponding SQL expressions
    sortable_columns = {
        'application_date': 'a.application_date',
        'full_name': 'v.full_name',
        'status': 'a.status'
    }
    
    # Whitelist for sort orders
    sort_orders = {
        'asc': 'ASC',
        'desc': 'DESC'
    }

    # Default to application_date if invalid column is provided
    order_by_column = sortable_columns.get(sort_by, 'a.application_date')
    # Default to DESC if invalid order is provided
    order_direction = sort_orders.get(sort_order, 'DESC')

    org_id = session.get('org_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # 案件が本当にこの組織に属しているか確認（セキュリティのため）
        cursor.execute("SELECT organization_id FROM Recruitments WHERE recruitment_id = %s", (rec_id,))
        recruitment = cursor.fetchone()
        if not recruitment or recruitment['organization_id'] != org_id:
            return jsonify({"error": "案件が見つからないか、アクセス権がありません。"}), 404

        # 応募者情報を取得
        query = f"""
            SELECT a.application_id, v.full_name, v.email, a.status
            FROM Applications a
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id
            WHERE a.recruitment_id = %s
            ORDER BY {order_by_column} {order_direction}
        """
        cursor.execute(query, (rec_id,))
        
        applicants = [dict(row) for row in cursor.fetchall()]
        
    except psycopg2.Error as err:
        print(f"応募者情報の取得エラー: {err}")
        return jsonify({"error": "データの取得に失敗しました。"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(applicants)

@app.route('/staff/api/applications/batch_approve', methods=['POST'])
def batch_approve_applications():
    """選択された複数の応募を一括で承認する"""
    if not check_org_login():
        return jsonify({"success": False, "message": "認証が必要です"}), 401

    org_id = session.get('org_id')
    data = request.get_json()
    application_ids = data.get('application_ids')

    if not application_ids or not isinstance(application_ids, list) or len(application_ids) == 0:
        return jsonify({"success": False, "message": "無効なリクエストです。応募者IDのリストが必要です。"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "message": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # --- セキュリティチェック ---
        # 承認しようとしている応募が、本当にログイン中の職員の組織に属しているかを確認
        ids_tuple = tuple(application_ids)
        
        # 渡されたIDのリストから、ログイン中の組織に属するIDだけを抽出
        cursor.execute("""
            SELECT a.application_id
            FROM Applications a
            JOIN Recruitments r ON a.recruitment_id = r.recruitment_id
            WHERE r.organization_id = %s AND a.application_id IN %s
        """, (org_id, ids_tuple))
        
        valid_ids_rows = cursor.fetchall()
        valid_ids = [row['application_id'] for row in valid_ids_rows]

        if len(valid_ids) != len(application_ids):
            # リクエストされたIDの中に、権限のないIDが含まれている
            return jsonify({"success": False, "message": "権限のない応募が含まれています。"}), 403
        
        if not valid_ids:
            # 有効なIDが一つもなかった
            return jsonify({"success": False, "message": "承認対象の応募が見つかりません。"}), 404

        # --- ステータス更新 ---
        # 有効なIDのみを対象に更新
        valid_ids_tuple = tuple(valid_ids)
        cursor.execute(
            "UPDATE Applications SET status = 'Approved' WHERE application_id IN %s AND status = 'Pending'",
            (valid_ids_tuple,)
        )
        
        updated_rows = cursor.rowcount
        conn.commit()

        return jsonify({"success": True, "message": f"{updated_rows}件の応募を承認しました。"})

    except psycopg2.Error as err:
        conn.rollback()
        print(f"一括承認エラー: {err}")
        return jsonify({"success": False, "message": f"処理中にエラーが発生しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

def send_new_recruitment_notifications(app, recruitment_id, category_ids):
    """新しい募集が登録されたことを興味のあるユーザーにメールで通知する"""
    # 修正: test_request_contextを使用して、URL生成に必要なリクエストコンテキストを作成する
    with app.test_request_context():
        if not category_ids:
            return

        conn = get_db_connection()
        if conn is None:
            print("通知メール送信のためのDB接続に失敗しました。")
            return
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            # 1. 募集詳細を取得
            cursor.execute("""
                SELECT r.title, r.description, o.name as organization_name
                FROM Recruitments r
                JOIN Organizations o ON r.organization_id = o.organization_id
                WHERE r.recruitment_id = %s
            """, (recruitment_id,))
            recruitment = cursor.fetchone()
            if not recruitment:
                return

            # 2. 関連カテゴリに興味のあるユーザーを取得 (重複排除)
            query = """
                SELECT DISTINCT v.full_name, v.email
                FROM Volunteers v
                JOIN VolunteerCategoryInterests vci ON v.volunteer_id = vci.volunteer_id
                WHERE vci.category_id IN %s
            """
            cursor.execute(query, (tuple(category_ids),))
            users_to_notify = cursor.fetchall()

            if not users_to_notify:
                return

            # 3. 各ユーザーにメールを送信
            for user in users_to_notify:
                subject = f"[地域支援Hub] 興味のあるカテゴリに新しい募集が追加されました"
                # ログインページへのリンクに、リダイレクト先として募集詳細ページのパスを付与する
                opportunity_path = url_for('opportunity_detail', recruitment_id=recruitment_id)
                recruitment_url = url_for('user_login_page', next=opportunity_path, _external=True)
                body = f"""
{user['full_name']}様

ご登録いただいた興味のあるカテゴリに、新しいボランティア募集が追加されましたのでお知らせします。

--------------------------------
募集タイトル: {recruitment['title']}
募集団体: {recruitment['organization_name']}
--------------------------------

以下のリンクからご確認いただけます。
{recruitment_url}

※ログインしていない場合は、ログイン後に募集ページへ自動的に移動します。

今後とも地域支援Hubをよろしくお願いいたします。
"""
                msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[user['email']], body=body)
                mail.send(msg)
                print(f"通知メールを {user['email']} に送信しました。")

        except Exception as e:
            print(f"通知メールの送信中にエラーが発生しました: {e}")
        finally:
            cursor.close()
            conn.close()


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

    # 必須データのバリデーション (スキーマ変更を反映し、不要な 'location', 'required_count' を削除)
    required_fields = ['title', 'description', 'activity_date', 'deadline', 'email', 'status']
    if not all(field in data and data[field] for field in required_fields):
        # required_count は数値0も許容したい場合は調整が必要ですが、ここでは必須項目とします。
        return jsonify({"error": "必須項目が不足しているか、空です。"}), 400
    
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
            RETURNING recruitment_id
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
        new_recruitment_id = cursor.fetchone()[0]
        
        # 2. カテゴリーの紐付け (RecruitmentCategoryMap)
        selected_categories = data.get('categories', [])
        if selected_categories:
            insert_map_query = "INSERT INTO RecruitmentCategoryMap (recruitment_id, category_id) VALUES (%s, %s)"
            # DBに渡すcategory_idは文字列ではなく数値である必要があるため、int()で型変換
            category_values = [(new_recruitment_id, int(cat_id)) for cat_id in selected_categories]
            cursor.executemany(insert_map_query, category_values)
        
        conn.commit()

        # 3. メール通知 (公開の場合のみ、バックグラウンドで実行)
        if db_status == 'Open' and selected_categories:
            thread = threading.Thread(target=send_new_recruitment_notifications, args=(app, new_recruitment_id, selected_categories))
            thread.start()

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
        if conn: # psycopg2 connection object does not have is_connected() method
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
        return jsonify({"error": "必須項目が不足しているか、空です。"}), 400

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
            return jsonify({"error": "案件が見つからないか、更新する権限がありません。"}), 403

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
        if conn: # psycopg2 connection object does not have is_connected() method
            cursor.close()
            conn.close()

@app.route("/staff/applications")
@login_required
def staff_applications_list():
    """職員向けの応募者一覧ページ。組織全体の応募者を一覧表示する。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))

    org_id = session.get('org_id')
    org_name = "所属組織不明"
    applications = []

    sort_by = request.args.get('sort_by', 'application_date')
    sort_order = request.args.get('sort_order', 'desc')

    sortable_columns = {
        'application_date': 'a.application_date',
        'applicant_name': 'applicant_name',
        'opportunity_title': 'opportunity_title',
        'status': 'application_status'
    }
    sort_orders = {'asc': 'ASC', 'desc': 'DESC'}

    order_by_column = sortable_columns.get(sort_by, 'a.application_date')
    order_direction = sort_orders.get(sort_order, 'DESC')

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("staff/re/applicant_list.html", applications=applications, org_name=org_name)

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # 組織名を取得
        cursor.execute("SELECT name FROM Organizations WHERE organization_id = %s", (org_id,))
        org_data = cursor.fetchone()
        if org_data:
            org_name = org_data['name']

        # 組織に紐づく全ての応募情報を取得
        query = f"""
            SELECT
                a.application_id,
                a.application_date,
                a.status AS application_status,
                v.full_name AS applicant_name,
                v.username AS applicant_username,
                r.title AS opportunity_title
            FROM Applications a
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id
            JOIN Recruitments r ON a.recruitment_id = r.recruitment_id
            WHERE r.organization_id = %s
            ORDER BY {order_by_column} {order_direction}
        """
        cursor.execute(query, (org_id,))
        applications = [dict(row) for row in cursor.fetchall()]

    except psycopg2.Error as err:
        flash(f"応募者情報の取得中にエラーが発生しました: {err}", "error")
    finally:
        cursor.close()
        conn.close()

    return render_template("staff/re/applicant_list.html", applications=applications, org_name=org_name, sort_by=sort_by, sort_order=sort_order)


@app.route("/staff/recruitment/application/<int:application_id>")
@login_required
def staff_application_detail(application_id):
    """
    応募者詳細ページ。応募者の情報と、案件担当者の情報を表示します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))

    org_id = session.get('org_id')
    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("staff/re/application_detail.html", detail=None)

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        # 応募情報、ボランティア情報、案件情報、そして案件担当者（AdminUser）の情報を取得
        query = """
            SELECT
                a.application_id, a.status AS application_status, a.application_date,
                v.full_name AS applicant_name, v.email AS applicant_email, v.phone_number AS applicant_phone,
                v.username AS applicant_username, v.volunteer_id, v.postal_code, v.address, v.birth_year, v.gender,
                r.title AS recruitment_title, r.recruitment_id, r.description as recruitment_description,
                r.start_date, r.end_date, r.contact_phone_number, r.contact_email,
                o.name AS organization_name,
                au.username AS manager_name, au.role AS manager_role
            FROM Applications a
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id
            JOIN Recruitments r ON a.recruitment_id = r.recruitment_id
            JOIN Organizations o ON r.organization_id = o.organization_id
            LEFT JOIN AdminUsers au ON o.organization_id = au.organization_id AND au.role = 'OrgAdmin'
            WHERE a.application_id = %s AND o.organization_id = %s;
        """
        cursor.execute(query, (application_id, org_id))
        detail = cursor.fetchone()

        if not detail:
            flash("応募情報が見つからないか、アクセス権がありません。", "error")
            return redirect(url_for('staff_opportunity_list_page'))

    except psycopg2.Error as err:
        flash(f"詳細の取得中にエラーが発生しました: {err}", "error")
        detail = None
    finally:
        cursor.close()
        conn.close()

    return render_template("staff/re/application_detail.html", detail=detail)


@app.route('/staff/recruitment/application/<int:application_id>/update_status', methods=['POST'])
@login_required
def staff_update_application_status(application_id):
    """
    応募ステータスを更新します。
    """
    org_id = session.get('org_id')
    new_status = request.form.get('new_status')

    if not new_status or new_status not in ['Approved', 'Rejected', 'Pending']:
        flash("無効なステータスです。", "error")
        return redirect(url_for('staff_application_detail', application_id=application_id))

    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return redirect(url_for('staff_application_detail', application_id=application_id))

    cursor = conn.cursor()
    try:
        # 更新対象の応募が、ログイン中の職員の組織のものであることを確認 (セキュリティチェック)
        cursor.execute("""
            UPDATE Applications SET status = %s
            WHERE application_id = %s
            AND EXISTS (
                SELECT 1 FROM Recruitments r
                WHERE r.recruitment_id = Applications.recruitment_id AND r.organization_id = %s
            )
        """, (new_status, application_id, org_id))

        if cursor.rowcount == 0:
            flash("更新対象の応募が見つからないか、アクセス権がありません。", "error")
        else:
            conn.commit()
            flash(f"応募ステータスを「{new_status}」に更新しました。", "success")

    except psycopg2.Error as err:
        conn.rollback()
        flash(f"ステータス更新中にエラーが発生しました: {err}", "error")
    finally:
        cursor.close()
        conn.close()

    # 詳細ページにリダイレクト
    return redirect(url_for('staff_application_detail', application_id=application_id))


@app.route("/staff/recruitment/list")

@app.route("/staff/api/applications/by_recruitment/<int:recruitment_id>")
def get_staff_applications_by_recruitment(recruitment_id):
    """
    特定の募集案件に紐づく応募者の一覧をJSONで返します。
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401

    org_id = session.get('org_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # 案件の所有権を確認
        cursor.execute("SELECT title FROM Recruitments WHERE recruitment_id = %s AND organization_id = %s", (recruitment_id, org_id))
        recruitment = cursor.fetchone()
        if not recruitment:
            return jsonify({"error": "案件が見つからないか、アクセス権がありません。"}), 403

        # 応募者情報を取得
        cursor.execute("""
            SELECT 
                a.application_id AS id,
                v.full_name AS name,
                v.email,
                a.status
            FROM Applications a
            JOIN Volunteers v ON a.volunteer_id = v.volunteer_id
            WHERE a.recruitment_id = %s
            ORDER BY a.application_date DESC
        """, (recruitment_id,))
        
        applications = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            "recruitment_title": recruitment['title'],
            "applications": applications
        })

    except psycopg2.Error as err:
        print(f"応募者一覧の取得クエリエラー: {err}")
        return jsonify({"error": f"応募者一覧の取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/staff/re/management")
def staff_management_page():
    """職員向けのユーザー管理メニューページをレンダリングします。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
        
    return render_template("staff/re/manage.html")

@app.route("/staff/re/user_list")
def staff_user_list_page():
    """職員向けのユーザー一覧ページをレンダリングします。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
        
    return render_template("staff/re/user_list_staff.html")

@app.route("/api/staff/users")
def get_staff_users():
    """
    ログインしている職員の組織に紐づく全ユーザー（ボランティアのみ）の一覧をJSONで返します。
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401

    org_id = session.get('org_id')
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # ボランティアのみを取得
        cursor.execute("""
            SELECT 
                volunteer_id AS id, 
                full_name AS name, 
                username, 
                email, 
                'active' AS status, 
                'ボランティア' AS status_text
            FROM Volunteers
            -- WHERE organization_id = %s -- 組織によるフィルタリングを削除
        """) # org_idパラメータも削除
        volunteers = [dict(row) for row in cursor.fetchall()]
        
        # display_idとしてプレフィックスなしのIDを返す
        for v in volunteers:
            v['display_id'] = v['id']

    except psycopg2.Error as err:
        print(f"ユーザー一覧の取得クエリエラー: {err}")
        return jsonify({"error": f"ユーザー一覧の取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(volunteers)

@app.route("/staff/re/user_edit/<int:user_id>")
def staff_user_edit_page(user_id):
    """職員向けのユーザー編集ページをレンダリングします。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
        
    return render_template("staff/re/user_edit_staff.html", user_id=user_id)

@app.route("/api/user/<int:user_id>", methods=['GET'])
def get_user_detail(user_id):
    """
    特定のボランティアの詳細情報をJSONで返します。
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401

    org_id = session.get('org_id')
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    user_data = None
    
    try:
        # ボランティアの情報を取得
        cursor.execute("""
            SELECT 
                volunteer_id AS id, full_name, username, email, phone_number, 
                birth_year, gender, postal_code, address
            FROM Volunteers
            WHERE volunteer_id = %s AND organization_id = %s
        """, (user_id, org_id))
        user_data = cursor.fetchone()
        
        if not user_data:
            return jsonify({"error": "ユーザーが見つからないか、アクセス権がありません。"}), 404

    except psycopg2.Error as err:
        print(f"ユーザー詳細の取得クエリエラー: {err}")
        return jsonify({"error": f"ユーザー詳細の取得に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify(dict(user_data))

@app.route('/api/user/<int:user_id>', methods=['PUT'])
def update_user_detail(user_id):
    """
    特定のボランティアの情報を更新します。
    """
    if not check_org_login():
        return jsonify({"error": "認証が必要です"}), 401

    org_id = session.get('org_id')
    data = request.get_json()

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "データベースに接続できませんでした。"}), 500

    cursor = conn.cursor()
    
    try:
        # ボランティアの情報を更新
        update_query = """
            UPDATE Volunteers SET
                full_name = %s, email = %s, phone_number = %s,
                birth_year = %s, gender = %s, postal_code = %s, address = %s
            WHERE volunteer_id = %s AND organization_id = %s
        """
        cursor.execute(update_query, (
            data.get('fullName'), data.get('email'), data.get('phoneNumber'),
            data.get('birthYear'), data.get('gender'), data.get('postalCode'), data.get('address'),
            user_id, org_id
        ))
        
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "更新対象のユーザーが見つからないか、権限がありません。"}), 404
            
        conn.commit()
        return jsonify({"success": True, "message": "ユーザー情報が更新されました。"})

    except psycopg2.Error as err:
        conn.rollback()
        print(f"ユーザー更新クエリエラー: {err}")
        return jsonify({"error": f"ユーザー情報の更新に失敗しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/user/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user_data(user_id):
    """単一のボランティアデータを削除するAPI"""
    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "message": "データベース接続エラー"}), 500

    cursor = conn.cursor()
    
    try:
        # 1. 関連テーブルのレコードを削除 (Applications)
        cursor.execute("DELETE FROM Applications WHERE volunteer_id = %s", (user_id,))
        
        # 2. 関連テーブルのレコードを削除 (VolunteerCategoryInterests)
        cursor.execute("DELETE FROM VolunteerCategoryInterests WHERE volunteer_id = %s", (user_id,))

        # 3. 本体であるボランティアを削除
        cursor.execute("DELETE FROM Volunteers WHERE volunteer_id = %s", (user_id,))
        
        if cursor.rowcount == 0:
            # ボランティアが見つからなかった場合
            conn.rollback()
            return jsonify({"success": False, "message": "削除対象のユーザーが見つかりませんでした。"}), 404
        
        conn.commit()
        
        return jsonify({"success": True, "message": f"ユーザーID {user_id} を削除しました。"}), 200

    except psycopg2.Error as e:
        conn.rollback()
        print(f"ユーザー削除エラー: {e}")
        return jsonify({"success": False, "message": "ユーザーの削除中にエラーが発生しました"}), 500
        
    finally:
        cursor.close()
        conn.close()

@app.route('/staff/user/user_invite', methods=['GET', 'POST'])
def staff_user_invite():
    """
    職員がボランティアユーザーを招待するページを表示します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))

    # GETリクエストの場合、フォームをレンダリング
    if request.method == 'GET':
        return render_template('staff/user/user_invite.html')

    # POSTリクエストの場合、フォームデータを処理
    elif request.method == 'POST':
        # フォームからデータを取得
        username = request.form.get('username') # Add this line
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        mynumber = request.form.get('mynumber') # マイナンバーを追加

        # 必須フィールドのチェック
        if not all([full_name, email, mynumber]):
            flash("氏名、メールアドレス、マイナンバーは必須です。", "error")
            return render_template('staff/user/user_invite.html',
                                   full_name=full_name, email=email,
                                   phone_number=phone_number, mynumber=mynumber)

        # マイナンバーの形式チェック（12桁の数字）
        if not (mynumber.isdigit() and len(mynumber) == 12):
            flash("マイナンバーは12桁の数字で入力してください。", "error")
            return render_template('staff/user/user_invite.html',
                                   full_name=full_name, email=email,
                                   phone_number=phone_number, mynumber=mynumber)

        # セッションに一時的にデータを保存して確認画面へ
        # セッションに一時的にデータを保存して確認画面へ
        session['invite_data'] = {
            'username': username,
            'password': request.form.get('password'), # Add password here
            'full_name': full_name,
            'email': email,
            'phone_number': phone_number,
            'mynumber': mynumber
        }
        return redirect(url_for('staff_user_invite_confirm_page'))
        
    return render_template("staff/user/user_invite.html")

@app.route("/staff/user/user_invite_confirm")
def staff_user_invite_confirm_page():
    """
    職員がボランティアユーザーを招待する際の確認ページを表示・処理します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))

    invite_data = session.get('invite_data')

    if not invite_data:
        flash("招待データが見つかりません。再度入力してください。", "error")
        return redirect(url_for('staff_user_invite'))

    if request.method == 'POST':
        # ここで実際にユーザーをDBに登録する処理を呼び出す
        # create_volunteer_process はAPIエンドポイントなので、直接呼び出すのではなく、
        # そのロジックをここに移植するか、内部的に呼び出すヘルパー関数にするのが適切
        # 今回は、簡略化のため、直接DB登録ロジックを記述します。

        conn = get_db_connection()
        if conn is None:
            flash("データベースに接続できませんでした。", "error")
            return render_template('staff/user/user_invite_confirm.html', invite_data=invite_data)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            # ユーザー名（メールアドレスを仮に使用）またはメールアドレスの重複を確認
            # 招待ユーザーには初期パスワードを自動生成
            initial_password = secrets.token_urlsafe(16) # 16文字の安全なパスワードを生成
            hashed_password = bcrypt.generate_password_hash(initial_password).decode('utf-8')
            
            # 招待した職員の組織IDを割り当てる
            org_id = session.get('org_id')
            if not org_id:
                flash("セッションから組織IDが取得できませんでした。再度ログインしてください。", "error")
                return redirect(url_for('staff_login'))

            # ユーザー名としてフォームで入力されたユーザー名を使用
            username_to_use = invite_data['username']

            cursor.execute("SELECT volunteer_id FROM Volunteers WHERE username = %s OR email = %s", (username_to_use, invite_data['email']))
            if cursor.fetchone():
                flash("そのメールアドレスは既に使用されています。", "error")
                return render_template('staff/user/user_invite_confirm.html', invite_data=invite_data)

            cursor.execute(
                """
                INSERT INTO Volunteers (organization_id, username, password_hash, full_name, mynumber, email, phone_number) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (org_id, username_to_use, hashed_password, invite_data['full_name'], invite_data['mynumber'], invite_data['email'], invite_data['phone_number'])
            )
            conn.commit()

            # 招待メールを送信
            msg = Message(
                subject="地域支援Hub ボランティア登録のご案内",
                sender=app.config['MAIL_USERNAME'],
                recipients=[invite_data['email']],
                body=f"""
{invite_data['full_name']}様

地域支援Hubへのご登録ありがとうございます。
以下の情報でアカウントが作成されました。

ユーザー名: {username_to_use}
初期パスワード: {initial_password}

以下のURLからログインし、パスワードを変更してください。
{url_for('user_login_page', _external=True)}

今後とも地域支援Hubをよろしくお願いいたします。
"""
            )
            mail.send(msg)

            session.pop('invite_data', None) # 招待データをクリア
            flash("ボランティアユーザーを招待し、初期パスワードを記載したメールを送信しました。", "success")
            return redirect(url_for('staff_user_invite_complete_page'))

        except psycopg2.Error as e:
            conn.rollback()
            print(f"Database error during volunteer invitation: {e}")
            flash(f"データベースエラーが発生しました: {e}", "error")
            return render_template('staff/user/user_invite_confirm.html', invite_data=invite_data)
        except Exception as e:
            conn.rollback()
            print(f"Unexpected error during volunteer invitation: {e}")
            flash(f"予期せぬエラーが発生しました: {e}", "error")
            return render_template('staff/user/user_invite_confirm.html', invite_data=invite_data)
        finally:
            cursor.close()
            conn.close()

    return render_template('staff/user/user_invite_confirm.html', invite_data=invite_data)

@app.route("/staff/re/user_invite_complete")
def staff_user_invite_complete_page():
    """職員向けのユーザー招待完了ページをレンダリングします。"""
    if not check_org_login():
        return redirect(url_for('staff_login'))
        
    return render_template("staff/user/user_invite_complete.html")

@app.route('/api/register_volunteer', methods=['POST'])
def register_volunteer_api():
    """
    職員がボランティアユーザーを代理登録するAPI。
    """
    if not check_org_login():
        return jsonify({"success": False, "message": "認証が必要です"}), 401

    org_id = session.get('org_id')
    data = request.get_json()
    
    # 必須データのバリデーション
    required_fields = ['username', 'password', 'full_name', 'mynumber', 'email']
    if not all(field in data and data[field] for field in required_fields):
        return jsonify({"success": False, "message": "必須項目が不足しています。"}), 400

    # パスワードをハッシュ化
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')

    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "message": "データベース接続エラー"}), 500

    cursor = conn.cursor()
    
    try:
        # Volunteersテーブルに新しいユーザーを挿入
        insert_query = """
            INSERT INTO Volunteers (
                organization_id, username, password_hash, full_name, email, phone_number,
                birth_year, gender, postal_code, address, registration_date
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """
        cursor.execute(insert_query, (
            org_id,
            data['username'],
            hashed_password,
            data['full_name'],
            data['email'],
            data.get('phone_number'),
            data.get('birth_year'),
            data.get('gender'),
            data.get('postal_code'),
            data.get('address')
        ))
        
        conn.commit()
        return jsonify({"success": True, "username": data['full_name']})

    except psycopg2.IntegrityError as e:
        conn.rollback()
        if 'volunteers_username_key' in str(e):
            return jsonify({"success": False, "message": f"ユーザー名 '{data['username']}' は既に使用されています。"}), 409
        if 'volunteers_email_key' in str(e):
            return jsonify({"success": False, "message": f"メールアドレス '{data['email']}' は既に使用されています。"}), 409
        return jsonify({"success": False, "message": "一意性制約違反です。"}), 409
    except psycopg2.Error as err:
        conn.rollback()
        print(f"ボランティア登録クエリエラー: {err}")
        return jsonify({"success": False, "message": f"データベース登録中にエラーが発生しました: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/staff/account/list')
def staff_account_list():
    """
    同じ組織に所属する職員アカウントの一覧ページを表示します。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))

    org_id = session.get('org_id')
    conn = get_db_connection()
    if conn is None:
        flash("データベースに接続できませんでした。", "error")
        return render_template("staff/re/staff_list.html", accounts=[])

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
        accounts = []
    finally:
        cursor.close()
        conn.close()

    return render_template("staff/re/staff_list.html", accounts=accounts)

@app.route('/staff/account/create', methods=['GET', 'POST'])
def staff_account_create():
    """
    新しい職員アカウント（Staffロール）を作成するページと処理。
    """
    if not check_org_login():
        return redirect(url_for('staff_login'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        if not all([username, password, password_confirm]):
            flash("すべてのフィールドを入力してください。", "error")
            return redirect(url_for('staff_account_create'))
        if password != password_confirm:
            flash("パスワードが一致しません。", "error")
            return redirect(url_for('staff_account_create'))

        org_id = session.get('org_id')
        pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')

        conn = get_db_connection()
        if conn is None:
            flash("データベースに接続できませんでした。", "error")
            return redirect(url_for('staff_account_create'))

        cursor = conn.cursor()
        try:
            # 職員アカウントは 'Staff' ロールで固定
            cursor.execute(
                "INSERT INTO AdminUsers (organization_id, username, password_hash, role) VALUES (%s, %s, %s, 'Staff')",
                (org_id, username, pw_hash)
            )
            conn.commit()
            flash(f"新しい職員アカウント「{username}」を作成しました。", "success")
            return redirect(url_for('staff_menu'))
        except psycopg2.IntegrityError:
            conn.rollback()
            flash(f"ユーザー名「{username}」は既に使用されています。", "error")
        except psycopg2.Error as err:
            conn.rollback()
            flash(f"アカウント作成中にエラーが発生しました: {err}", "error")
        finally:
            cursor.close()
            conn.close()
        
        return redirect(url_for('staff_account_create'))

    return render_template("staff/re/staff_create.html")

# ------------------------------
# メイン実行ブロック
# ------------------------------

@app.route('/csv/<path:filename>')
def download_csv_template(filename):
    """CSVテンプレートファイルをダウンロードするためのルート"""
    return send_from_directory('csv', filename, as_attachment=True)





if __name__ == "__main__":
    # SSLコンテキストの代わりに環境変数を使用
    # context = ('path/to/cert.pem', 'path/to/key.pem')
    # app.run(debug=True, host='0.0.0.0', port=5000, ssl_context=context)
    app.run(debug=True, host='0.0.0.0', port=5000)
