import os
import psycopg2
from dotenv import load_dotenv

def add_mynumber_column():
    """
    Connects to the database and adds the 'mynumber' column to the 'volunteers' table.
    """
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("エラー: 環境変数 DATABASE_URL が .env ファイルに設定されていません。")
        return

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Add the column. This will fail if the column already exists.
        # We handle this specific error.
        alter_query = "ALTER TABLE volunteers ADD COLUMN mynumber VARCHAR(12);"
        
        cursor.execute(alter_query)
        conn.commit()
        
        print("成功: 'volunteers' テーブルに 'mynumber' カラムを追加しました。")
        
    except psycopg2.Error as err:
        # Check if the error is "column already exists"
        if err.pgcode == '42701': # duplicate_column
            print("情報: 'mynumber' カラムは既に存在しているため、スキップしました。")
        else:
            print(f"データベースエラー: {err}")
            if conn:
                conn.rollback()
            
    finally:
        if conn:
            cursor.close()
            conn.close()
            print("データベース接続を閉じました。")

if __name__ == "__main__":
    print("'volunteers' テーブルの構造を更新します...")
    add_mynumber_column()
    print("処理が完了しました。")
