# ========== 核心依赖导入 ==========
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request, Form
import re
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from datetime import datetime, timedelta
import cv2
import numpy as np
from ultralytics import YOLO
import io
import time
import os
import logging
from PIL import Image, ImageDraw, ImageFont
import uuid
import torch
from torchvision import transforms
from unet_model import UNet
from typing import List, Optional
from config import get_mysql_connection, get_judge_db_connection
from waste_cause_inference import predict_with_rules
import pymysql
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import uvicorn
import socket
import gc
import urllib.request
import json

# ========== 日志配置 ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ========== FastAPI应用初始化 ==========
app = FastAPI(title="餐盘残余菜品检测API", version="1.0")

# ========== 评委打分表（独立数据库，自动建表） ==========
def init_judge_table():
    try:
        conn = get_judge_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS judge_evaluations (
                id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                record_id BIGINT NOT NULL COMMENT '关联检测记录ID',
                result ENUM('correct','incorrect') NOT NULL COMMENT '评委判定：正确/错误',
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '评价时间',
                PRIMARY KEY (id),
                UNIQUE KEY uk_record_id (record_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评委打分记录表'
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS judge_config (
                config_key VARCHAR(64) PRIMARY KEY,
                config_value VARCHAR(128) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cursor.execute("""
            INSERT IGNORE INTO judge_config (config_key, config_value)
            VALUES ('reset_time', '2000-01-01 00:00:00')
        """)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("✅ judge_scoring_db 就绪（judge_evaluations + judge_config）")
    except Exception as e:
        logger.warning(f"⚠️ judge_scoring_db 初始化失败: {e}")

init_judge_table()

def get_judge_reset_time():
    """读取评委打分的重置时间"""
    conn = get_judge_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT config_value FROM judge_config WHERE config_key = 'reset_time'")
        row = cursor.fetchone()
        return row[0] if row else "2000-01-01 00:00:00"
    finally:
        cursor.close()
        conn.close()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
files_path = os.path.join(BASE_DIR, "files")
os.makedirs(files_path, exist_ok=True)
app.mount("/files", StaticFiles(directory=files_path))

# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 接口鉴权中间件（简单 token） ==========
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """除白名单外的 API 请求需携带正确 token，防止公网未授权访问"""
    # 放行 CORS 预检请求：OPTIONS 不带 Authorization 头，交由 CORS 中间件处理
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    # 白名单：图片静态文件、首页、健康检查、API 文档不鉴权
    if (path.startswith("/files") or path.startswith("/static")
            or path in ("/", "/health")):
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else auth.strip()
    if token != API_TOKEN:
        return JSONResponse(status_code=401, content={"detail": "未授权：token 缺失或错误"})
    return await call_next(request)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ========== 模型核心参数配置 ==========
MODEL_PATH = "model/best.pt"
DETECT_PORT = 8000
# 对外图片/接口的基础地址：默认本机，内网穿透或部署时用环境变量 BASE_URL 覆盖
# 例：BASE_URL=https://xxx.cpolar.top 或 http://公网IP:8000（结尾不要带 /）
BASE_URL = os.environ.get("BASE_URL", f"http://127.0.0.1:{DETECT_PORT}").rstrip("/")
# 接口鉴权口令：默认值仅供本地开发，穿透/部署时务必用环境变量 API_TOKEN 覆盖
API_TOKEN = os.environ.get("API_TOKEN", "zhongyan-xiliang-2026")

# Coze 智能体配置：bot_id 和 API token 从环境变量读取
COZE_BOT_ID = os.environ.get("COZE_BOT_ID", "")
COZE_API_TOKEN = os.environ.get("COZE_API_TOKEN", "")
COZE_API_BASE = "https://api.coze.cn"

def rewrite_image_url(url):
    """把图片 URL 的主机部分替换为当前 BASE_URL，防止内网穿透/部署后历史记录裂图。
    只替换 scheme://host[:port] 前缀，保留 /files/xxx.jpg 路径不变。"""
    if not url:
        return url
    return re.sub(r"^https?://[^/]+", BASE_URL, url)
DETECT_PARAMS = {
    "conf": 0.3, "iou": 0.5, "imgsz": 800,
    "augment": False, "agnostic_nms": True, "max_det": 20, "half": False
}

# U-Net配置
UNET_MODEL_PATH = "model/unet_best.pth"
UNET_NUM_CLASSES = 3
UNET_IMG_SIZE = (256, 256)
UNET_PREPROCESS = transforms.Compose([
    transforms.Resize(UNET_IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.229, 0.225])
])
unet_model = None
TORCH_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 缓存中文字体，避免每次绘图重复加载
try:
    _FONT_CACHE = ImageFont.truetype("simhei.ttf", 20)
except Exception:
    _FONT_CACHE = ImageFont.load_default(size=20)

# 文件限制
SINGLE_FILE_LIMIT = 15 * 1024 * 1024
TOTAL_FILE_LIMIT = 100 * 1024 * 1024
ALLOWED_IMAGE_TYPES = ["jpg", "jpeg", "png", "bmp", "webp"]

# ========== 模型加载 ==========
def load_yolo_model():
    try:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"YOLO模型不存在：{os.path.abspath(MODEL_PATH)}")
        model = YOLO(MODEL_PATH)
        logger.info(f"✅ YOLO模型加载成功：{MODEL_PATH}")
        return model
    except Exception as e:
        logger.error(f"❌ YOLO加载失败：{str(e)}")
        raise

def load_unet_model():
    global unet_model
    if unet_model is not None:
        return unet_model
    try:
        if not os.path.exists(UNET_MODEL_PATH):
            raise FileNotFoundError(f"U-Net模型不存在：{os.path.abspath(UNET_MODEL_PATH)}")
        unet_model = UNet(num_classes=UNET_NUM_CLASSES).to(TORCH_DEVICE)
        unet_model.load_state_dict(torch.load(UNET_MODEL_PATH, map_location=TORCH_DEVICE))
        unet_model.eval()
        logger.info(f"✅ U-Net模型加载成功：{UNET_MODEL_PATH}，设备：{TORCH_DEVICE}")
        return unet_model
    except Exception as e:
        logger.error(f"❌ U-Net加载失败：{str(e)}")
        raise

# ========== 模型推理 ==========
def yolo_infer(image: np.ndarray):
    return yolo_model(image, **DETECT_PARAMS)

def unet_infer(image: Image.Image) -> np.ndarray:
    model = load_unet_model()
    input_tensor = UNET_PREPROCESS(image).unsqueeze(0).to(TORCH_DEVICE)
    with torch.no_grad():
        output = model(input_tensor)
    return torch.argmax(output, dim=1).squeeze(0).cpu().numpy()

# 浪费率计算
def calculate_wastage_rate(mask: np.ndarray) -> tuple[float, int, int]:
    """基于U-Net分割掩码计算浪费率，含形态学后处理去噪。

    浪费率定义：剩余食物像素面积 / 餐盘总像素面积 × 100。

    为什么分母用 (food + plate) 而不是 (plate)：
    U-Net 为 argmax 三分类(0背景/1餐盘/2食物)，一个像素只能归一类，
    而食物物理上盖在餐盘上，被食物覆盖的餐盘像素会被判为"食物"。
    因此 class1 只统计到"露出的餐盘"，若直接用 food/plate，
    食物越多分母越小，比值会被拉高甚至 >100%。
    完整餐盘 ≈ 剩余食物 + 露出餐盘，故用 (food_pixels + plate_pixels) 作分母，
    物理正确且天然 ≤ 100%。
    """
    # 1. 形态学后处理：对食物区域做开运算，去除酱汁/油渍产生的细碎噪声
    food_mask = (mask == 2).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    food_cleaned = cv2.morphologyEx(food_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # 2. 连通域过滤：去掉面积 < 100px 的孤立噪点
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(food_cleaned, connectivity=8)
    food_filtered = np.zeros_like(food_cleaned)
    min_area = 100
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            food_filtered[labels == i] = 1

    # 3. 统计像素数
    plate_mask = (mask == 1).astype(np.uint8)
    # 对餐盘也做一次开运算，去掉边缘毛刺
    plate_cleaned = cv2.morphologyEx(plate_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    plate_pixels = int(np.sum(plate_cleaned))
    food_pixels = int(np.sum(food_filtered))

    # 4. 浪费率 = 剩余食物面积 / 餐盘总面积 × 100（天然 ≤ 100%，无需经验系数修正）
    total_plate = food_pixels + plate_pixels
    if total_plate == 0:
        wastage_rate = 0.0
    else:
        wastage_rate = round((food_pixels / total_plate) * 100, 2)

    wastage_rate = max(wastage_rate, 0.0)
    return wastage_rate, plate_pixels, food_pixels


def extract_waste_cause_features(img_pil: Image.Image, original_bgr: np.ndarray,
                                 yolo_results, unet_mask: np.ndarray,
                                 wastage_rate: float, plate_pixels: int, food_pixels: int):
    """从YOLO+U-Net结果中提取结构化特征，供弃因模型使用"""
    h, w = original_bgr.shape[:2]
    b_mean, g_mean, r_mean = np.mean(original_bgr, axis=(0, 1))

    # YOLO特征
    detected_dishes = []
    dish_confidences = []
    bboxes = []
    for box in yolo_results[0].boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        dish_name = yolo_model.names[cls]
        detected_dishes.append(dish_name)
        dish_confidences.append(conf)
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        bboxes.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    n_det = len(detected_dishes)
    avg_conf = round(float(np.mean(dish_confidences)), 3) if dish_confidences else 0.0
    min_conf = round(float(np.min(dish_confidences)), 3) if dish_confidences else 0.0

    rice_kw = ["米饭", "米", "饭"]
    meat_kw = ["肉", "鸡", "鸭", "鱼", "虾", "猪", "牛", "蛋", "翅", "腿", "丸", "排"]
    veg_kw = ["菜", "茄", "豆", "菇", "瓜", "椒", "蔬", "笋", "菌", "粉"]

    has_rice = int(any(any(kw in d for kw in rice_kw) for d in detected_dishes))
    meat_cnt = sum(1 for d in detected_dishes if any(kw in d for kw in meat_kw))
    veg_cnt = sum(1 for d in detected_dishes if any(kw in d for kw in veg_kw))
    mvr = round(meat_cnt / max(veg_cnt, 1), 2)

    # Bbox空间特征
    if bboxes:
        areas = [(b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) for b in bboxes]
        cx = [(b["x1"] + b["x2"]) / 2 / w for b in bboxes]
        cy = [(b["y1"] + b["y2"]) / 2 / h for b in bboxes]
        aar = round(float(np.mean(areas)) / (w * h), 4)
        bos = round((float(np.std(cx)) + float(np.std(cy))) / 2, 4)
    else:
        aar, bos = 0.0, 0.0

    # U-Net特征
    food_mask = (unet_mask == 2).astype(np.uint8)
    plate_mask = (unet_mask == 1).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    food_cleaned = cv2.morphologyEx(food_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    oil_px = int(np.sum(food_cleaned)) - food_pixels
    oil_ratio = round(oil_px / max(food_pixels + plate_pixels, 1), 4)

    num_labels_food, _, _, _ = cv2.connectedComponentsWithStats(food_cleaned, connectivity=8)
    frag_cnt = num_labels_food - 1

    mid_h, mid_w = h // 2, w // 2
    total_food = max(int(np.sum(food_cleaned)), 1)
    ft = float(np.sum(food_cleaned[:mid_h, :])) / total_food
    fb = float(np.sum(food_cleaned[mid_h:, :])) / total_food
    fl = float(np.sum(food_cleaned[:, :mid_w])) / total_food
    fr = float(np.sum(food_cleaned[:, mid_w:])) / total_food

    # 上下左右四个方向占比（两两重叠、和约为2），非标准信息熵，仅作"食物空间离散度"度量。
    # 与训练脚本 extract_features.py 的 waste_spatial_entropy 计算保持数值一致。
    quad = np.array([ft, fb, fl, fr])
    quad = quad[quad > 0]
    ent = -float(np.sum(quad * np.log(quad + 1e-10)))

    # 弃因模型的输入特征：与训练集(extract_features.py 生成的 CSV)口径一致，
    # 均使用新公式 food/(food+plate)（重训时训练侧已同步改为新公式，训练/推理不再漂移）。
    raw_rate = (food_pixels / max(food_pixels + plate_pixels, 1)) * 100
    waste_capped = round(min(max(raw_rate, 0), 100), 2)
    waste_ratio_capped = round(min(food_pixels / max(food_pixels + plate_pixels, 1), 1.0), 4)
    if waste_capped < 5:
        wl_int = 0
    elif waste_capped < 20:
        wl_int = 1
    else:
        wl_int = 2

    return {
        "img_height": h, "img_width": w,
        "img_aspect_ratio": round(w / h, 3),
        "avg_b": round(float(b_mean), 1), "avg_g": round(float(g_mean), 1),
        "avg_r": round(float(r_mean), 1),
        "color_temp": round(float(r_mean - b_mean), 1),
        "detected_count": n_det,
        "avg_confidence": avg_conf, "min_confidence": min_conf,
        "has_rice": has_rice, "meat_dish_count": meat_cnt, "veg_dish_count": veg_cnt,
        "meat_veg_ratio": mvr,
        "avg_bbox_area_ratio": aar, "bbox_overlap_score": bos,
        "plate_pixels": plate_pixels, "food_pixels": food_pixels, "oil_pixels": oil_px,
        "oil_ratio": oil_ratio, "food_fragment_count": frag_cnt,
        "food_top_ratio": round(ft, 3), "food_bottom_ratio": round(fb, 3),
        "food_left_ratio": round(fl, 3), "food_right_ratio": round(fr, 3),
        "waste_spatial_entropy": round(ent, 3),
        "waste_rate_capped": waste_capped, "waste_ratio_capped": waste_ratio_capped,
        "waste_level_int": wl_int,
    }

# 系统清理函数
def get_config_value(config_key: str, default: int = 7) -> int:
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT config_value FROM system_config WHERE config_key = %s", (config_key,))
        res = cursor.fetchone()
        return int(res["config_value"]) if res else default
    except Exception as e:
        print(f"读取配置 {config_key} 失败: {e}")
        return default
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

def clean_expired_images():
    days = get_config_value("image_clean_days", 90)
    expire_time = time.time() - days * 86400
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files_dir = os.path.join(base_dir, "files")

    if not os.path.exists(files_dir):
        return 0

    count = 0
    for filename in os.listdir(files_dir):
        file_path = os.path.join(files_dir, filename)
        if os.path.isfile(file_path):
            if os.path.getmtime(file_path) < expire_time:
                os.remove(file_path)
                count += 1
    print(f"✅ 清理图片完成：删除 {count} 张 {days} 天前的图片")
    return count

def clean_expired_records():
    days = get_config_value("records_clean_days", 30)
    expire_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_mysql_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE di FROM detection_items di
            JOIN detection_records dr ON di.record_id = dr.id
            WHERE dr.create_time < %s
        """, (expire_date,))
        items_deleted = cursor.rowcount

        cursor.execute("""
            DELETE FROM detection_records
            WHERE create_time < %s
        """, (expire_date,))
        records_deleted = cursor.rowcount

        conn.commit()
        print(f"✅ 清理记录完成：删除 {records_deleted} 条记录，{items_deleted} 条明细（保留 {days} 天）")
        return records_deleted, items_deleted
    except Exception as e:
        conn.rollback()
        print(f"❌ 清理记录失败: {e}")
        return 0, 0
    finally:
        cursor.close()
        conn.close()

def clean_expired_summary_records():
    days = get_config_value("summary_keep_days", 90)
    expire_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_mysql_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM summary_records
            WHERE create_time < %s
        """, (expire_date,))
        summary_deleted = cursor.rowcount
        conn.commit()
        print(f"✅ 清理汇总记录完成：删除 {summary_deleted} 条（保留 {days} 天）")
        return summary_deleted
    except Exception as e:
        if "Table 'canteen_waste_monitor.summary_records' doesn't exist" not in str(e):
            print(f"❌ 清理汇总记录失败: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()

def auto_clean_task():
    while True:
        clean_expired_images()
        clean_expired_records()
        clean_expired_summary_records()
        time.sleep(86400)

# 辅助函数
def draw_custom_boxes(img: np.ndarray, results) -> np.ndarray:
    # OpenCV 批量画矩形框（释放 GIL），PIL 批量画中文标签（一次转换）
    img_bgr = img.copy()
    label_infos = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cls = int(box.cls[0])
        conf = round(float(box.conf[0]) * 100, 2)
        label = f"{yolo_model.names[cls]}({conf}%)"

        cv2.rectangle(img_bgr, (x1, y1), (x2, y2), (0, 0, 255), 3)
        b = _FONT_CACHE.getbbox(label)
        lw, lh = b[2] - b[0], b[3] - b[1]
        ly = y1 - lh - 5 if y1 > lh + 5 else y1 + 5
        cv2.rectangle(img_bgr, (x1, ly), (x1 + lw + 8, ly + lh + 4), (0, 0, 255), -1)
        label_infos.append((label, x1 + 4, ly + 2))

    if label_infos:
        img_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        for label, lx, ly in label_infos:
            draw.text((lx, ly), label, font=_FONT_CACHE, fill=(255, 255, 255))
        img_bgr = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    return img_bgr

def mask_to_visual(mask: np.ndarray, original_img: np.ndarray) -> np.ndarray:
    visual_mask = np.zeros_like(original_img, dtype=np.uint8)
    visual_mask[mask == 1] = (200, 220, 255)
    visual_mask[mask == 2] = (0, 0, 255)
    return cv2.addWeighted(original_img, 0.3, visual_mask, 0.7, 0)

def preprocess_image(image: Image.Image) -> np.ndarray:
    img = np.array(image)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    b, g, r = cv2.split(img)
    b_avg, g_avg, r_avg = np.mean(b), np.mean(g), np.mean(r)
    gray_avg = (b_avg + g_avg + r_avg) / 3
    b = np.clip(b * (gray_avg / (b_avg + 1e-6)), 0, 255).astype(np.uint8)
    g = np.clip(g * (gray_avg / (g_avg + 1e-6)), 0, 255).astype(np.uint8)
    r = np.clip(r * (gray_avg / (r_avg + 1e-6)), 0, 255).astype(np.uint8)
    img = cv2.merge((b, g, r))
    h, w = img.shape[:2]
    scale = min(DETECT_PARAMS["imgsz"] / w, DETECT_PARAMS["imgsz"] / h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    pad_x = (DETECT_PARAMS["imgsz"] - new_w) // 2
    pad_y = (DETECT_PARAMS["imgsz"] - new_h) // 2
    return cv2.copyMakeBorder(img, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=(0, 0, 0))

# 统计函数
def get_trend_statistics(time_dim, where_sql, params):
    conn = get_mysql_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    labels = []
    wasteRates = []

    try:
        if time_dim == "day":
            if params and len(params) >= 2:
                start_date = datetime.strptime(params[0], "%Y-%m-%d %H:%M:%S")
                end_date = datetime.strptime(params[1], "%Y-%m-%d %H:%M:%S")
            else:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=6)

            current = start_date
            while current <= end_date:
                label = current.strftime("%m.%d")
                labels.append(label)
                date_str = current.strftime("%Y-%m-%d")

                query_where = f"WHERE DATE(create_time) = %s"
                if where_sql.replace("WHERE ", ""):
                    query_where += f" AND {where_sql.replace('WHERE ', '')}"

                sql = f"""
                    SELECT AVG(wastage_rate) avg_rate
                    FROM detection_records
                    {query_where}
                """
                cursor.execute(sql, [date_str] + params)
                row = cursor.fetchone()
                avg = row.get("avg_rate", 0) or 0
                wasteRates.append(round(float(avg), 1))
                current += timedelta(days=1)

        elif time_dim == "week":
            today = datetime.now()
            for i in range(4):
                days_to_monday = today.weekday()
                week_start = today - timedelta(days=days_to_monday + 7 * i)
                week_end = week_start + timedelta(days=6)

                year_week = week_start.isocalendar()[1]
                year = week_start.year
                labels.insert(0, f"{year}年第{year_week}周")

                query_where = "WHERE 1=1"
                if where_sql.replace("WHERE ", ""):
                    query_where += f" AND {where_sql.replace('WHERE ', '')}"

                sql = f"""
                    SELECT AVG(wastage_rate) avg_rate
                    FROM detection_records
                    {query_where}
                    AND create_time BETWEEN %s AND %s
                """
                week_start_str = week_start.strftime("%Y-%m-%d 00:00:00")
                week_end_str = week_end.strftime("%Y-%m-%d 23:59:59")
                cursor.execute(sql, params + [week_start_str, week_end_str])
                row = cursor.fetchone()
                avg = row.get("avg_rate", 0) or 0
                wasteRates.insert(0, round(float(avg), 1))

        elif time_dim == "month":
            today = datetime.now()
            for i in range(6):
                month = today.month - i
                year = today.year
                while month <= 0:
                    month += 12
                    year -= 1

                labels.insert(0, f"{year}年{month}月")

                query_where = "WHERE 1=1"
                if where_sql.replace("WHERE ", ""):
                    query_where += f" AND {where_sql.replace('WHERE ', '')}"

                sql = f"""
                    SELECT AVG(wastage_rate) avg_rate
                    FROM detection_records
                    {query_where}
                    AND YEAR(create_time) = %s AND MONTH(create_time) = %s
                """
                cursor.execute(sql, params + [year, month])
                row = cursor.fetchone()
                avg = row.get("avg_rate", 0) or 0
                wasteRates.insert(0, round(float(avg), 1))

    finally:
        cursor.close()
        conn.close()

    return {"labels": labels, "wasteRates": wasteRates}

def get_food_statistics(where_sql, params):
    conn = get_mysql_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    food_counts = {}
    total = 0

    try:
        join_sql = ""
        if where_sql:
            join_sql = f"JOIN detection_records dr ON di.record_id = dr.id {where_sql.replace('create_time', 'dr.create_time')}"

        sql = f"""
            SELECT di.food_name, COUNT(*) cnt
            FROM detection_items di
            {join_sql}
            GROUP BY di.food_name
            ORDER BY cnt DESC
        """
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        for row in rows:
            food_counts[row["food_name"]] = row["cnt"]
            total += row["cnt"]

        labels = []
        values = []
        other = 0
        for i, (k, v) in enumerate(food_counts.items()):
            if i < 5:
                labels.append(k)
                values.append(round((v / total) * 100) if total else 0)
            else:
                other += v
        if other > 0:
            labels.append("其他")
            values.append(round((other / total) * 100) if total else 0)
        if not labels:
            labels = ["暂无数据"]
            values = [100]

    finally:
        cursor.close()
        conn.close()

    return {"labels": labels, "values": values}

def get_upload_statistics(where_sql, params):
    conn = get_mysql_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    data = {"single": 0, "batch": 0, "camera": 0}

    try:
        sql = f"""
            SELECT record_type, COUNT(*) cnt
            FROM detection_records
            {where_sql}
            GROUP BY record_type
        """
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        for r in rows:
            if r["record_type"] == "single":
                data["single"] = r["cnt"]
            elif r["record_type"] == "batch":
                data["batch"] = r["cnt"]
            elif r["record_type"] == "camera":
                data["camera"] = r["cnt"]
        if sum(data.values()) == 0:
            data = {"single": 1, "batch": 1, "camera": 1}

    finally:
        cursor.close()
        conn.close()

    return {
        "labels": ["单张上传", "批量上传", "摄像头抓拍"],
        "counts": [data["single"], data["batch"], data["camera"]]
    }

# 检测逻辑
def process_single_file(file: UploadFile):
    try:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        FILES_DIR = os.path.join(BASE_DIR, "files")
        os.makedirs(FILES_DIR, exist_ok=True)

        file_size = file.size if file.size is not None else 0
        if file_size > SINGLE_FILE_LIMIT:
            raise HTTPException(status_code=400, detail=f"文件 {file.filename} 超过15MB限制")

        file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if file_ext not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"文件 {file.filename} 格式不支持")

        contents = file.file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail=f"文件 {file.filename} 为空")

        start_time = time.time()
        img = Image.open(io.BytesIO(contents)).convert("RGB")
        original_img = np.array(img)
        original_img_bgr = cv2.cvtColor(original_img, cv2.COLOR_RGB2BGR)
        processed_img = preprocess_image(img)

        yolo_results = yolo_infer(processed_img)
        detections = []
        items_data = []

        for box in yolo_results[0].boxes:
            cls = int(box.cls[0])
            conf = round(float(box.conf[0]), 3)
            dish_name = yolo_model.names[cls]

            detections.append({"class_name": dish_name, "confidence": conf})
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            items_data.append({
                "food_name": dish_name,
                "confidence": round(conf * 100, 1),
                "bbox_x1": int(x1),
                "bbox_y1": int(y1),
                "bbox_x2": int(x2),
                "bbox_y2": int(y2)
            })

        result_img = draw_custom_boxes(processed_img, yolo_results)
        result_img = cv2.resize(result_img, (original_img.shape[1], original_img.shape[0]), interpolation=cv2.INTER_LANCZOS4)

        unet_mask = unet_infer(img)
        original_h, original_w = original_img.shape[:2]
        unet_mask = cv2.resize(unet_mask, (original_w, original_h), interpolation=cv2.INTER_NEAREST)

        wastage_rate, plate_pixels, food_pixels = calculate_wastage_rate(unet_mask)

        cause_features = extract_waste_cause_features(
            img, original_img_bgr, yolo_results, unet_mask,
            wastage_rate, plate_pixels, food_pixels)
        cause_result = predict_with_rules(cause_features, img)

        mask_img = mask_to_visual(unet_mask, original_img_bgr)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename_unique = f"{timestamp}_{os.urandom(4).hex()}.jpg"

        ori_save_path = os.path.join(FILES_DIR, f"original_{filename_unique}")
        res_save_path = os.path.join(FILES_DIR, f"result_{filename_unique}")
        mask_save_path = os.path.join(FILES_DIR, f"mask_{filename_unique}")

        cv2.imwrite(ori_save_path, original_img_bgr)
        cv2.imwrite(res_save_path, result_img)
        cv2.imwrite(mask_save_path, mask_img)

        original_url = f"{BASE_URL}/files/original_{filename_unique}"
        result_url = f"{BASE_URL}/files/result_{filename_unique}"
        mask_url = f"{BASE_URL}/files/mask_{filename_unique}"

        status = "正常" if wastage_rate < 5 else "轻微损耗" if wastage_rate < 20 else "严重损耗"
        detect_time = round(time.time() - start_time, 2)

        result_data = {
            "filename": file.filename,
            "file_name": file.filename,
            "file_size": file_size,
            "original_image_url": original_url,
            "result_image_url": result_url,
            "mask_image_url": mask_url,
            "detections": detections,
            "detection_count": len(detections),
            "wastage_rate": wastage_rate,
            "status": status,
            "detect_time": detect_time,
            "detect_time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_food_area": food_pixels + plate_pixels,
            "waste_food_area": food_pixels,
            "waste_cause": cause_result["cause"],
            "waste_cause_confidence": cause_result["confidence"],
        }

        logger.info(f"✅ 检测成功：{file.filename}，浪费率：{wastage_rate}%，菜品：{[d['class_name'] for d in detections]}")
        return result_data, items_data
    except Exception as e:
        logger.error(f"检测失败 {file.filename}：{str(e)}", exc_info=True)
        return {"filename": file.filename, "error": str(e), "success": False}, []

def batch_save_records(records_with_items):
    """批量保存检测记录（单事务），减少连接开销"""
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()
        for result, items_data in records_with_items:
            if result.get("error"):
                continue
            cursor.execute(
                """INSERT INTO detection_records (record_type, file_name, file_size,
                   original_image_url, result_image_url, mask_image_url,
                   wastage_rate, status, error_msg, waste_cause, waste_cause_confidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (result.get('record_type'), result.get('file_name'), result.get('file_size'),
                 result.get('original_image_url'), result.get('result_image_url'), result.get('mask_image_url'),
                 result.get('wastage_rate'), result.get('status', 'success'), result.get('error_msg', ''),
                 result.get('waste_cause'), result.get('waste_cause_confidence'))
            )
            record_id = cursor.lastrowid
            if items_data and record_id:
                cursor.executemany(
                    """INSERT INTO detection_items (record_id, food_name, confidence,
                       bbox_x1, bbox_y1, bbox_x2, bbox_y2)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    [(record_id, it.get('food_name'), it.get('confidence'),
                      it.get('bbox_x1'), it.get('bbox_y1'), it.get('bbox_x2'), it.get('bbox_y2'))
                     for it in items_data]
                )
        conn.commit()
        logger.info(f"✅ 批量保存 {len(records_with_items)} 条记录成功")
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"批量保存失败: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_detection_record(record_data, items_data):
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor()

        record_sql = """
            INSERT INTO detection_records (record_type, file_name, file_size,
                                           original_image_url, result_image_url, mask_image_url,
                                           wastage_rate, status, error_msg, waste_cause, waste_cause_confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        record_values = (
            record_data.get('record_type'),
            record_data.get('file_name'),
            record_data.get('file_size'),
            record_data.get('original_image_url'),
            record_data.get('result_image_url'),
            record_data.get('mask_image_url'),
            record_data.get('wastage_rate'),
            record_data.get('status', 'success'),
            record_data.get('error_msg', ''),
            record_data.get('waste_cause'),
            record_data.get('waste_cause_confidence')
        )
        cursor.execute(record_sql, record_values)
        record_id = cursor.lastrowid

        if items_data and record_id:
            items_sql = """
                INSERT INTO detection_items (record_id, food_name, confidence,
                                             bbox_x1, bbox_y1, bbox_x2, bbox_y2)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            items_values = [
                (record_id, item.get('food_name'), item.get('confidence'),
                 item.get('bbox_x1'), item.get('bbox_y1'), item.get('bbox_x2'), item.get('bbox_y2'))
                for item in items_data
            ]
            cursor.executemany(items_sql, items_values)

        conn.commit()
        return {"success": True, "record_id": record_id}
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"保存记录失败：{e}")
        return {"success": False, "error": str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ====================== 全局AI分析接口（核心优化：先汇总再调用AI） ======================
# ========== 核心接口 ==========
@app.get("/")
async def index():
    index_path = "static/index.html"
    return FileResponse(index_path) if os.path.exists(index_path) else {"message": "服务运行中"}

# 配置接口
@app.get("/api/configs")
def get_all_configs():
    conn = get_mysql_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT config_key, config_value FROM system_config")
        rows = cursor.fetchall()

        default_configs = {
            "daily_summary_hour": "2",
            "daily_summary_minute": "0",
            "image_clean_days": "90",
            "records_clean_days": "30",
            "summary_keep_days": "90"
        }

        for row in rows:
            default_configs[row["config_key"]] = row["config_value"]

        return default_configs
    finally:
        cursor.close()
        conn.close()

@app.post("/api/configs")
def update_all_configs(
        image_clean_days: int = Query(..., ge=1, le=365),
        records_clean_days: int = Query(..., ge=1, le=365),
        daily_summary_hour: int = Query(2, ge=0, le=23),
        daily_summary_minute: int = Query(0, ge=0, le=59),
        summary_keep_days: int = Query(90, ge=1, le=3650)
):
    conn = get_mysql_connection()
    cursor = conn.cursor()
    try:
        configs = [
            ("image_clean_days", str(image_clean_days)),
            ("records_clean_days", str(records_clean_days)),
            ("daily_summary_hour", str(daily_summary_hour)),
            ("daily_summary_minute", str(daily_summary_minute)),
            ("summary_keep_days", str(summary_keep_days))
        ]

        for key, value in configs:
            cursor.execute("""
                INSERT INTO system_config (config_key, config_value, name)
                VALUES (%s, %s, %s) ON DUPLICATE KEY
                UPDATE config_value = %s
            """, (key, value, key.replace("_", " ").title(), value))

        conn.commit()
        return {"success": True, "msg": "保存成功"}
    except Exception as e:
        conn.rollback()
        return {"success": False, "msg": f"保存失败：{str(e)}"}
    finally:
        cursor.close()
        conn.close()

# 检测接口
@app.post("/predict")
async def predict(file: UploadFile = File(...), record_type: str = Form("single")):
    try:
        result_data, items_data = process_single_file(file)
        if "error" in result_data:
            raise HTTPException(status_code=500, detail=result_data["error"])
        result_data['record_type'] = record_type
        save_detection_record(result_data, items_data)
        return {"success": True, "data": [result_data], "message": "检测成功"}
    except HTTPException as e:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检测失败：{str(e)}")

@app.post("/batch_predict")
async def batch_predict(files: List[UploadFile] = File(...)):
    all_results = []
    batch_id = str(uuid.uuid4())

    total_size = sum([file.size or 0 for file in files])
    if total_size > TOTAL_FILE_LIMIT:
        raise HTTPException(status_code=400, detail=f"总文件大小超过100MB限制")

    # 单文件预校验（不读内容，只校验大小与格式）
    for file in files:
        file_size = file.size if file.size is not None else 0
        if file_size > SINGLE_FILE_LIMIT:
            raise HTTPException(status_code=400, detail=f"文件 {file.filename} 超过15MB限制")
        file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""
        if file_ext not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"文件 {file.filename} 格式不支持")

    t_start = time.time()
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    FILES_DIR = os.path.join(BASE_DIR, "files")
    os.makedirs(FILES_DIR, exist_ok=True)

    # 内部分批大小：避免一次处理过多大图导致内存峰值过高（本机 16GB RAM 硬约束，
    # 每张大图约 48MB、预处理时同时持有原图/PIL图/推理图三份；4 张一批峰值约 400MB，安全且批次更少更快）
    SUB_BATCH_SIZE = 4

    def process_sub_batch(sub_files):
        """处理一个子批，返回 (results, items_data) 两个列表"""
        # 1. 预读 + 预处理本子批
        preprocessed_list = []
        for file in sub_files:
            contents = file.file.read()
            if len(contents) == 0:
                raise HTTPException(status_code=400, detail=f"文件 {file.filename} 为空")
            img = Image.open(io.BytesIO(contents)).convert("RGB")
            original_bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            yolo_input = preprocess_image(img)
            preprocessed_list.append((file.filename, original_bgr, img, yolo_input, file.size or 0))

        # 2. YOLO 批量推理
        all_yolo_inputs = [item[3] for item in preprocessed_list]
        all_yolo_results = yolo_model(all_yolo_inputs, **DETECT_PARAMS, verbose=False)
        for i, r in enumerate(all_yolo_results, start=1):
            if r.boxes:
                names = [yolo_model.names[int(c)] for c in r.boxes.cls]
                logger.info(f"  {i:2d}: 检测到 {', '.join(names)}")
            else:
                logger.info(f"  {i:2d}: (无检测)")

        # 3. U-Net 批量推理
        unet_model = load_unet_model()
        unet_batch = torch.stack([UNET_PREPROCESS(item[2]) for item in preprocessed_list]).to(TORCH_DEVICE)
        with torch.no_grad():
            unet_outputs = unet_model(unet_batch)
        unet_masks = torch.argmax(unet_outputs, dim=1).cpu().numpy()  # (N, 256, 256)

        # 4. 后处理 + 并行保存图片（纯 I/O，线程安全）
        def postprocess_and_save(idx):
            filename, original_bgr, pil_img, _, file_size = preprocessed_list[idx]
            h, w = original_bgr.shape[:2]

            yolo_result = all_yolo_results[idx]
            detections = []
            items_data = []
            for box in yolo_result.boxes:
                cls = int(box.cls[0])
                conf = round(float(box.conf[0]), 3)
                dish_name = yolo_model.names[cls]
                detections.append({"class_name": dish_name, "confidence": conf})
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                items_data.append({
                    "food_name": dish_name, "confidence": round(conf * 100, 1),
                    "bbox_x1": int(x1), "bbox_y1": int(y1),
                    "bbox_x2": int(x2), "bbox_y2": int(y2)
                })

            result_img = draw_custom_boxes(preprocessed_list[idx][3], [yolo_result])
            result_img = cv2.resize(result_img, (w, h), interpolation=cv2.INTER_LANCZOS4)

            mask_resized = cv2.resize(unet_masks[idx], (w, h), interpolation=cv2.INTER_NEAREST)
            wastage_rate, plate_pixels, food_pixels = calculate_wastage_rate(mask_resized)
            mask_vis = mask_to_visual(mask_resized, original_bgr)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            uid = os.urandom(4).hex()
            cv2.imwrite(os.path.join(FILES_DIR, f"original_{timestamp}_{uid}.jpg"), original_bgr)
            cv2.imwrite(os.path.join(FILES_DIR, f"result_{timestamp}_{uid}.jpg"), result_img)
            cv2.imwrite(os.path.join(FILES_DIR, f"mask_{timestamp}_{uid}.jpg"), mask_vis)

            status = "正常" if wastage_rate < 5 else "轻微损耗" if wastage_rate < 20 else "严重损耗"

            cause_features = extract_waste_cause_features(
                pil_img, original_bgr, yolo_result, mask_resized,
                wastage_rate, plate_pixels, food_pixels)
            cause_result = predict_with_rules(cause_features, pil_img)

            return {
                "filename": filename, "file_name": filename, "file_size": file_size,
                "original_image_url": f"{BASE_URL}/files/original_{timestamp}_{uid}.jpg",
                "result_image_url": f"{BASE_URL}/files/result_{timestamp}_{uid}.jpg",
                "mask_image_url": f"{BASE_URL}/files/mask_{timestamp}_{uid}.jpg",
                "detections": detections, "detection_count": len(detections),
                "wastage_rate": wastage_rate, "status": status,
                "detect_time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_food_area": food_pixels + plate_pixels, "waste_food_area": food_pixels,
                "record_type": "batch",
                "waste_cause": cause_result["cause"],
                "waste_cause_confidence": cause_result["confidence"],
            }, items_data

        sub_results = []
        sub_items = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(postprocess_and_save, i) for i in range(len(preprocessed_list))]
            for future in as_completed(futures):
                result, items_data = future.result()
                sub_results.append(result)
                sub_items.append((result, items_data))
        return sub_results, sub_items

    # 分批处理，逐批释放内存（gc.collect 强制回收本批的大图内存）
    all_items = []
    for i in range(0, len(files), SUB_BATCH_SIZE):
        sub_files = files[i:i + SUB_BATCH_SIZE]
        sub_results, sub_items = process_sub_batch(sub_files)
        all_results.extend(sub_results)
        all_items.extend(sub_items)
        gc.collect()

    if all_items:
        batch_save_records(all_items)

    total_time = round(time.time() - t_start, 2)
    logger.info(f"批量检测 {len(files)} 张完成，总耗时 {total_time}s")
    return {
        "success": True, "batch_id": batch_id,
        "total_count": len(all_results),
        "success_count": len([r for r in all_results if "error" not in r]),
        "fail_count": len([r for r in all_results if "error" in r]),
        "records": all_results,
        "message": f"批量检测完成，共{len(all_results)}个文件，耗时{total_time}s"
    }

# 记录查询
@app.get("/batch_results")
def get_detection_records(
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=20),
        record_type: Optional[str] = None,
        food_name: Optional[str] = None,
        waste_min: Optional[int] = None,
        waste_max: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        batch_id: Optional[str] = None
):
    conn = None
    cursor = None
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        where_conditions = []
        params = []

        if record_type and record_type.strip():
            where_conditions.append("dr.record_type = %s")
            params.append(record_type.strip())

        if food_name and food_name.strip():
            where_conditions.append("""
                EXISTS (
                    SELECT 1 FROM detection_items di
                    WHERE di.record_id = dr.id
                    AND di.food_name LIKE %s
                )
            """)
            params.append(f"%{food_name.strip()}%")

        if waste_min is not None:
            where_conditions.append("dr.wastage_rate >= %s")
            params.append(waste_min)
        if waste_max is not None:
            where_conditions.append("dr.wastage_rate <= %s")
            params.append(waste_max)

        if start_time and start_time.strip():
            where_conditions.append("dr.create_time >= %s")
            params.append(start_time.strip())
        if end_time and end_time.strip():
            where_conditions.append("dr.create_time <= %s")
            params.append(end_time.strip())

        where_sql = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

        count_sql = f"SELECT COUNT(*) as total FROM detection_records dr {where_sql}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()["total"] or 0

        offset = (page - 1) * page_size

        query_sql = f"""
            SELECT dr.* FROM detection_records dr
            {where_sql}
            ORDER BY dr.create_time DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        cursor.execute(query_sql, params)
        records = cursor.fetchall()

        # 一次性查出所有记录的 items，避免 N+1 查询
        items_map = {}
        if records:
            ids = [r["id"] for r in records]
            placeholders = ",".join(["%s"] * len(ids))
            cursor.execute(f"SELECT * FROM detection_items WHERE record_id IN ({placeholders})", ids)
            for item in cursor.fetchall():
                items_map.setdefault(item["record_id"], []).append(item)

        for record in records:
            record["original_image_url"] = rewrite_image_url(record.get("original_image_url"))
            record["result_image_url"] = rewrite_image_url(record.get("result_image_url"))
            record["mask_image_url"] = rewrite_image_url(record.get("mask_image_url"))
            record["items"] = items_map.get(record["id"], [])

        return {
            "success": True,
            "data": {
                "records": records,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
                    "has_prev": page > 1,
                    "has_next": page < ((total + page_size - 1) // page_size if total > 0 else 0)
                }
            }
        }
    except Exception as e:
        print(f"查询记录失败：{e}")
        return {"success": False, "error": str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# 统计接口
@app.get("/api/statistics")
def get_statistics(
        type: str = Query(..., enum=["trend", "food", "upload"]),
        time_dim: str = Query("day", enum=["day", "week", "month"]),
        start_time: str = None,
        end_time: str = None
):
    if time_dim in ["week", "month"]:
        start_time = None
        end_time = None

    conn = get_mysql_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    try:
        where_conditions = []
        params = []

        if start_time and start_time.strip():
            where_conditions.append("create_time >= %s")
            params.append(start_time.strip())
        if end_time and end_time.strip():
            where_conditions.append("create_time <= %s")
            params.append(end_time.strip())

        where_sql = ""
        if where_conditions:
            where_sql = "WHERE " + " AND ".join(where_conditions)

        if type == "trend":
            return get_trend_statistics(time_dim, where_sql, params.copy())
        elif type == "food":
            return get_food_statistics(where_sql, params.copy())
        elif type == "upload":
            return get_upload_statistics(where_sql, params.copy())

        return {"labels": [], "wasteRates": []}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/overview")
def get_overview_statistics(start_time=None, end_time=None):
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        where_conditions = []
        params = []

        if start_time and start_time.strip():
            where_conditions.append("create_time >= %s")
            params.append(start_time.strip())
        if end_time and end_time.strip():
            where_conditions.append("create_time <= %s")
            params.append(end_time.strip())

        where_sql = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        base_cond = "wastage_rate IS NOT NULL"
        if where_sql:
            where_sql += f" AND {base_cond}"
        else:
            where_sql = f"WHERE {base_cond}"

        cursor.execute(f"SELECT COUNT(*) AS total FROM detection_records {where_sql}", params)
        totalCount = cursor.fetchone()["total"] or 0

        cursor.execute(f"SELECT AVG(wastage_rate) avg_rate FROM detection_records {where_sql}", params)
        avgWasteRate = round(float(cursor.fetchone()["avg_rate"] or 0), 1)

        cursor.execute(f"SELECT COUNT(*) high_count FROM detection_records {where_sql} AND wastage_rate > 50", params)
        highWasteCount = cursor.fetchone()["high_count"] or 0

        cursor.execute(f"SELECT COUNT(*) success FROM detection_records {where_sql}", params)
        success = cursor.fetchone()["success"] or 0
        successRate = round((success / totalCount) * 100, 1) if totalCount > 0 else 0

        return {
            "totalCount": totalCount,
            "avgWasteRate": avgWasteRate,
            "highWasteCount": highWasteCount,
            "successRate": successRate
        }
    except Exception as e:
        print(f"总览统计错误: {e}")
        return {"totalCount": 0, "avgWasteRate": 0, "highWasteCount": 0, "successRate": 0}
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.get("/api/analysis/summary")
def get_analysis_summary(
    start_time: str = None,
    end_time: str = None,
    time_dim: str = Query("day", enum=["day", "week", "month"]),
    top_n: int = Query(5, ge=1, le=20)
):
    """聚合分析接口：供 Coze 插件/智能体调用，返回结构化 JSON 供大模型组织自然语言。

    返回字段语义清晰、带单位(_pct 表示百分比)，方便 LLM 理解：
    - overview: 总检测次数 / 平均剩余占比(%) / 高浪费条数(>50%) / 成功率(%)
    - top_wasted_foods: 按"出现频繁 × 浪费率高"综合严重度排序的菜品
    - trend: 按时间维度的平均剩余占比(%)趋势
    - waste_level_distribution: 浪费等级分布(正常<5% / 轻微5-20% / 严重≥20%)
    """
    # week/month 维度忽略起止时间（与前端统计逻辑一致）
    if time_dim in ["week", "month"]:
        start_time = None
        end_time = None

    # 时间过滤条件（单表 detection_records 无别名）
    where_conditions = []
    params = []
    if start_time and start_time.strip():
        where_conditions.append("create_time >= %s")
        params.append(start_time.strip())
    if end_time and end_time.strip():
        where_conditions.append("create_time <= %s")
        params.append(end_time.strip())
    where_sql = ("WHERE " + " AND ".join(where_conditions)) if where_conditions else ""

    conn = get_mysql_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        # 1. 总览（复用现有函数，统一字段名/单位）
        ov = get_overview_statistics(start_time, end_time)
        overview = {
            "total_records": ov.get("totalCount", 0),
            "avg_waste_rate_pct": ov.get("avgWasteRate", 0),
            "high_waste_count": ov.get("highWasteCount", 0),
            "success_rate_pct": ov.get("successRate", 0),
        }

        # 2. 趋势（复用现有函数）
        trend = get_trend_statistics(time_dim, where_sql, params.copy())

        # 3. 菜品浪费排行：出现次数 × 平均浪费率 加权（JOIN 用 dr 别名）
        join_sql = "JOIN detection_records dr ON di.record_id = dr.id"
        if where_sql:
            join_sql += " " + where_sql.replace("create_time", "dr.create_time")
        cursor.execute(f"""
            SELECT di.food_name,
                   COUNT(*) AS appear_count,
                   ROUND(AVG(dr.wastage_rate), 1) AS avg_waste_rate
            FROM detection_items di
            {join_sql}
            GROUP BY di.food_name
            ORDER BY (COUNT(*) * AVG(dr.wastage_rate)) DESC
            LIMIT %s
        """, params + [top_n])
        top_foods = [
            {
                "food_name": row["food_name"],
                "appear_count": int(row["appear_count"]),
                "avg_waste_rate_pct": float(row["avg_waste_rate"] or 0),
            }
            for row in cursor.fetchall()
        ]

        # 4. 浪费等级分布
        cursor.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN wastage_rate < 5 THEN 1 ELSE 0 END), 0) AS normal,
                COALESCE(SUM(CASE WHEN wastage_rate >= 5 AND wastage_rate < 20 THEN 1 ELSE 0 END), 0) AS mild,
                COALESCE(SUM(CASE WHEN wastage_rate >= 20 THEN 1 ELSE 0 END), 0) AS severe
            FROM detection_records
            {where_sql}
        """, params)
        lv = cursor.fetchone()
        level_distribution = {
            "normal": int(lv["normal"] or 0),
            "mild": int(lv["mild"] or 0),
            "severe": int(lv["severe"] or 0),
        }

        # 5. 弃因分布
        cause_where = (where_sql + " AND " if where_sql else "WHERE ") + "waste_cause IS NOT NULL AND waste_cause != ''"
        cursor.execute(f"""
            SELECT waste_cause, COUNT(*) AS cnt
            FROM detection_records
            {cause_where}
            GROUP BY waste_cause
            ORDER BY cnt DESC
        """, params)
        waste_cause_distribution = [
            {"cause": row["waste_cause"], "count": int(row["cnt"])}
            for row in cursor.fetchall()
        ]

        return {
            "success": True,
            "time_range": {"dimension": time_dim, "start_time": start_time, "end_time": end_time},
            "overview": overview,
            "top_wasted_foods": top_foods,
            "trend": trend,
            "waste_level_distribution": level_distribution,
            "waste_cause_distribution": waste_cause_distribution,
        }
    except Exception as e:
        logger.error(f"聚合分析接口错误: {e}")
        return {"success": False, "detail": f"聚合分析失败: {e}"}
    finally:
        cursor.close()
        conn.close()


@app.get("/api/analysis/summary_pair")
def get_analysis_summary_pair(time_dim: str = Query("day", enum=["day", "week", "month"])):
    """本期+上期聚合（供 ADP 大模型生成月/周/日环比报告）。
    current / previous 均复用 get_analysis_summary，保证含 waste_level_distribution。"""
    today = datetime.now().date()
    if time_dim == "day":
        cur_start = today.strftime("%Y-%m-%d 00:00:00")
        cur_end = today.strftime("%Y-%m-%d 23:59:59")
        yest = today - timedelta(days=1)
        prev_start = yest.strftime("%Y-%m-%d 00:00:00")
        prev_end = yest.strftime("%Y-%m-%d 23:59:59")
        current = get_analysis_summary(start_time=cur_start, end_time=cur_end, time_dim="day")
        previous = get_analysis_summary(start_time=prev_start, end_time=prev_end, time_dim="day")
    elif time_dim == "week":
        current = get_analysis_summary(time_dim="week")
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        last_sunday = this_monday - timedelta(days=1)
        previous = get_analysis_summary(
            start_time=last_monday.strftime("%Y-%m-%d 00:00:00"),
            end_time=last_sunday.strftime("%Y-%m-%d 23:59:59"),
            time_dim="day")
    else:  # month
        current = get_analysis_summary(time_dim="month")
        first_this = today.replace(day=1)
        last_last = first_this - timedelta(days=1)
        first_last = last_last.replace(day=1)
        previous = get_analysis_summary(
            start_time=first_last.strftime("%Y-%m-%d 00:00:00"),
            end_time=last_last.strftime("%Y-%m-%d 23:59:59"),
            time_dim="day")
    return {"success": True, "time_dim": time_dim, "current": current, "previous": previous}


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "服务运行正常"}


# ========== AI 助手（Coze 智能体代理） ==========
class CozeChatRequest(BaseModel):
    message: str
    user_id: str = "guest"


def _coze_request(method: str, path: str, body: dict = None) -> dict:
    """调用 Coze API，返回 JSON dict。method: GET/POST"""
    url = COZE_API_BASE + path
    headers = {
        "Authorization": f"Bearer {COZE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


@app.post("/api/ai/chat")
def ai_chat(req: CozeChatRequest):
    """前端 AI 助手对话接口：转发到 Coze 智能体（挂餐食浪费分析插件），返回智能体回复"""
    if not COZE_BOT_ID or not COZE_API_TOKEN:
        raise HTTPException(status_code=500, detail="Coze 未配置：请设置 COZE_BOT_ID 和 COZE_API_TOKEN 环境变量")

    try:
        # 1. 发起对话（非流式）
        chat_resp = _coze_request("POST", "/v3/chat", {
            "bot_id": COZE_BOT_ID,
            "user_id": req.user_id,
            "stream": False,
            "auto_save_history": True,
            "additional_messages": [{"role": "user", "content": req.message, "content_type": "text"}],
        })
        data = chat_resp.get("data") or {}
        chat_id = data.get("id")
        conversation_id = data.get("conversation_id")
        if not chat_id or not conversation_id:
            raise HTTPException(status_code=500, detail=f"Coze 调用失败：{chat_resp}")

        # 2. 轮询状态直到终态（最多约 60 秒，插件调后端链路较慢）
        status = data.get("status", "")
        for _ in range(60):
            if status in ("completed", "failed", "canceled", "requires_action"):
                break
            time.sleep(1)
            st_resp = _coze_request("GET", f"/v3/chat/retrieve?conversation_id={conversation_id}&chat_id={chat_id}")
            status = (st_resp.get("data") or {}).get("status", "")

        if status != "completed":
            raise HTTPException(status_code=500, detail=f"Coze 对话未完成：status={status}")

        # 3. 取回复内容（type=answer 的消息）
        msg_resp = _coze_request("GET", f"/v3/chat/message/list?conversation_id={conversation_id}&chat_id={chat_id}")
        answer = ""
        for m in (msg_resp.get("data") or []):
            if m.get("type") == "answer":
                answer = m.get("content", "")
        return {"success": True, "answer": answer}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Coze 对话失败: {e}")
        raise HTTPException(status_code=500, detail=f"AI 助手异常：{str(e)}")


# ========== 评委打分接口 ==========
@app.get("/api/judge/records")
def get_judge_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50)
):
    """获取检测记录列表供评委浏览打分"""
    reset_time = get_judge_reset_time()
    conn = get_mysql_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        # 总数（仅统计重置时间之后的记录）
        cursor.execute(
            "SELECT COUNT(*) as total FROM detection_records WHERE create_time >= %s",
            [reset_time]
        )
        total = cursor.fetchone()["total"] or 0

        offset = (page - 1) * page_size
        cursor.execute(
            """SELECT id, file_name, original_image_url, result_image_url, mask_image_url,
                      wastage_rate, status, create_time
               FROM detection_records WHERE create_time >= %s
               ORDER BY id DESC LIMIT %s OFFSET %s""",
            [reset_time, page_size, offset]
        )
        records = cursor.fetchall()

        # 从评委独立数据库获取判定结果
        record_ids = [r["id"] for r in records]
        judge_map = {}
        if record_ids:
            jconn = get_judge_db_connection()
            jcursor = jconn.cursor(pymysql.cursors.DictCursor)
            try:
                placeholders = ",".join(["%s"] * len(record_ids))
                jcursor.execute(
                    f"SELECT record_id, result FROM judge_evaluations WHERE record_id IN ({placeholders})",
                    record_ids
                )
                for row in jcursor.fetchall():
                    judge_map[row["record_id"]] = row["result"]
            finally:
                jcursor.close()
                jconn.close()

        # 一次性查出所有记录的菜品，避免 N+1 查询
        items_map = {}
        if record_ids:
            placeholders = ",".join(["%s"] * len(record_ids))
            cursor.execute(
                f"SELECT record_id, food_name FROM detection_items WHERE record_id IN ({placeholders})",
                record_ids
            )
            for row in cursor.fetchall():
                items_map.setdefault(row["record_id"], []).append(row["food_name"])

        for rec in records:
            rec["original_image_url"] = rewrite_image_url(rec.get("original_image_url"))
            rec["result_image_url"] = rewrite_image_url(rec.get("result_image_url"))
            rec["mask_image_url"] = rewrite_image_url(rec.get("mask_image_url"))
            rec["judge_result"] = judge_map.get(rec["id"])
            rec["foods"] = items_map.get(rec["id"], [])

        return {
            "success": True,
            "data": {
                "records": records,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size if total > 0 else 0
                }
            }
        }
    finally:
        cursor.close()
        conn.close()

class JudgeEvaluateRequest(BaseModel):
    record_id: int
    result: str  # "correct" or "incorrect"

@app.post("/api/judge/evaluate")
def submit_judge_evaluation(req: JudgeEvaluateRequest):
    """评委提交判定结果"""
    if req.result not in ("correct", "incorrect"):
        raise HTTPException(status_code=400, detail="result 必须为 correct 或 incorrect")
    conn = get_judge_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO judge_evaluations (record_id, result)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE result = VALUES(result)
        """, [req.record_id, req.result])
        conn.commit()
        return {"success": True, "message": "判定已保存"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")
    finally:
        cursor.close()
        conn.close()

@app.get("/api/judge/score")
def get_judge_score():
    """获取评委打分汇总"""
    conn = get_judge_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT COUNT(*) as total FROM judge_evaluations")
        total = cursor.fetchone()["total"] or 0
        cursor.execute("SELECT COUNT(*) as correct FROM judge_evaluations WHERE result = 'correct'")
        correct = cursor.fetchone()["correct"] or 0
        incorrect = total - correct
        accuracy = round(correct / total * 100, 1) if total > 0 else 0
        return {
            "success": True,
            "data": {
                "total": total,
                "correct": correct,
                "incorrect": incorrect,
                "accuracy": accuracy
            }
        }
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/judge/reset")
def reset_judge_evaluations():
    """重置评委打分数据（设置重置时间点，之后的新记录才显示）"""
    conn = get_judge_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM judge_evaluations")
        cursor.execute(
            "UPDATE judge_config SET config_value = %s WHERE config_key = 'reset_time'",
            [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        )
        conn.commit()
        return {"success": True, "message": "评委打分数据已重置"}
    finally:
        cursor.close()
        conn.close()



# ========== 启动服务 ==========
if __name__ == "__main__":
    # 启动定时清理线程
    threading.Thread(target=auto_clean_task, daemon=True).start()

    # 端口占用检测
    def is_port_used(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    if is_port_used(DETECT_PORT):
        logger.error(f"❌ 端口 {DETECT_PORT} 已被占用")
        exit(1)

    # 加载模型
    yolo_model = load_yolo_model()
    load_unet_model()

    logger.info(f"🚀 启动餐盘残余菜品检测系统，端口：{DETECT_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=DETECT_PORT, reload=False, log_level="info", workers=1)