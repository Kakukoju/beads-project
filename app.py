from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)

# 繁體中文註解：設定 RDS 連線字串
# 格式：postgresql://用戶名:密碼@主機位址:埠號/資料庫名稱
DB_URL = "postgresql://harryguo:skyla168@database-1.cfutwrwyrxts.ap-northeast-1.rds.amazonaws.com:5432/beadsdb"

app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

@app.route('/')
def test_db():
    try:
        # 測試執行一個簡單的 SQL 查詢
        db.session.execute(text('SELECT 1'))
        return jsonify({
            "status": "success",
            "message": "成功連線至 RDS (beadsdb)!",
            "host": "database-1.cfutwrwyrxts.ap-northeast-1.rds.amazonaws.com"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)