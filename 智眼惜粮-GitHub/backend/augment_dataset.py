"""
离线数据增强 V2：每张原图 ×9 复杂变体 → 保存图片 → 提取特征 → 输出CSV
运行方式: python augment_dataset.py
输出:
  files/augmented/  → 增强图片 (N × 9 张)
  waste_cause_features_augmented.csv → 特征+标签
"""
import os
import time
import numpy as np
import cv2
from PIL import Image
import pandas as pd

import albumentations as A
import torch
from ultralytics import YOLO
from torchvision import transforms

from unet_model import UNet

# ========== 配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "best.pt")
UNET_MODEL_PATH = os.path.join(BASE_DIR, "model", "unet_best.pth")
FILES_DIR = os.path.join(BASE_DIR, "files")
AUG_DIR = os.path.join(FILES_DIR, "augmented")
OLD_CSV = os.path.join(BASE_DIR, "waste_cause_features_labeled.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "waste_cause_features_augmented.csv")
AUG_PER_IMAGE = 9

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

# ========== 9种增强策略（每种模拟一个真实场景） ==========
AUGMENTATIONS = [
    # 0. 强光照变化 — 模拟晴天/阴天/不同色温灯光
    A.Compose([
        A.RandomBrightnessContrast(brightness_limit=0.35, contrast_limit=0.35, p=1.0),
        A.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2, hue=0.08, p=1.0),
    ], p=1.0),

    # 1. 几何变换 — 模拟拍摄角度偏移
    A.Compose([
        A.ShiftScaleRotate(shift_limit=0.06, scale_limit=0.12, rotate_limit=12,
                           border_mode=cv2.BORDER_REFLECT_101, p=1.0),
        A.Perspective(scale=(0.03, 0.06), keep_size=True, p=1.0),
    ], p=1.0),

    # 2. 高斯模糊 — 模拟对焦不准
    A.Compose([
        A.GaussianBlur(blur_limit=(5, 9), p=1.0),
        A.GaussNoise(var_limit=(5.0, 20.0), p=0.6),
    ], p=1.0),

    # 3. 运动模糊 — 模拟摄像头抖动
    A.Compose([
        A.MotionBlur(blur_limit=(5, 11), p=1.0),
        A.ISONoise(color_shift=(0.01, 0.03), intensity=(0.05, 0.15), p=0.6),
    ], p=1.0),

    # 4. 色相/饱和度偏移 — 模拟不同品牌摄像头
    A.Compose([
        A.HueSaturationValue(hue_shift_limit=15, sat_shift_limit=25, val_shift_limit=25, p=1.0),
        A.RandomGamma(gamma_limit=(75, 125), p=1.0),
    ], p=1.0),

    # 5. RGB通道偏移 — 模拟白平衡偏差
    A.Compose([
        A.RGBShift(r_shift_limit=15, g_shift_limit=15, b_shift_limit=15, p=1.0),
        A.ChannelShuffle(p=0.3),  # 随机交换通道
        A.ToGray(p=0.2),          # 20%概率转灰度再转回（削弱依赖颜色）
    ], p=1.0),

    # 6. 极端噪声 — 模拟低光照/高ISO
    A.Compose([
        A.GaussNoise(var_limit=(30.0, 80.0), p=1.0),
        A.MultiplicativeNoise(multiplier=(0.95, 1.05), p=0.8),
        A.CLAHE(clip_limit=2.0, tile_grid_size=(8, 8), p=0.5),
    ], p=1.0),

    # 7. 局部遮挡 + 阴影 — 模拟餐盘叠放/部分遮挡
    A.Compose([
        A.CoarseDropout(max_holes=6, max_height=60, max_width=60,
                        min_holes=2, fill_value=0, p=1.0),
        A.RandomShadow(shadow_roi=(0, 0, 1, 1), num_shadows_lower=1, num_shadows_upper=2,
                       shadow_dimension=3, p=0.7),
    ], p=1.0),

    # 8. 综合极端增强 — 上述随机组合 + 弹性变形
    A.Compose([
        A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.7),
        A.ShiftScaleRotate(shift_limit=0.04, scale_limit=0.1, rotate_limit=10,
                           border_mode=cv2.BORDER_REFLECT_101, p=0.7),
        A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=20, val_shift_limit=20, p=0.6),
        A.OneOf([
            A.GaussianBlur(blur_limit=(3, 7), p=1.0),
            A.MotionBlur(blur_limit=(3, 7), p=1.0),
        ], p=0.6),
        A.GaussNoise(var_limit=(10.0, 40.0), p=0.5),
        A.CoarseDropout(max_holes=4, max_height=50, max_width=50, fill_value=128, p=0.3),
        A.ElasticTransform(alpha=30, sigma=5, alpha_affine=5, p=0.3),
    ], p=1.0),
]

# ========== 加载模型 ==========
print("[1/4] 加载YOLO和U-Net模型...")
yolo_model = YOLO(MODEL_PATH)
unet_model = UNet(num_classes=UNET_NUM_CLASSES).to(TORCH_DEVICE)
unet_model.load_state_dict(torch.load(UNET_MODEL_PATH, map_location=TORCH_DEVICE))
unet_model.eval()
print(f"      设备: {TORCH_DEVICE}")

from extract_features import preprocess_image, unet_infer, calculate_wastage_rate_raw


def extract_from_array(img_bgr: np.ndarray, filename: str) -> dict:
    """从BGR数组提取完整特征向量"""
    h, w = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)

    feats = {"filename": filename}
    feats["img_height"] = h
    feats["img_width"] = w
    feats["img_aspect_ratio"] = round(w / h, 3)

    b_mean, g_mean, r_mean = np.mean(img_bgr, axis=(0, 1))
    feats["avg_b"] = round(float(b_mean), 1)
    feats["avg_g"] = round(float(g_mean), 1)
    feats["avg_r"] = round(float(r_mean), 1)
    feats["color_temp"] = round(float(r_mean - b_mean), 1)

    # ---- YOLO检测 ----
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
        dish_bboxes.append({
            "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
            "name": dish_name
        })

    feats["detected_count"] = len(detected_dishes)
    feats["avg_confidence"] = round(float(np.mean(dish_confidences)), 3) if dish_confidences else 0.0
    feats["min_confidence"] = round(float(np.min(dish_confidences)), 3) if dish_confidences else 0.0
    feats["detected_dishes"] = "|".join(detected_dishes)

    rice_kw = ["米饭", "米", "饭"]
    meat_kw = ["肉", "鸡", "鸭", "鱼", "虾", "猪", "牛", "蛋", "翅", "腿", "丸", "排"]
    veg_kw = ["菜", "茄", "豆", "菇", "瓜", "椒", "蔬", "笋", "菌", "粉"]
    has_rice = any(any(kw in dish for kw in rice_kw) for dish in detected_dishes)
    meat_cnt = sum(1 for d in detected_dishes if any(kw in d for kw in meat_kw))
    veg_cnt = sum(1 for d in detected_dishes if any(kw in d for kw in veg_kw))
    feats["has_rice"] = int(has_rice)
    feats["meat_dish_count"] = meat_cnt
    feats["veg_dish_count"] = veg_cnt
    feats["meat_veg_ratio"] = round(meat_cnt / max(veg_cnt, 1), 2)

    if dish_bboxes:
        areas = [(b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) for b in dish_bboxes]
        cx = [(b["x1"] + b["x2"]) / 2 / w for b in dish_bboxes]
        cy = [(b["y1"] + b["y2"]) / 2 / h for b in dish_bboxes]
        feats["avg_bbox_area_ratio"] = round(float(np.mean(areas)) / (w * h), 4)
        feats["bbox_overlap_score"] = round(
            (float(np.std(cx)) + float(np.std(cy))) / 2, 4)
    else:
        feats["avg_bbox_area_ratio"] = 0.0
        feats["bbox_overlap_score"] = 0.0

    # ---- U-Net分割 ----
    unet_mask = unet_infer(img_pil)
    unet_mask = cv2.resize(unet_mask, (w, h), interpolation=cv2.INTER_NEAREST)
    raw_rate, plate_px, food_px, oil_px = calculate_wastage_rate_raw(unet_mask)

    feats["waste_rate_raw"] = raw_rate
    feats["plate_pixels"] = plate_px
    feats["food_pixels"] = food_px
    feats["oil_pixels"] = oil_px
    feats["waste_ratio"] = round(food_px / max(food_px + plate_px, 1), 4)
    feats["oil_ratio"] = round(oil_px / max(food_px + plate_px, 1), 4)

    if raw_rate < 5:
        feats["waste_level"] = "low"
        feats["waste_level_int"] = 0
    elif raw_rate < 20:
        feats["waste_level"] = "medium"
        feats["waste_level_int"] = 1
    else:
        feats["waste_level"] = "high"
        feats["waste_level_int"] = 2

    food_mask = (unet_mask == 2).astype(np.uint8)
    num_labels_food, _, _, _ = cv2.connectedComponentsWithStats(food_mask, connectivity=8)
    feats["food_fragment_count"] = num_labels_food - 1

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

    quad = np.array([food_top, food_bottom, food_left, food_right]) / total_food
    quad = quad[quad > 0]
    feats["waste_spatial_entropy"] = round(
        float(-np.sum(quad * np.log(quad + 1e-10))), 3)

    feats["waste_rate_capped"] = min(max(raw_rate, 0), 100)
    feats["waste_ratio_capped"] = round(min(food_px / max(food_px + plate_px, 1), 1.0), 4)

    return feats


def main():
    # ===== 扫描原始图片（用户确认全部是纯净原图） =====
    print("[2/4] 扫描原始图片...")
    image_files = sorted([
        f for f in os.listdir(FILES_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    print(f"       纯净原图: {len(image_files)} 张")

    # ===== 加载旧标签 =====
    print("       加载标签映射...")
    if os.path.exists(OLD_CSV):
        old_df = pd.read_csv(OLD_CSV)
        label_map = dict(zip(old_df["filename"], old_df["cause_label"]))
        cluster_map = dict(zip(old_df["filename"], old_df["cluster"]))
    else:
        label_map = {}
        cluster_map = {}
    labeled = sum(1 for f in image_files if f in label_map)
    unlabeled = len(image_files) - labeled
    print(f"       有标签: {labeled} | 无标签(跳过): {unlabeled}")

    # ===== 创建增强输出目录 =====
    os.makedirs(AUG_DIR, exist_ok=True)

    # ===== 增强 + 提取特征 =====
    all_rows = []
    skipped = 0
    t_start = time.time()
    total_imgs = labeled * (1 + AUG_PER_IMAGE)  # 原图 + 增强图

    print(f"[3/4] 增强处理 (每张×{AUG_PER_IMAGE}, 共{total_imgs}张)...")

    for idx, img_file in enumerate(image_files):
        if img_file not in label_map:
            skipped += 1
            continue

        img_path = os.path.join(FILES_DIR, img_file)
        img_bgr = cv2.imread(img_path)
        if img_bgr is None:
            skipped += 1
            continue
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        base_name = os.path.splitext(img_file)[0]
        cause_label = label_map[img_file]
        cluster_id = cluster_map.get(img_file, -1)

        # --- 保留原图特征（已有，从旧CSV读） ---
        old_row = old_df[old_df["filename"] == img_file]
        if len(old_row) > 0:
            row_dict = old_row.iloc[0].to_dict()
            row_dict["image_path"] = img_path
            row_dict["is_augmented"] = 0
            all_rows.append(row_dict)

        # --- 生成增强变体 ---
        for aug_idx, aug_pipeline in enumerate(AUGMENTATIONS):
            aug_name = f"{base_name}_aug{aug_idx}.jpg"
            aug_save_path = os.path.join(AUG_DIR, aug_name)

            try:
                augmented = aug_pipeline(image=img_rgb)
                aug_bgr = cv2.cvtColor(augmented["image"], cv2.COLOR_RGB2BGR)
                cv2.imwrite(aug_save_path, aug_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])

                feats = extract_from_array(aug_bgr, aug_name)
                feats["image_path"] = aug_save_path
                feats["cause_label"] = cause_label
                feats["cluster"] = cluster_id
                feats["is_augmented"] = 1
                all_rows.append(feats)
            except Exception as e:
                skipped += 1
                if skipped <= 5:
                    print(f"       WARNING {img_file}_aug{aug_idx}: {e}")

        if (idx + 1) % 20 == 0:
            elapsed = time.time() - t_start
            done = idx + 1
            speed = elapsed / max(done, 1)
            remaining = speed * (labeled - done)
            print(f"       [{done}/{labeled}] 耗时{elapsed:.0f}s | 预计剩余{remaining:.0f}s | 已生成{len(all_rows)}条")

    elapsed = time.time() - t_start
    augmented_df = pd.DataFrame(all_rows)
    total = len(augmented_df)
    n_aug = int(augmented_df["is_augmented"].sum()) if "is_augmented" in augmented_df.columns else 0
    n_orig = total - n_aug

    print(f"       完成! 耗时{elapsed:.1f}s | 原图:{n_orig} + 增强:{n_aug} = {total} | 跳过:{skipped}")

    # ===== 保存 =====
    print(f"[4/4] 保存 {OUTPUT_CSV}...")
    augmented_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"       OK! {total} 条")

    print(f"\n增强后标签分布:")
    for label, count in augmented_df["cause_label"].value_counts().items():
        pct = count / total * 100
        print(f"  {label}: {count} ({pct:.1f}%)")

    print(f"\n增强图片保存在: {AUG_DIR}")
    print(f"特征CSV: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
