# config.py
import os
import pymysql
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 基础配置 — 密码从环境变量读取，不硬编码
MYSQL_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "localhost"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", "123456"),
    "database": os.environ.get("MYSQL_DATABASE", "canteen_waste_monitor"),
    "charset": "utf8mb4"
}

# 1. 原生pymysql连接（适合简单操作）
def get_mysql_connection():
    """获取MySQL连接"""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        return conn
    except Exception as e:
        print(f"数据库连接失败：{e}")
        raise

# 2. SQLAlchemy ORM连接（适合复杂项目）
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}?charset=utf8mb4"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_judge_db_connection():
    """获取评委打分独立数据库连接"""
    config = MYSQL_CONFIG.copy()
    config["database"] = "judge_scoring_db"
    try:
        conn = pymysql.connect(**config)
        return conn
    except pymysql.err.OperationalError:
        # 首次启动：创建独立数据库
        conn = pymysql.connect(
            host=MYSQL_CONFIG["host"], port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"], password=MYSQL_CONFIG["password"],
            charset=MYSQL_CONFIG["charset"]
        )
        cursor = conn.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS judge_scoring_db DEFAULT CHARSET utf8mb4")
        cursor.close()
        conn.close()
        conn = pymysql.connect(**config)
        return conn

# 依赖函数（FastAPI中使用）
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()