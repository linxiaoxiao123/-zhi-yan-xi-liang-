"""
特征提取脚本 —— 对files目录下所有图片跑YOLO+U-Net，提取特征存为CSV。
运行方式: python extract_features.py
输出文件: waste_cause_features.csv
"""

import os
import time
import numpy as np
import cv2
from PIL import Image
import torch
from ultralytics import YOLO
from torchvision import transforms
from unet_model import UNet

# ========== 配置（与main.py保持一致）==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "best.pt")
UNET_MODEL_PATH = os.path.join(BASE_DIR, "model", "unet_best.pth")
FILES_DIR = os.path.join(BASE_DIR, "files")
OUTPUT_CSV = os.path.join(BASE_DIR, "waste_cause_features.csv")

DETECT_PARAMS = {"conf": 0.3, "iou": 0.5, "imgsz": 800,
                 "augment": False, "agnostic_nms": True, "max_det": 20, "half": False}
UNET_NUM_CLASSES = 3
UNET_IMG_SIZE = (256, 256)
UNET_PREPROCESS = transforms.Compose([
    transforms.Resize(UNET_IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.229, 0.225])
])
TORCH_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ========== 加载模型 ==========
print("[1/5] 加载YOLO模型...")
yolo_model = YOLO(MODEL_PATH)
print(f"       设备: {TORCH_DEVICE}")

print("[2/5] 加载U-Net模型...")
unet_model = UNet(num_classes=UNET_NUM_CLASSES).to(TORCH_DEVICE)
unet_model.load_state_dict(torch.load(UNET_MODEL_PATH, map_location=TORCH_DEVICE))
unet_model.eval()
print(f"       U-Net已加载，设备: {TORCH_DEVICE}")


# ========== 图像预处理函数（从main.py复制）==========
def preprocess_image(image: Image.Image) -> np.ndarray:
    img = np.array(image)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    # 白平衡校正
    b, g, r = cv2.split(img)
    b_avg, g_avg, r_avg = np.mean(b), np.mean(g), np.mean(r)
    gray_avg = (b_avg + g_avg + r_avg) / 3.0
    b = np.clip(b * (gray_avg / (b_avg + 1e-6)), 0, 255).astype(np.uint8)
    g = np.clip(g * (gray_avg / (g_avg + 1e-6)), 0, 255).astype(np.uint8)
    r = np.clip(r * (gray_avg / (r_avg + 1e-6)), 0, 255).astype(np.uint8)
    img = cv2.merge((b, g, r))
    # 缩放+letterbox
    h, w = img.shape[:2]
    scale = min(DETECT_PARAMS["imgsz"] / w, DETECT_PARAMS["imgsz"] / h)
    new_w, new_h = int(w * scale), int(h * scale)
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    pad_x = (DETECT_PARAMS["imgsz"] - new_w) // 2
    pad_y = (DETECT_PARAMS["imgsz"] - new_h) // 2
    return cv2.copyMakeBorder(img, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=(0, 0, 0))


def unet_infer(image: Image.Image) -> np.ndarray:
    input_tensor = UNET_PREPROCESS(image).unsqueeze(0).to(TORCH_DEVICE)
    with torch.no_grad():
        output = unet_model(input_tensor)
    return torch.argmax(output, dim=1).squeeze(0).cpu().numpy()


def calculate_wastage_rate_raw(mask: np.ndarray):
    """计算原始浪费率（不含硬编码修正），返回(raw_rate, plate_px, food_px, oil_px)"""
    food_mask = (mask == 2).astype(np.uint8)
    plate_mask = (mask == 1).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    food_cleaned = cv2.morphologyEx(food_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    plate_cleaned = cv2.morphologyEx(plate_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(food_cleaned, connectivity=8)
    food_filtered = np.zeros_like(food_cleaned)
    min_area = 100
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            food_filtered[labels == i] = 1

    oil_pixels = int(np.sum(food_cleaned)) - int(np.sum(food_filtered))
    plate_pixels = int(np.sum(plate_cleaned))
    food_pixels = int(np.sum(food_filtered))

    total_plate = food_pixels + plate_pixels
    if total_plate == 0:
        raw_rate = 0.0
    else:
        raw_rate = round((food_pixels / total_plate) * 100, 2)

    return raw_rate, plate_pixels, food_pixels, oil_pixels


# ========== 核心：从单张图片提取特征 ==========
def extract_features_from_image(image_path: str, filename: str) -> dict:
    feats = {"filename": filename, "image_path": image_path}

    # --- 图像加载 ---
    img_pil = Image.open(image_path).convert("RGB")
    original_img = np.array(img_pil)
    h, w = original_img.shape[:2]
    feats["img_height"] = h
    feats["img_width"] = w
    feats["img_aspect_ratio"] = round(w / h, 3)

    # 颜色统计
    bgr = cv2.cvtColor(original_img, cv2.COLOR_RGB2BGR)
    b_mean, g_mean, r_mean = np.mean(bgr, axis=(0, 1))
    feats["avg_b"] = round(float(b_mean), 1)
    feats["avg_g"] = round(float(g_mean), 1)
    feats["avg_r"] = round(float(r_mean), 1)
    feats["color_temp"] = round(float(r_mean - b_mean), 1)

    # --- YOLO检测 ---
    processed = preprocess_image(img_pil)
    yolo_results = yolo_model(processed, **DETECT_PARAMS)

    detected_dishes = []
    dish_confidences = []
    dish_bboxes = []
    for box in yolo_results[0].boxes:
        cls = int(box.cls[0])
        conf = round(float(box.conf[0]), 3)
        dish_name = yolo_model.names[cls]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        detected_dishes.append(dish_name)
        dish_confidences.append(conf)
        dish_bboxes.append({"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
                            "name": dish_name})

    feats["detected_count"] = len(detected_dishes)
    feats["avg_confidence"] = round(float(np.mean(dish_confidences)), 3) if dish_confidences else 0.0
    feats["min_confidence"] = round(float(np.min(dish_confidences)), 3) if dish_confidences else 0.0
    feats["detected_dishes"] = "|".join(detected_dishes)

    # 菜品类型统计
    rice_keywords = ["米饭", "米", "饭"]
    meat_keywords = ["肉", "鸡", "鸭", "鱼", "虾", "猪", "牛", "蛋", "翅", "腿", "丸", "排"]
    veg_keywords = ["菜", "茄", "豆", "菇", "瓜", "椒", "蔬", "笋", "菌", "粉"]

    has_rice = any(any(kw in dish for kw in rice_keywords) for dish in detected_dishes)
    meat_count = sum(1 for dish in detected_dishes if any(kw in dish for kw in meat_keywords))
    veg_count = sum(1 for dish in detected_dishes if any(kw in dish for kw in veg_keywords))

    feats["has_rice"] = int(has_rice)
    feats["meat_dish_count"] = meat_count
    feats["veg_dish_count"] = veg_count
    feats["meat_veg_ratio"] = round(meat_count / max(veg_count, 1), 2)

    # 菜品空间分布特征
    if dish_bboxes:
        bbox_areas = [(b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) for b in dish_bboxes]
        bbox_centers_x = [(b["x1"] + b["x2"]) / 2 / w for b in dish_bboxes]
        bbox_centers_y = [(b["y1"] + b["y2"]) / 2 / h for b in dish_bboxes]
        feats["avg_bbox_area_ratio"] = round(float(np.mean(bbox_areas)) / (w * h), 4)
        feats["bbox_overlap_score"] = round(
            float(np.std(bbox_centers_x) + np.std(bbox_centers_y)) / 2, 4)
    else:
        feats["avg_bbox_area_ratio"] = 0.0
        feats["bbox_overlap_score"] = 0.0

    # --- U-Net分割 ---
    unet_mask = unet_infer(img_pil)
    unet_mask = cv2.resize(unet_mask, (w, h), interpolation=cv2.INTER_NEAREST)

    raw_rate, plate_px, food_px, oil_px = calculate_wastage_rate_raw(unet_mask)

    feats["waste_rate_raw"] = raw_rate
    feats["plate_pixels"] = plate_px
    feats["food_pixels"] = food_px
    feats["oil_pixels"] = oil_px
    feats["waste_ratio"] = round(food_px / max(food_px + plate_px, 1), 4)
    feats["oil_ratio"] = round(oil_px / max(food_px + plate_px, 1), 4)

    # 浪费率等级
    if raw_rate < 5:
        feats["waste_level"] = "low"
        feats["waste_level_int"] = 0
    elif raw_rate < 20:
        feats["waste_level"] = "medium"
        feats["waste_level_int"] = 1
    else:
        feats["waste_level"] = "high"
        feats["waste_level_int"] = 2

    # 分割质量特征
    food_mask = (unet_mask == 2).astype(np.uint8)
    num_labels_food, _, _, _ = cv2.connectedComponentsWithStats(food_mask, connectivity=8)
    feats["food_fragment_count"] = num_labels_food - 1

    # 食物空间分布
    mid_h, mid_w = h // 2, w // 2
    food_top = np.sum(food_mask[:mid_h, :])
    food_bottom = np.sum(food_mask[mid_h:, :])
    food_left = np.sum(food_mask[:, :mid_w])
    food_right = np.sum(food_mask[:, mid_w:])
    total_food = max(np.sum(food_mask), 1)
    feats["food_top_ratio"] = round(float(food_top / total_food), 3)
    feats["food_bottom_ratio"] = round(float(food_bottom / total_food), 3)
    feats["food_left_ratio"] = round(float(food_left / total_food), 3)
    feats["food_right_ratio"] = round(float(food_right / total_food), 3)

    # 浪费分布熵
    quadrant_ratios = np.array([
        food_top, food_bottom, food_left, food_right
    ]) / total_food
    quadrant_ratios = quadrant_ratios[quadrant_ratios > 0]
    waste_entropy = -np.sum(quadrant_ratios * np.log(quadrant_ratios + 1e-10))
    feats["waste_spatial_entropy"] = round(float(waste_entropy), 3)

    return feats


# ========== 主流程 ==========
def main():
    print("[3/5] 扫描files目录...")
    image_files = sorted([
        f for f in os.listdir(FILES_DIR)
        if f.endswith((".jpg", ".jpeg", ".png"))
    ])
    print(f"       找到 {len(image_files)} 张图片")

    if len(image_files) == 0:
        print("ERROR: files目录下没有original_*.jpg文件！")
        return

    print("[4/5] 提取特征中...")
    all_features = []
    errors = []
    t_start = time.time()

    for i, img_file in enumerate(image_files):
        img_path = os.path.join(FILES_DIR, img_file)
        try:
            feats = extract_features_from_image(img_path, img_file)
            all_features.append(feats)
            if (i + 1) % 10 == 0 or i == len(image_files) - 1:
                elapsed = time.time() - t_start
                speed = elapsed / (i + 1)
                eta = speed * (len(image_files) - i - 1) if i < len(image_files) - 1 else 0
                print(f"       [{i+1}/{len(image_files)}] 已耗时{elapsed:.0f}s | "
                      f"预计剩余{eta:.0f}s | 最新: {img_file[:30]}")
        except Exception as e:
            errors.append((img_file, str(e)))
            print(f"       WARNING {img_file} 处理失败: {e}")

    elapsed = time.time() - t_start
    print(f"       完成! 总耗时: {elapsed:.1f}s | 成功: {len(all_features)} | 失败: {len(errors)}")
    if errors:
        for fname, err in errors:
            print(f"        失败: {fname} -> {err}")

    # 保存CSV
    print(f"[5/5] 保存特征到 {OUTPUT_CSV}...")
    import csv
    if all_features:
        keys = all_features[0].keys()
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_features)
        print(f"       OK 已保存 {len(all_features)} 条特征数据")
        print(f"       文件: {OUTPUT_CSV}")
        print(f"       特征维度: {len(keys)} 维")
        print(f"       前10个特征: {list(keys)[:10]}")
    else:
        print("       ERROR 没有成功提取任何特征！")


if __name__ == "__main__":
    main()
