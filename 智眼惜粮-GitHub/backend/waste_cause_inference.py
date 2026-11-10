"""
弃因推理模块 —— 加载训练好的ResNet-18+MLP模型，对新图片做弃因预测
"""
import os
import numpy as np
from PIL import Image

import torch
from torchvision import transforms

from waste_cause_model import WasteCauseClassifier

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model", "waste_cause_3cls.pth")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

img_transform = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])

# 与训练时一致的特征列顺序
FEATURE_COLS = [
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

_model = None
_label_to_idx = None
_idx_to_label = None


def _load_model():
    """懒加载模型"""
    global _model, _label_to_idx, _idx_to_label
    if _model is not None:
        return

    checkpoint = torch.load(MODEL_PATH, map_location=DEVICE, weights_only=False)
    _label_to_idx = checkpoint["label_to_idx"]
    _idx_to_label = {v: k for k, v in _label_to_idx.items()}
    num_classes = checkpoint["num_classes"]
    feature_dim = len(checkpoint["feature_cols"])

    # 从 checkpoint 自动推断 resnet 变体（visual_fc.0.weight 输入维度：512=resnet18, 2048=resnet50）
    fc_shape = checkpoint["model_state_dict"]["visual_fc.0.weight"].shape
    resnet_variant = "resnet50" if fc_shape[1] == 2048 else "resnet18"

    _model = WasteCauseClassifier(
        structured_dim=feature_dim,
        num_classes=num_classes,
        resnet_variant=resnet_variant,
        pretrained=False,
    ).to(DEVICE)
    _model.load_state_dict(checkpoint["model_state_dict"])
    _model.eval()


def predict(image: Image.Image, features: dict) -> dict:
    """
    预测单张图片的弃因

    参数:
        image: PIL Image (RGB)
        features: 字典，包含FEATURE_COLS中的所有键

    返回:
        {"cause": "正常范围", "confidence": 0.95, "all_probs": {...}}
    """
    _load_model()

    # 图像预处理
    img_tensor = img_transform(image).unsqueeze(0).to(DEVICE)

    # 结构化特征 → 按FEATURE_COLS顺序组装
    feat_values = []
    for col in FEATURE_COLS:
        val = features.get(col, 0)
        feat_values.append(float(val) if val is not None else 0.0)
    feat_tensor = torch.tensor([feat_values], dtype=torch.float32).to(DEVICE)

    with torch.no_grad():
        logits = _model(img_tensor, feat_tensor)
        probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()

    pred_idx = int(np.argmax(probs))
    cause = _idx_to_label[pred_idx]
    confidence = round(float(probs[pred_idx]), 4)

    all_probs = {_idx_to_label[i]: round(float(p), 4) for i, p in enumerate(probs)}

    return {"cause": cause, "confidence": confidence, "all_probs": all_probs}


def predict_with_rules(features: dict, image: Image.Image = None) -> dict:
    """
    带规则前置的预测:
    1. detected_count == 0 → 无餐盘/空盘
    2. oil_pixels 超阈值 → 油腻不适
    3. 其余 → 模型预测3分类
    """
    detected_count = features.get("detected_count", 0)
    oil_pixels = features.get("oil_pixels", 0)

    if detected_count == 0:
        return {"cause": "无餐盘/空盘", "confidence": 1.0, "rule_match": True,
                "all_probs": {"无餐盘/空盘": 1.0}}

    # 油腻不适：oil_pixels 是被连通域过滤掉的 <100px 细碎残渣像素，并非真正的油渍。
    # 用绝对像素阈值而非 oil_ratio>0，避免米粒/菜渣等正常碎渣被误判成油腻。
    if oil_pixels > 2000:
        return {"cause": "油腻不适", "confidence": 0.9, "rule_match": True,
                "all_probs": {"油腻不适": 0.9}}

    if image is None:
        return {"cause": "正常范围", "confidence": 0.0, "rule_match": False,
                 "all_probs": {}}

    result = predict(image, features)
    result["rule_match"] = False
    return result
