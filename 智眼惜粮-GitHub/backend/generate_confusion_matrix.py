# -*- coding: utf-8 -*-
"""
混淆矩阵生成脚本（论文图 6-2）
=========================================
用训练好的弃因分类模型在测试集上预测，生成混淆矩阵热力图。

用法（必须用 bank/venv 的 Python，因为 torch 装在那里）：
    D:\\bank\\venv\\Scripts\\python.exe generate_confusion_matrix.py

输出：confusion_matrix.png（项目 backend 目录下）

说明：
- 优先使用增强数据 waste_cause_features_augmented.csv（云端训练用的，样本多）。
- 本地若没有增强 CSV，会自动降级到 waste_cause_features_labeled.csv（331 张原图，
  测试集约 33 张，混淆矩阵会较小）。要得到和论文一致的 302 样本混淆矩阵，
  请先从 CloudStudio 云端下载 waste_cause_features_augmented.csv 放到 backend 目录。
"""
import os
import sys
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# 中文字体设置（避免混淆矩阵中文标签乱码）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False


def stratified_train_test_split(df, test_size, seed):
    """按类别分层随机划分（替代 sklearn 的 train_test_split）"""
    rng = np.random.RandomState(seed)
    test_idx = []
    for label, group in df.groupby("cause_label"):
        idx = group.index.tolist()
        n_test = max(1, int(round(len(idx) * test_size)))
        chosen = rng.choice(idx, size=n_test, replace=False)
        test_idx.extend(chosen)
    test_df = df.loc[test_idx]
    train_df = df.drop(test_idx)
    return train_df, test_df


def build_confusion_matrix(labels, preds, num_classes):
    """构建混淆矩阵"""
    cm = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(labels, preds):
        cm[t][p] += 1
    return cm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from waste_cause_model import WasteCauseClassifier

CSV_FILE = os.path.join(BASE_DIR, "waste_cause_features_augmented.csv")
if not os.path.exists(CSV_FILE):
    CSV_FILE = os.path.join(BASE_DIR, "waste_cause_features_labeled.csv")
MODEL_PATH = os.path.join(BASE_DIR, "model", "waste_cause_3cls.pth")
OUTPUT_PNG = os.path.join(BASE_DIR, "confusion_matrix.png")

RANDOM_SEED = 42
torch.manual_seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

STRUCTURED_FEATURE_COLS = [
    "img_height", "img_width", "img_aspect_ratio",
    "avg_b", "avg_g", "avg_r", "color_temp",
    "detected_count", "avg_confidence", "min_confidence",
    "has_rice", "meat_dish_count", "veg_dish_count", "meat_veg_ratio",
    "avg_bbox_area_ratio", "bbox_overlap_score",
    "plate_pixels", "food_pixels", "oil_pixels",
    "oil_ratio", "food_fragment_count",
    "food_top_ratio", "food_bottom_ratio", "food_left_ratio", "food_right_ratio",
    "waste_spatial_entropy",
    "waste_rate_capped", "waste_ratio_capped", "waste_level_int",
]

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

val_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])


class WasteCauseDataset(Dataset):
    def __init__(self, df, label_to_idx, feature_cols):
        self.df = df.reset_index(drop=True)
        self.label_to_idx = label_to_idx
        self.feature_cols = feature_cols

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        try:
            img = Image.open(row["image_path"]).convert("RGB")
        except Exception:
            img = Image.new("RGB", (224, 224), color=(128, 128, 128))
        img = val_transform(img)
        feats = torch.tensor(row[self.feature_cols].fillna(0).values.astype(np.float32))
        label = self.label_to_idx[row["cause_label"]]
        return img, feats, label


def infer_resnet_variant(state_dict):
    """从 checkpoint 的 visual_fc.0.weight 输入维度推断 resnet 变体"""
    w = state_dict["visual_fc.0.weight"]
    in_dim = w.shape[1]
    if in_dim == 2048:
        return "resnet50"
    elif in_dim == 512:
        return "resnet18"
    else:
        raise ValueError(f"无法推断 resnet_variant，visual_fc 输入维度 {in_dim}")


def main():
    print(f"使用数据: {CSV_FILE}")
    if not os.path.exists(CSV_FILE):
        print(f"❌ 数据文件不存在: {CSV_FILE}")
        sys.exit(1)

    df = pd.read_csv(CSV_FILE)
    print(f"总样本数: {len(df)}")

    # 检查图片文件是否存在（图片缺失会导致视觉分支失效、结果不可靠）
    img_exist = df["image_path"].apply(lambda p: os.path.exists(p))
    exist_rate = img_exist.mean()
    print(f"图片文件存在率: {exist_rate*100:.1f}%")
    if exist_rate < 0.5:
        print("⚠️ 警告：大部分图片文件不存在（image_path 指向旧路径），视觉特征将失效！")
        print("   混淆矩阵结果不可靠。请从 CloudStudio 云端训练日志获取混淆矩阵，")
        print("   或修复 CSV 中的 image_path 指向本地实际图片路径后重跑。")

    # 与训练一致：排除无餐盘，合并油腻
    df = df[df["cause_label"] != "无餐盘/空盘"].copy()
    df["cause_label"] = df["cause_label"].replace("油腻不适", "口味偏好/菜品质量")

    labels = sorted(df["cause_label"].unique())
    label_to_idx = {l: i for i, l in enumerate(labels)}
    idx_to_label = {i: l for l, i in label_to_idx.items()}
    num_classes = len(labels)
    print(f"类别数: {num_classes} -> {label_to_idx}")

    # 与训练一致的数据划分（分层抽样）
    train_df, temp_df = stratified_train_test_split(df, test_size=0.25, seed=RANDOM_SEED)
    val_df, test_df = stratified_train_test_split(temp_df, test_size=0.4, seed=RANDOM_SEED)
    print(f"训练集 {len(train_df)} | 验证集 {len(val_df)} | 测试集 {len(test_df)}")

    test_ds = WasteCauseDataset(test_df, label_to_idx, STRUCTURED_FEATURE_COLS)
    test_loader = DataLoader(test_ds, batch_size=32, shuffle=False)

    # 加载模型（自动推断 resnet_variant）
    print(f"加载模型: {MODEL_PATH}")
    checkpoint = torch.load(MODEL_PATH, map_location="cpu")
    if "model_state_dict" in checkpoint:
        state_dict = checkpoint["model_state_dict"]
    else:
        state_dict = checkpoint
    resnet_variant = infer_resnet_variant(state_dict)
    print(f"推断 resnet_variant: {resnet_variant}")

    model = WasteCauseClassifier(
        structured_dim=len(STRUCTURED_FEATURE_COLS),
        num_classes=num_classes,
        resnet_variant=resnet_variant,
        pretrained=False,
    )
    model.load_state_dict(state_dict)
    model.eval()

    # 预测
    all_preds, all_labels = [], []
    with torch.no_grad():
        for img, feats, label in test_loader:
            out = model(img, feats)
            preds = out.argmax(dim=1)
            all_preds.extend(preds.tolist())
            all_labels.extend(label.tolist())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    acc = (all_preds == all_labels).mean()
    print(f"测试集准确率: {acc:.4f}")

    # 混淆矩阵
    cm = build_confusion_matrix(all_labels, all_preds, num_classes)
    class_names = [idx_to_label[i] for i in range(num_classes)]

    # 绘图
    plt.figure(figsize=(7, 6))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=class_names, yticklabels=class_names,
                cbar_kws={"label": "样本数"})
    plt.xlabel("预测类别", fontsize=12)
    plt.ylabel("真实类别", fontsize=12)
    plt.title(f"弃因分类混淆矩阵（测试集 {len(test_df)} 张，准确率 {acc*100:.1f}%）", fontsize=13)
    plt.tight_layout()
    plt.savefig(OUTPUT_PNG, dpi=200, bbox_inches="tight")
    print(f"✅ 混淆矩阵已保存: {OUTPUT_PNG}")
    print(f"类别顺序: {class_names}")


if __name__ == "__main__":
    main()
