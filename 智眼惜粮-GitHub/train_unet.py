# train_unet.py
import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import albumentations as A
from albumentations.pytorch import ToTensorV2
import cv2
import numpy as np
from tqdm import tqdm
import shutil
import tempfile
import csv
import matplotlib
matplotlib.use('Agg')  # 无界面/服务器环境也能保存图片
import matplotlib.pyplot as plt

# ----------------------------
# 使用 segmentation_models_pytorch 的 UNet（推荐小数据集）
# ----------------------------
import segmentation_models_pytorch as smp

def get_pretrained_unet(n_classes=1):
    """使用 ResNet34 作为 backbone 的 UNet，适合小数据集"""
    return smp.Unet(
        encoder_name="resnet34",
        encoder_weights="imagenet",  # 预训练权重，提升泛化
        in_channels=3,
        classes=n_classes,
        activation=None  # 输出 logits，配合 BCEWithLogitsLoss
    )

# ----------------------------
# 数据集类
# ----------------------------
class SegmentationDataset(Dataset):
    def __init__(self, image_dir, mask_dir, transform=None):
        self.image_dir = image_dir
        self.mask_dir = mask_dir
        self.transform = transform
        self.images = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        img_name = self.images[idx]
        img_path = os.path.join(self.image_dir, img_name)
        # 掩码文件名与原图同名（如 001.jpg → 001.png）
        mask_path = os.path.join(self.mask_dir, os.path.splitext(img_name)[0] + '.png')

        image = cv2.imread(img_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            mask = np.zeros((image.shape[0], image.shape[1]), dtype=np.uint8)

        if self.transform:
            augmented = self.transform(image=image, mask=mask)
            image = augmented['image']
            mask = augmented['mask']

        # 转为 0/1 浮点张量 [1, H, W]
        mask = (mask / 255.0).astype(np.float32)
        return image, mask[np.newaxis, :, :]

# ----------------------------
# 训练与验证函数
# ----------------------------
def train_one_epoch(model, dataloader, optimizer, criterion, device, accumulation_steps=1):
    model.train()
    total_loss = 0
    optimizer.zero_grad()
    for i, (images, masks) in enumerate(tqdm(dataloader, desc="Training")):
        images, masks = images.to(device), masks.to(device)
        outputs = model(images)
        loss = criterion(outputs, masks) / accumulation_steps
        loss.backward()

        if (i + 1) % accumulation_steps == 0:
            optimizer.step()
            optimizer.zero_grad()

        total_loss += loss.item() * accumulation_steps
    return total_loss / len(dataloader)

@torch.no_grad()
def validate(model, dataloader, criterion, device):
    model.eval()
    total_loss = 0
    for images, masks in dataloader:
        images, masks = images.to(device), masks.to(device)
        outputs = model(images)
        loss = criterion(outputs, masks)
        total_loss += loss.item()
    return total_loss / len(dataloader)

# ----------------------------
# 保存 loss 日志（CSV）+ 绘制曲线（PNG）
# ----------------------------
def save_loss_log_and_plot(task_name, save_path, history):
    """把每轮 train/val loss 写成 CSV，并绘制训练/验证双线曲线。"""
    out_dir = os.path.dirname(save_path)
    os.makedirs(out_dir, exist_ok=True)

    csv_path = os.path.join(out_dir, f"{task_name}_loss_log.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "train_loss", "val_loss"])
        for r in history:
            w.writerow([r["epoch"], f"{r['train_loss']:.6f}", f"{r['val_loss']:.6f}"])
    print(f"📄 损失日志已保存: {csv_path}")

    if not history:
        return

    epochs = [r["epoch"] for r in history]
    train_losses = [r["train_loss"] for r in history]
    val_losses = [r["val_loss"] for r in history]

    plt.figure(figsize=(8, 5))
    plt.plot(epochs, train_losses, marker="o", ms=3, label="Train Loss")
    plt.plot(epochs, val_losses, marker="s", ms=3, label="Val Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title(f"{task_name} Training Loss Curve")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    fig_path = os.path.join(out_dir, f"{task_name}_loss_curve.png")
    plt.savefig(fig_path, dpi=120)
    plt.close()
    print(f"📈 损失曲线已保存: {fig_path}")

def _link_or_copy(src, dst):
    """优先用软链接(省空间/快)，Windows 无权限时自动退化为复制，避免直接崩。"""
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError, AttributeError):
        shutil.copy(src, dst)


# ----------------------------
# 主训练函数（带早停）
# ----------------------------
def train_model(task_name, image_dir, mask_dir, save_path, epochs=50, batch_size=4):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🚀 训练 {task_name} | 设备: {device}")

    # 强数据增强（防过拟合）
    train_transform = A.Compose([
        A.Resize(512, 512),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.3),
        A.RandomRotate90(p=0.4),
        A.ShiftScaleRotate(shift_limit=0.15, scale_limit=0.3, rotate_limit=25, p=0.5),
        A.ElasticTransform(alpha=120, sigma=12, alpha_affine=15, p=0.25),
        A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.25),
        A.RandomBrightnessContrast(p=0.4),
        A.HueSaturationValue(p=0.3),
        A.GaussNoise(var_limit=(10.0, 60.0), p=0.2),
        A.Blur(blur_limit=3, p=0.15),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2()
    ])
    val_transform = A.Compose([
        A.Resize(512, 512),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2()
    ])

    # 划分训练/验证集（8:2）
    all_images = sorted(os.listdir(image_dir))
    split = int(0.8 * len(all_images))
    train_images = all_images[:split]
    val_images = all_images[split:]

    # 创建临时符号链接（避免复制数据）
    temp_dir = tempfile.mkdtemp()
    dirs = ["train_images", "train_masks", "val_images", "val_masks"]
    paths = [os.path.join(temp_dir, d) for d in dirs]
    for p in paths:
        os.makedirs(p)

    for img in train_images:
        _link_or_copy(os.path.join(image_dir, img), os.path.join(paths[0], img))
        _link_or_copy(os.path.join(mask_dir, os.path.splitext(img)[0] + '.png'), os.path.join(paths[1], os.path.splitext(img)[0] + '.png'))
    for img in val_images:
        _link_or_copy(os.path.join(image_dir, img), os.path.join(paths[2], img))
        _link_or_copy(os.path.join(mask_dir, os.path.splitext(img)[0] + '.png'), os.path.join(paths[3], os.path.splitext(img)[0] + '.png'))

    # 数据加载器
    train_dataset = SegmentationDataset(paths[0], paths[1], transform=train_transform)
    val_dataset = SegmentationDataset(paths[2], paths[3], transform=val_transform)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=4, pin_memory=True)

    # 模型、优化器、损失
    model = get_pretrained_unet(n_classes=1).to(device)
    optimizer = optim.Adam(model.parameters(), lr=1e-4)
    criterion = nn.BCEWithLogitsLoss()

    # 早停配置
    patience = 10
    best_val_loss = float('inf')
    trigger_times = 0
    accumulation_steps = 2  # 模拟 batch_size=8

    history = []  # 记录每轮 loss，用于写日志 / 画曲线
    for epoch in range(epochs):
        train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device, accumulation_steps)
        val_loss = validate(model, val_loader, criterion, device)
        print(f"Epoch {epoch+1}/{epochs} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
        history.append({"epoch": epoch+1, "train_loss": train_loss, "val_loss": val_loss})

        # 保存最佳模型（同时保留带 epoch/loss 的命名文件，便于回溯/重建曲线）
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            trigger_times = 0
            torch.save(model.state_dict(), save_path)
            named_path = os.path.join(
                os.path.dirname(save_path),
                f"{task_name}_segment_best_epoch{epoch+1}_loss{val_loss:.4f}.pth"
            )
            torch.save(model.state_dict(), named_path)
            print(f"✅ 保存最佳模型: {named_path}")
        else:
            trigger_times += 1
            if trigger_times >= patience:
                print("🛑 早停触发，训练结束")
                break

    # 保存 loss 日志（CSV）并绘制曲线（PNG）
    save_loss_log_and_plot(task_name, save_path, history)

    # 清理临时目录
    shutil.rmtree(temp_dir)
    print(f"🎉 {task_name} 模型训练完成！")

# ----------------------------
# 主程序
# ----------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="U-Net 餐盘/残余菜品分割训练")
    parser.add_argument("--dataset", default="./dataset",
                        help="数据集根目录（含 images/masks_plate/masks_residual）")
    parser.add_argument("--model_dir", default="./model",
                        help="模型与曲线输出目录")
    parser.add_argument("--epochs", type=int, default=50, help="训练轮数")
    parser.add_argument("--batch_size", type=int, default=4, help="批大小")
    args = parser.parse_args()

    DATASET_DIR = args.dataset
    IMAGE_DIR = os.path.join(DATASET_DIR, "images")
    MASK_PLATE_DIR = os.path.join(DATASET_DIR, "masks_plate")
    MASK_RESIDUAL_DIR = os.path.join(DATASET_DIR, "masks_residual")
    MODEL_DIR = args.model_dir
    os.makedirs(MODEL_DIR, exist_ok=True)

    # 训练餐盘分割模型
    train_model(
        task_name="plate",
        image_dir=IMAGE_DIR,
        mask_dir=MASK_PLATE_DIR,
        save_path=os.path.join(MODEL_DIR, "plate_unet.pth"),
        epochs=args.epochs,
        batch_size=args.batch_size
    )

    # 训练残余菜品分割模型
    train_model(
        task_name="residual",
        image_dir=IMAGE_DIR,
        mask_dir=MASK_RESIDUAL_DIR,
        save_path=os.path.join(MODEL_DIR, "residual_unet.pth"),
        epochs=args.epochs,
        batch_size=args.batch_size
    )