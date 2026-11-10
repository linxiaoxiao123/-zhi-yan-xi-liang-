"""
对files目录下所有图片跑YOLO+U-Net，保存标注图到 files/annotated/ 目录
运行方式: python visualize_detections.py
输出:
  files/annotated/  → 每张图3个视角（检测框/分割掩码/合成）
  detection_quality.csv → 所有图片的检测质量指标，方便排序筛选
"""
import os
import time
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import pandas as pd

import torch
from ultralytics import YOLO
from torchvision import transforms
from unet_model import UNet

# ========== 配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "best.pt")
UNET_MODEL_PATH = os.path.join(BASE_DIR, "model", "unet_best.pth")
FILES_DIR = os.path.join(BASE_DIR, "files")
OUT_DIR = os.path.join(FILES_DIR, "annotated")
QUALITY_CSV = os.path.join(BASE_DIR, "detection_quality.csv")

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

# ========== 颜色定义 ==========
COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (128, 255, 0), (255, 128, 0),
    (0, 128, 255), (128, 0, 255), (255, 128, 128), (128, 255, 128),
]
MASK_COLORS = {
    0: (0, 0, 0),        # 背景-黑色
    1: (0, 255, 0),      # 餐盘-绿色
    2: (255, 0, 0),      # 食物-红色
}


def preprocess_image(image: Image.Image) -> np.ndarray:
    img = np.array(image)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    b, g, r = cv2.split(img)
    b_avg, g_avg, r_avg = np.mean(b), np.mean(g), np.mean(r)
    gray_avg = (b_avg + g_avg + r_avg) / 3.0
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


def unet_infer(image: Image.Image) -> np.ndarray:
    model = load_unet_model()
    input_tensor = UNET_PREPROCESS(image).unsqueeze(0).to(TORCH_DEVICE)
    with torch.no_grad():
        output = model(input_tensor)
    return torch.argmax(output, dim=1).squeeze(0).cpu().numpy()


def draw_detection_boxes(img_bgr, yolo_results, class_names):
    """在图上画YOLO检测框"""
    img = img_bgr.copy()
    h, w = img.shape[:2]
    for box in yolo_results[0].boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        name = class_names[cls]
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        color = COLORS[cls % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"{name} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img, (x1, y1 - th - 4), (x1 + tw, y1), color, -1)
        cv2.putText(img, label, (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1, cv2.LINE_AA)
    return img


def draw_mask_overlay(img_bgr, mask):
    """在原图上叠加分割掩码"""
    h, w = img_bgr.shape[:2]
    mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    overlay = img_bgr.copy()
    for cls_id, color in MASK_COLORS.items():
        if cls_id == 0:
            continue
        alpha = 0.45 if cls_id == 1 else 0.55
        overlay[mask_resized == cls_id] = color
    return cv2.addWeighted(img_bgr, 0.5, overlay, 0.5, 0)


def draw_combined(img_bgr, yolo_results, mask, class_names):
    """检测框+分割掩码合成图"""
    img = draw_detection_boxes(img_bgr, yolo_results, class_names)
    h, w = img.shape[:2]
    mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    overlay = img.copy()
    overlay[mask_resized == 2] = (0, 0, 255)  # 食物-红色
    overlay[mask_resized == 1] = (0, 255, 0)  # 餐盘-绿色
    return cv2.addWeighted(img, 0.6, overlay, 0.4, 0)


def calculate_quality(unet_mask):
    """计算U-Net分割质量指标"""
    plate_mask = (unet_mask == 1).astype(np.uint8)
    food_mask = (unet_mask == 2).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    plate_cleaned = cv2.morphologyEx(plate_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    food_cleaned = cv2.morphologyEx(food_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(food_cleaned, connectivity=8)
    food_filtered = np.zeros_like(food_cleaned)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= 100:
            food_filtered[labels == i] = 1

    plate_px = int(np.sum(plate_cleaned))
    food_px = int(np.sum(food_filtered))
    oil_px = int(np.sum(food_cleaned)) - food_px

    if plate_px > 0:
        waste_rate = round((food_px / plate_px) * 100, 1)
    else:
        waste_rate = 0.0

    return {
        "plate_pixels": plate_px,
        "food_pixels": food_px,
        "oil_pixels": oil_px,
        "waste_rate": min(waste_rate, 100.0),
    }


# ========== 模型加载 ==========
_unet_model = None


def load_unet_model():
    global _unet_model
    if _unet_model is not None:
        return _unet_model
    _unet_model = UNet(num_classes=UNET_NUM_CLASSES).to(TORCH_DEVICE)
    _unet_model.load_state_dict(torch.load(UNET_MODEL_PATH, map_location=TORCH_DEVICE))
    _unet_model.eval()
    return _unet_model


# ========== 主流程 ==========
def main():
    print(f"设备: {TORCH_DEVICE}")

    print("[1/3] 加载YOLO模型...")
    yolo_model = YOLO(MODEL_PATH)
    _ = load_unet_model()
    print(f"      YOLO classes: {len(yolo_model.names)}")

    print("[2/3] 扫描图片...")
    image_files = sorted([f for f in os.listdir(FILES_DIR)
                          if f.lower().endswith((".jpg", ".jpeg", ".png"))])
    # 跳过已有的结果图
    image_files = [f for f in image_files
                   if not f.startswith(("original_", "result_", "mask_", "annotated_"))]
    print(f"      待处理: {len(image_files)} 张")

    os.makedirs(OUT_DIR, exist_ok=True)

    quality_records = []
    errors = []
    t_start = time.time()

    for i, img_file in enumerate(image_files):
        img_path = os.path.join(FILES_DIR, img_file)
        try:
            img_pil = Image.open(img_path).convert("RGB")
            original_img = np.array(img_pil)
            original_bgr = cv2.cvtColor(original_img, cv2.COLOR_RGB2BGR)

            # YOLO检测
            processed = preprocess_image(img_pil)
            yolo_results = yolo_model(processed, **DETECT_PARAMS)

            n_det = len(yolo_results[0].boxes)
            confs = [float(b.conf[0]) for b in yolo_results[0].boxes]
            avg_conf = round(np.mean(confs), 3) if confs else 0.0
            min_conf = round(np.min(confs), 3) if confs else 0.0

            # U-Net分割
            unet_mask = unet_infer(img_pil)
            h, w = original_bgr.shape[:2]

            quality = calculate_quality(unet_mask)

            # 生成3张标注图
            img_boxes = draw_detection_boxes(original_bgr, yolo_results, yolo_model.names)
            img_mask = draw_mask_overlay(original_bgr, unet_mask)
            img_combined = draw_combined(original_bgr, yolo_results, unet_mask, yolo_model.names)

            # 保存
            base_name = os.path.splitext(img_file)[0]
            cv2.imwrite(os.path.join(OUT_DIR, f"{base_name}_boxes.jpg"), img_boxes)
            cv2.imwrite(os.path.join(OUT_DIR, f"{base_name}_mask.jpg"), img_mask)
            cv2.imwrite(os.path.join(OUT_DIR, f"{base_name}_combined.jpg"), img_combined)

            quality_records.append({
                "filename": img_file,
                "detected_count": n_det,
                "avg_confidence": avg_conf,
                "min_confidence": min_conf,
                "waste_rate": quality["waste_rate"],
                "plate_pixels": quality["plate_pixels"],
                "food_pixels": quality["food_pixels"],
                "oil_pixels": quality["oil_pixels"],
            })

            if (i + 1) % 20 == 0:
                elapsed = time.time() - t_start
                eta = elapsed / (i + 1) * (len(image_files) - i - 1)
                print(f"       [{i+1}/{len(image_files)}] 耗时{elapsed:.0f}s | 预计剩余{eta:.0f}s")

        except Exception as e:
            errors.append((img_file, str(e)))

    elapsed = time.time() - t_start
    print(f"       完成! 总耗时{elapsed:.1f}s | 成功{len(quality_records)} | 失败{len(errors)}")

    # 保存质量报告
    print(f"[3/3] 保存质量报告...")
    df = pd.DataFrame(quality_records)
    df.to_csv(QUALITY_CSV, index=False, encoding="utf-8-sig")
    print(f"      {QUALITY_CSV} ({len(df)} 条)")

    # 统计
    print(f"\n===== 质量统计 =====")
    print(f"  检测菜品数=0 的图片: {len(df[df['detected_count']==0])} 张  ← 可能是空盘/误拍")
    print(f"  浪费率>100% (分割异常): {len(df[df['waste_rate']>=100])} 张")
    print(f"  浪费率>80%: {len(df[df['waste_rate']>80])} 张")
    print(f"  平均置信度<0.5: {len(df[df['avg_confidence']<0.5])} 张  ← YOLO检测不够准")
    print(f"  油渍像素>0: {len(df[df['oil_pixels']>0])} 张")

    print(f"\n标注图保存在: {OUT_DIR}")
    print(f"质量报告: {QUALITY_CSV}")
    print(f"\n筛选建议:")
    print(f"  1. 打开 {OUT_DIR} 浏览 _combined.jpg 图")
    print(f"  2. 对照 {QUALITY_CSV} 找到质量差的图片")
    print(f"  3. 直接在 files/ 目录中删除对应原图")
    print(f"  4. 删除后重新运行 augment_dataset.py 做增强")


if __name__ == "__main__":
    main()
