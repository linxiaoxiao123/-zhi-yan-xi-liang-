# gen_unet_vis.py
# 用线上同款 unet_best.pth 对真实餐盘图推理，生成 U-Net 分割效果可视化（图 4-2）。
# 推理逻辑与 main.py 完全一致：UNET_PREPROCESS / argmax / INTER_NEAREST 还原 / 形态学后处理 / 浪费率口径。
import os, glob, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch
from torchvision import transforms
from unet_model import UNet

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NUM_CLASSES = 3
IMG_SIZE = (256, 256)
UNET_PREPROCESS = transforms.Compose([
    transforms.Resize(IMG_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.229, 0.225]),
])

FONT_PATH = r"C:\Windows\Fonts\simhei.ttf"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PNG = os.path.join(OUT_DIR, "unet_seg_examples.png")

# ---------- 模型加载（同 main.py load_unet_model） ----------
model = UNet(num_classes=NUM_CLASSES).to(DEVICE)
model.load_state_dict(torch.load("model/unet_best.pth", map_location=DEVICE))
model.eval()
print(f"U-Net 加载成功，设备：{DEVICE}")

# ---------- 推理 + 后处理（同 main.py） ----------
def unet_infer(img_pil):
    t = UNET_PREPROCESS(img_pil).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        out = model(t)
    return torch.argmax(out, 1).squeeze(0).cpu().numpy()  # (256,256) 0/1/2

def calculate_wastage_rate(mask):
    food_mask = (mask == 2).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    food_cleaned = cv2.morphologyEx(food_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(food_cleaned, connectivity=8)
    food_filtered = np.zeros_like(food_cleaned)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= 100:
            food_filtered[labels == i] = 1
    plate_mask = (mask == 1).astype(np.uint8)
    plate_cleaned = cv2.morphologyEx(plate_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    plate_pixels = int(np.sum(plate_cleaned))
    food_pixels = int(np.sum(food_filtered))
    total = food_pixels + plate_pixels
    wr = round((food_pixels / total) * 100, 2) if total > 0 else 0.0
    return max(wr, 0.0), plate_pixels, food_pixels

def make_panels(original_bgr, mask_full):
    """返回 (原图RGB, 纯色掩膜RGB, 叠加RGB)，颜色定义统一为 RGB：餐盘蓝、食物红。"""
    h, w = original_bgr.shape[:2]
    mask_resized = cv2.resize(mask_full, (w, h), interpolation=cv2.INTER_NEAREST)
    original_rgb = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2RGB)

    # 纯色掩膜：背景黑、餐盘蓝 (RGB)、食物红 (RGB)
    color_mask = np.zeros((h, w, 3), dtype=np.uint8)
    color_mask[mask_resized == 1] = (60, 120, 216)   # 餐盘-蓝
    color_mask[mask_resized == 2] = (220, 50, 50)    # 食物-红

    # 叠加可视化：原图 40% + 掩膜色 60%，与 main.py 的 addWeighted 目的一致（半透明叠加）
    overlay = (original_rgb * 0.4 + color_mask * 0.6).astype(np.uint8)
    return original_rgb, color_mask, overlay

# ---------- 处理全部基础图，按浪费率挑代表性样本 ----------
imgs = sorted(glob.glob(r"D:\yoloy\*.jpg"), key=lambda p: os.path.basename(p))
imgs = [p for p in imgs if "_aug" not in os.path.basename(p)]
print(f"待处理基础图：{len(imgs)} 张")

results = []
for p in imgs:
    bgr = cv2.imread(p)
    if bgr is None:
        continue
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    mask256 = unet_infer(pil)
    wr, plate_px, food_px = calculate_wastage_rate(mask256)
    # 过滤：必须检测到餐盘（掩膜有效），否则无展示意义
    if plate_px < 5000:
        continue
    results.append({
        "name": os.path.basename(p), "bgr": bgr, "mask256": mask256,
        "wr": wr, "plate_px": plate_px, "food_px": food_px,
    })

print(f"有效（检测到餐盘）样本：{len(results)} 张")
results.sort(key=lambda r: r["wr"])
# 在有效区间均匀挑 6 张，覆盖低/中/高浪费率
N = min(6, len(results))
if N == 1:
    picks = results
else:
    picks = [results[int(i * (len(results) - 1) / (N - 1))] for i in range(N)]
print("挑选样本浪费率：", [r["wr"] for r in picks])

# ---------- 拼图（PIL + 黑体中文） ----------
CELL = 240
GAP = 8
HEADER = 40
LABEL_W = 110
cols = 3  # 原图 / 掩码 / 叠加
col_titles = ["原图", "分割掩码", "叠加可视化"]

def draw_text(draw, pos, text, size=18, color=(0, 0, 0)):
    font = ImageFont.truetype(FONT_PATH, size)
    draw.text(pos, text, font=font, fill=color)

W = LABEL_W + cols * (CELL + GAP) + GAP
H = HEADER + N * (CELL + GAP) + GAP + 50  # 底部图例
canvas = Image.new("RGB", (W, H), (255, 255, 255))
draw = ImageDraw.Draw(canvas)

# 表头
for c, title in enumerate(col_titles):
    x = LABEL_W + GAP + c * (CELL + GAP)
    draw_text(draw, (x + CELL // 2 - 30, HEADER // 2 - 12), title, size=19)

for i, r in enumerate(picks):
    y0 = HEADER + i * (CELL + GAP) + GAP
    orig, msk, ov = make_panels(r["bgr"], r["mask256"])
    panels = [Image.fromarray(orig), Image.fromarray(msk), Image.fromarray(ov)]
    for c, panel in enumerate(panels):
        x0 = LABEL_W + GAP + c * (CELL + GAP)
        panel = panel.resize((CELL, CELL))
        canvas.paste(panel, (x0, y0))
    # 左侧标签
    draw_text(draw, (10, y0 + CELL // 2 - 26), f"样例{i+1}", size=17)
    draw_text(draw, (10, y0 + CELL // 2 - 2), f"浪费率 {r['wr']}%", size=16, color=(200, 0, 0))

# 底部图例
ly = H - 40
draw_text(draw, (LABEL_W + GAP, ly), "图例：", size=16)
draw.rectangle([LABEL_W + GAP + 55, ly + 4, LABEL_W + GAP + 95, ly + 24], fill=(60, 120, 216))
draw_text(draw, (LABEL_W + GAP + 100, ly), "餐盘", size=16)
draw.rectangle([LABEL_W + GAP + 160, ly + 4, LABEL_W + GAP + 200, ly + 24], fill=(220, 50, 50))
draw_text(draw, (LABEL_W + GAP + 205, ly), "食物", size=16)
draw_text(draw, (LABEL_W + GAP + 265, ly), "（其余为背景）", size=14, color=(120, 120, 120))

canvas.save(OUT_PNG)
print(f"✅ 已保存组图：{OUT_PNG}")

# 额外导出单列原图+叠加的清晰版，供论文单独引用
for i, r in enumerate(picks):
    orig, msk, ov = make_panels(r["bgr"], r["mask256"])
    Image.fromarray(ov).resize((360, 360)).save(os.path.join(OUT_DIR, f"unet_overlay_{i+1}.png"))
print("✅ 已导出叠加单图 unet_overlay_1~%d.png" % N)
