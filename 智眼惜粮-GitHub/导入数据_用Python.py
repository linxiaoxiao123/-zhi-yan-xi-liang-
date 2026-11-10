# -*- coding: utf-8 -*-
"""
【队友用】把「智眼惜粮_数据库导入.sql」导入你自己本机的 MySQL
适合电脑上没有 mysql 命令行客户端的情况。

前置：
  1. 本机已装 MySQL 并启动
  2. 已安装 pymysql：  pip install pymysql

运行：
  python 导入数据_用Python.py
  （会提示输入你的 MySQL root 密码；也可先 set MYSQL_PASSWORD=你的密码 再运行）
"""
import os
import sys
import getpass

try:
    import pymysql
except ImportError:
    print("缺少 pymysql，请先执行： pip install pymysql")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
SQL_FILE = os.path.join(HERE, "智眼惜粮_数据库导入.sql")

if not os.path.exists(SQL_FILE):
    print("找不到 SQL 文件：%s" % SQL_FILE)
    sys.exit(1)

pwd = os.getenv("MYSQL_PASSWORD")
if not pwd:
    pwd = getpass.getpass("请输入你的 MySQL root 密码（直接回车表示空密码）：")

host = os.getenv("DB_HOST", "localhost")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "root")

print("连接 MySQL %s:%s 用户 %s ..." % (host, port, user))
conn = pymysql.connect(host=host, port=port, user=user, password=pwd,
                       charset="utf8mb4", autocommit=True)
cur = conn.cursor()
print("连接成功\n开始导入（数据量较大，约需十几秒到一分钟）...")

with open(SQL_FILE, encoding="utf-8") as f:
    sql = f.read()

# 去掉整行 "--" 注释后按语句切分
clean_lines = [ln for ln in sql.split("\n") if not ln.strip().startswith("--")]
stmts = [s.strip() for s in "\n".join(clean_lines).split(";\n") if s.strip()]

ok = err = 0
for s in stmts:
    try:
        cur.execute(s)
        ok += 1
    except Exception as e:
        err += 1
        if err <= 5:
            print("  [失败] %s... -> %s" % (s[:70].replace("\n", " "), str(e)[:90]))

print("\n执行完成：成功 %d 条，失败 %d 条" % (ok, err))

if err == 0:
    print("\n=== 校验结果 ===")
    for db, tb, expect in [
        ("canteen_waste_monitor", "detection_records", 7349),
        ("canteen_waste_monitor", "detection_items", 36245),
        ("canteen_waste_monitor", "system_config", 5),
        ("judge_scoring_db", "judge_evaluations", 50),
    ]:
        try:
            cur.execute("SELECT COUNT(*) FROM `%s`.`%s`" % (db, tb))
            n = cur.fetchone()[0]
            print("  %s.%s: %d 条（期望 %d）%s"
                  % (db, tb, n, expect, "OK" if n == expect else "!! 不符"))
        except Exception as e:
            print("  %s.%s 校验失败: %s" % (db, tb, str(e)[:80]))
    print("\n导入成功！后端 config.py 保持 host=localhost 即可，无需改其他配置。")
else:
    print("\n有语句执行失败，请检查上面报错（多半是权限或已存在的库冲突）。")

cur.close()
conn.close()
