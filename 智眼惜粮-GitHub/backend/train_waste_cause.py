"""
训练多模态弃因分类模型
运行方式: python train_waste_cause.py
"""
import os
import numpy as np
import pandas as pd
from collections import Counter
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from tqdm import tqdm

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from waste_cause_model import WasteCauseClassifier
from cloud_train_config import get_config as get_cloud_config

# ========== 配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "waste_cause_features_augmented.csv")
# 如果增强数据不存在，回退到原始数据
if not os.path.exists(CSV_FILE):
    CSV_FILE = os.path.join(BASE_DIR, "waste_cause_features_labeled.csv")
MODEL_SAVE_PATH = os.path.join(BASE_DIR, "model", "waste_cause_3cls.pth")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
RANDOM_SEED = 42
torch.manual_seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

BATCH_SIZE = 32  # 增大batch size（数据量增加了）
NUM_EPOCHS = 60  # 多给一些epoch，early stopping会自动提前结束
LEARNING_RATE = 3e-5   # 降低学习率，更稳定收敛
WEIGHT_DECAY = 1e-4
EARLY_STOP_PATIENCE = 15  # 配合低学习率，多给耐心

# 训练模式: "fusion" | "structured_only" | "visual_only"
TRAIN_MODE = "fusion"

# ImageNet标准化参数
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

# 结构化特征列
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

# 图像预处理
train_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
    transforms.RandomHorizontalFlip(),
    transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1, hue=0.05),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])

val_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])


class WasteCauseDataset(Dataset):
    def __init__(self, df, label_to_idx, feature_cols, is_train=True):
        self.df = df.reset_index(drop=True)
        self.label_to_idx = label_to_idx
        self.feature_cols = feature_cols
        self.transform = train_transform if is_train else val_transform
        self.is_train = is_train

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        # 图像
        img_path = row["image_path"]
        try:
            img = Image.open(img_path).convert("RGB")
        except Exception:
            img = Image.new("RGB", (224, 224), color=(128, 128, 128))
        img = self.transform(img)

        # 结构化特征
        feats = row[self.feature_cols].fillna(0).values.astype(np.float32)
        feats = torch.tensor(feats, dtype=torch.float32)

        # 标签
        label = self.label_to_idx[row["cause_label"]]

        return img, feats, label


def compute_class_weights(labels, num_classes):
    """计算类别权重用于平衡损失函数"""
    counts = Counter(labels)
    weights = torch.zeros(num_classes, dtype=torch.float32)
    for cls, count in counts.items():
        weights[cls] = len(labels) / (num_classes * count)
    return weights


def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for images, feats, labels in tqdm(loader, desc="Train", leave=False):
        images, feats, labels = images.to(device), feats.to(device), labels.to(device)

        optimizer.zero_grad()
        logits = model(images, feats)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)
        correct += (logits.argmax(1) == labels).sum().item()
        total += images.size(0)

    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    all_preds, all_labels = [], []
    for images, feats, labels in loader:
        images, feats, labels = images.to(device), feats.to(device), labels.to(device)
        logits = model(images, feats)
        loss = criterion(logits, labels)

        total_loss += loss.item() * images.size(0)
        preds = logits.argmax(1)
        correct += (preds == labels).sum().item()
        total += images.size(0)
        all_preds.extend(preds.cpu().tolist())
        all_labels.extend(labels.cpu().tolist())

    return total_loss / total, correct / total, all_preds, all_labels


def plot_training_curves(history, save_path):
    """绘制训练曲线：Loss + Accuracy"""
    epochs = list(range(1, len(history["train_loss"]) + 1))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Loss曲线
    axes[0].plot(epochs, history["train_loss"], "b-", label="Train Loss", linewidth=1.5)
    axes[0].plot(epochs, history["val_loss"], "r-", label="Val Loss", linewidth=1.5)
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].set_title("Training & Validation Loss")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Accuracy曲线
    axes[1].plot(epochs, history["train_acc"], "b-", label="Train Acc", linewidth=1.5)
    axes[1].plot(epochs, history["val_acc"], "r-", label="Val Acc", linewidth=1.5)
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].set_title("Training & Validation Accuracy")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    # 标注最佳epoch
    best_epoch = history["best_epoch"]
    best_val = history["best_val_acc"]
    axes[1].axvline(x=best_epoch, color="g", linestyle="--", alpha=0.6, label=f"Best (epoch {best_epoch}, acc={best_val:.3f})")
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    print(f"训练曲线已保存: {save_path}")


def main():
    cloud_cfg = get_cloud_config()

    print(f"设备: {DEVICE}")
    print(f"训练模式: {TRAIN_MODE} | ResNet: {cloud_cfg['resnet_variant']} | "
          f"Batch: {cloud_cfg['batch_size']} | LR: {cloud_cfg['learning_rate']}")

    # ===== 1. 加载数据 =====
    df = pd.read_csv(CSV_FILE)
    print(f"总样本数: {len(df)}")

    # 排除"无餐盘/空盘"（推理时用规则过滤: detected_count==0 → 无餐盘）
    df = df[df["cause_label"] != "无餐盘/空盘"].copy()

    # 合并"油腻不适"→"口味偏好/菜品质量"（oil_ratio>0可直接区分）
    df["cause_label"] = df["cause_label"].replace("油腻不适", "口味偏好/菜品质量")

    # 构建标签映射
    labels = sorted(df["cause_label"].unique())
    label_to_idx = {l: i for i, l in enumerate(labels)}
    idx_to_label = {i: l for l, i in label_to_idx.items()}
    num_classes = len(labels)
    print(f"类别数: {num_classes}")
    for l, i in label_to_idx.items():
        n = len(df[df["cause_label"] == l])
        print(f"  {i}: {l} ({n}张)")

    # ===== 2. 划分数据集 =====
    train_df, temp_df = train_test_split(df, test_size=0.25, random_state=RANDOM_SEED,
                                         stratify=df["cause_label"])
    val_df, test_df = train_test_split(temp_df, test_size=0.4, random_state=RANDOM_SEED,
                                       stratify=temp_df["cause_label"])
    print(f"训练集: {len(train_df)} | 验证集: {len(val_df)} | 测试集: {len(test_df)}")

    train_ds = WasteCauseDataset(train_df, label_to_idx, STRUCTURED_FEATURE_COLS, is_train=True)
    val_ds = WasteCauseDataset(val_df, label_to_idx, STRUCTURED_FEATURE_COLS, is_train=False)
    test_ds = WasteCauseDataset(test_df, label_to_idx, STRUCTURED_FEATURE_COLS, is_train=False)

    train_loader = DataLoader(train_ds, batch_size=cloud_cfg["batch_size"], shuffle=True,
                              num_workers=cloud_cfg["num_workers"])
    val_loader = DataLoader(val_ds, batch_size=cloud_cfg["batch_size"], shuffle=False,
                            num_workers=cloud_cfg["num_workers"])
    test_loader = DataLoader(test_ds, batch_size=cloud_cfg["batch_size"], shuffle=False,
                             num_workers=cloud_cfg["num_workers"])

    # ===== 3. 初始化模型 =====
    model = WasteCauseClassifier(
        structured_dim=len(STRUCTURED_FEATURE_COLS),
        num_classes=num_classes,
        resnet_variant=cloud_cfg["resnet_variant"],
        pretrained=True,
    ).to(DEVICE)

    # 如果只用结构化特征，冻结ResNet
    if TRAIN_MODE == "structured_only":
        for p in model.visual_backbone.parameters():
            p.requires_grad = False
        for p in model.visual_fc.parameters():
            p.requires_grad = False
        # 需要绕过visual分支，直接用structured特征分类
        # 这里简化处理：直接替换forward
        print("  结构化特征模式: ResNet已冻结，仅训练structured encoder + classifier")

    # 如果只用视觉特征，冻结structured encoder
    if TRAIN_MODE == "visual_only":
        for p in model.structured_encoder.parameters():
            p.requires_grad = False
        print("  视觉特征模式: structured encoder已冻结")

    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"可训练参数: {total_params:,}")

    # 类别权重
    class_weights = compute_class_weights(
        [label_to_idx[l] for l in train_df["cause_label"]], num_classes
    ).to(DEVICE)
    print(f"类别权重: {class_weights.tolist()}")

    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cloud_cfg["learning_rate"],
                                  weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cloud_cfg["num_epochs"])

    # ===== 4. 训练 =====
    best_val_acc = 0.0
    best_epoch = 0
    patience_counter = 0
    history = {"train_loss": [], "train_acc": [], "val_loss": [], "val_acc": []}

    print("\n开始训练...")
    for epoch in range(1, cloud_cfg["num_epochs"] + 1):
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, DEVICE)
        val_loss, val_acc, _, _ = evaluate(model, val_loader, criterion, DEVICE)

        scheduler.step()

        history["train_loss"].append(train_loss)
        history["train_acc"].append(train_acc)
        history["val_loss"].append(val_loss)
        history["val_acc"].append(val_acc)

        lr = scheduler.get_last_lr()[0]
        print(f"Epoch {epoch:2d}/{NUM_EPOCHS} | "
              f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.3f} | "
              f"Val Loss: {val_loss:.4f} | Val Acc: {val_acc:.3f} | lr: {lr:.2e}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch
            patience_counter = 0
            os.makedirs(os.path.dirname(MODEL_SAVE_PATH), exist_ok=True)
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_acc": val_acc,
                "label_to_idx": label_to_idx,
                "feature_cols": STRUCTURED_FEATURE_COLS,
                "num_classes": num_classes,
                "train_mode": TRAIN_MODE,
            }, MODEL_SAVE_PATH)
        else:
            patience_counter += 1
            if patience_counter >= EARLY_STOP_PATIENCE:
                print(f"\nEarly stopping at epoch {epoch} (最佳: epoch {best_epoch}, val_acc={best_val_acc:.3f})")
                break

    history["best_epoch"] = best_epoch
    history["best_val_acc"] = best_val_acc

    # 绘制训练曲线
    curve_path = os.path.join(BASE_DIR, "training_curves.png")
    plot_training_curves(history, curve_path)

    # ===== 5. 测试 =====
    print(f"\n加载最佳模型 (epoch {best_epoch})...")
    checkpoint = torch.load(MODEL_SAVE_PATH, map_location=DEVICE)
    model.load_state_dict(checkpoint["model_state_dict"])

    test_loss, test_acc, all_preds, all_labels = evaluate(model, test_loader, criterion, DEVICE)
    print(f"\n测试集准确率: {test_acc:.3f}")
    print(f"\n分类报告:")
    print(classification_report(all_labels, all_preds, target_names=[idx_to_label[i] for i in range(num_classes)], zero_division=0))

    cm = confusion_matrix(all_labels, all_preds)
    print(f"混淆矩阵:")
    print("          " + " ".join(f"{idx_to_label[i]:6s}" for i in range(num_classes)))
    for i in range(num_classes):
        print(f"{idx_to_label[i]:8s} " + " ".join(f"{cm[i][j]:6d}" for j in range(num_classes)))

    print(f"\n模型已保存: {MODEL_SAVE_PATH}")


if __name__ == "__main__":
    main()
