# -*- coding: utf-8 -*-
"""
给 YOLOv8 训练曲线图（results.png）加标注：
1. 在 mAP50 / mAP50-95 两个关键子图外画红色高亮框
2. 在图片底部加"结果摘要"条（关键指标一目了然）
输出标注版，不修改原图。
"""
import shutil
from PIL import Image, ImageDraw, ImageFont

SRC = r"C:\Users\34542\OneDrive\xwechat_files\wxid_0qry9i9m4p9h22_2c0b\temp\RWTemp\2026-08\8ff413a481465a8ff94571687490e36a.png"
DST_RAW = r"D:\毕设\智眼惜粮-GitHub\backend\yolo_training_curves.png"
DST_ANN = r"D:\毕设\智眼惜粮-GitHub\backend\yolo_training_curves_annotated.png"

# 1. 复制原图到项目目录（论文用原图）
shutil.copy(SRC, DST_RAW)
print(f"✅ 原图已复制到: {DST_RAW}")

img = Image.open(SRC).convert("RGB")
W, H = img.size
print(f"原图尺寸: {W}x{H}")

# 2. 底部扩展摘要条
BAR_H = 130
new_img = Image.new("RGB", (W, H + BAR_H), "white")
new_img.paste(img, (0, 0))

draw = ImageDraw.Draw(new_img)

# 中文字体
def load_font(size):
    for fp in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
               r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"]:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()

# 3. 红框圈出 mAP50 与 mAP50-95（第2行第4、5列）
# 标准 2 行 x 5 列布局，留少量内缩
col_w = W / 5.0
row_h = H / 2.0
# 列索引（0-based）：mAP50=3, mAP50-95=4；行=1（第二行）
for idx, label in [(3, "mAP@0.5"), (4, "mAP@0.5:0.95")]:
    x0 = int(idx * col_w) + 8
    y0 = int(1 * row_h) + 8
    x1 = int((idx + 1) * col_w) - 8
    y1 = int((1 + 1) * row_h) - 8
    draw.rectangle([x0, y0, x1, y1], outline=(220, 20, 60), width=6)
    draw.text((x0 + 10, y0 + 10), label, fill=(220, 20, 60), font=load_font(30))

# 4. 底部摘要条
title_font = load_font(34)
txt_font = load_font(28)

draw.text((30, H + 16), "检测模型（YOLOv8）最终性能", fill=(30, 30, 30), font=title_font)
summary = "mAP@0.5 = 0.90     Precision = 0.90     Recall = 0.85     mAP@0.5:0.95 = 0.57"
draw.text((30, H + 72), summary, fill=(220, 20, 60), font=load_font(36))

new_img.save(DST_ANN, dpi=(200, 200))
print(f"✅ 标注版已保存: {DST_ANN}")
print(f"   标注版尺寸: {new_img.size}")
