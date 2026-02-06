import os
import psycopg2
from dotenv import load_dotenv

def fix_organization_status():
    """
    Connects to the database and updates the is_active status for all organizations.
    """
    # Load environment variables from .env file
    load_dotenv()
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("エラー: 環境変数 DATABASE_URL が .env ファイルに設定されていません。")
        return

    conn = None
    try:
        # Connect to the database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # The SQL command to execute
        update_query = 'UPDATE Organizations SET is_active = TRUE WHERE is_active IS NOT TRUE;'
        
        # Execute the command
        cursor.execute(update_query)
        
        # Get the number of rows updated
        updated_rows = cursor.rowcount
        
        # Commit the changes to the database
        conn.commit()
        
        print(f"成功: {updated_rows} 件の市区町村が「有効」に更新されました。")
        
    except psycopg2.Error as err:
        print(f"データベースエラー: {err}")
        if conn:
            conn.rollback() # Roll back the transaction on error
            
    finally:
        if conn:
            # Close the connection
            cursor.close()
            conn.close()
            print("データベース接続を閉じました。")

if __name__ == "__main__":
    print("既存の市区町村データを修正します...")
    fix_organization_status()
    print("処理が完了しました。")
