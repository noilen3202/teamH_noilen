import os
import psycopg2
from dotenv import load_dotenv

def populate_database():
    """
    Reads sample_data.sql and executes it to populate the database.
    """
    # Load environment variables from .env file
    load_dotenv()
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("エラー: 環境変数 DATABASE_URL が .env ファイルに設定されていません。")
        return

    sql_file_path = 'sample_data.sql'
    if not os.path.exists(sql_file_path):
        print(f"エラー: {sql_file_path} が見つかりません。")
        return
        
    # Read the SQL file
    with open(sql_file_path, 'r', encoding='utf-8') as f:
        sql_script = f.read()

    conn = None
    try:
        # Connect to the database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Execute the entire SQL script
        cursor.execute(sql_script)
        
        # Commit the changes
        conn.commit()
        
        print("成功: sample_data.sql の内容をデータベースに登録しました。")
        
    except psycopg2.Error as err:
        print(f"データベースエラー: {err}")
        if conn:
            conn.rollback()
            
    finally:
        if conn:
            cursor.close()
            conn.close()
            print("データベース接続を閉じました。")

if __name__ == "__main__":
    print("データベースに初期データを登録します...")
    populate_database()
    print("処理が完了しました。")
