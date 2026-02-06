# create_superadmin.py

import os
import getpass
from flask import Flask
from flask_bcrypt import Bcrypt
import psycopg2
from dotenv import load_dotenv

# このスクリプトはFlaskアプリのコンテキスト外で実行されるため、
# ダミーのFlaskアプリを作成してBcryptを初期化します。
app = Flask(__name__)
bcrypt = Bcrypt(app)

# .envファイルから環境変数を読み込む
load_dotenv()

def get_db_connection():
    """データベース接続を取得します。"""
    try:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("[エラー] 環境変数 DATABASE_URL が設定されていません。")
            return None
        conn = psycopg2.connect(database_url)
        return conn
    except psycopg2.Error as err:
        print(f"[エラー] データベースに接続できませんでした: {err}")
        return None

def main():
    """メインの処理"""
    print("--- 新規SuperAdmin作成スクリプト ---")
    
    username = input("作成する管理者のユーザー名を入力してください: ")
    password = getpass.getpass("パスワードを入力してください（入力内容は表示されません）: ")
    password_confirm = getpass.getpass("パスワードを再入力してください（確認用）: ")

    if not all([username, password, password_confirm]):
        print("\n[エラー] ユーザー名とパスワードは必須です。処理を中断します。")
        return

    if password != password_confirm:
        print("\n[エラー] パスワードが一致しません。処理を中断します。")
        return

    # パスワードをハッシュ化
    pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    print(f"\nユーザー名 '{username}' のパスワードをハッシュ化しました。")

    conn = get_db_connection()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
        # 既存のユーザーを上書き、または新規作成
        cursor.execute("SELECT super_admin_id FROM SuperAdmins WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user:
            print(f"既存のユーザー '{username}' のパスワードを更新します。")
            cursor.execute("UPDATE SuperAdmins SET password_hash = %s WHERE username = %s", (pw_hash, username))
        else:
            print(f"新規ユーザー '{username}' を作成します。")
            cursor.execute("INSERT INTO SuperAdmins (username, password_hash) VALUES (%s, %s)", (username, pw_hash))
        
        conn.commit()
        print("\n[成功] データベースの更新が完了しました。")

    except psycopg2.Error as err:
        print(f"\n[エラー] データベース操作中にエラーが発生しました: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()
