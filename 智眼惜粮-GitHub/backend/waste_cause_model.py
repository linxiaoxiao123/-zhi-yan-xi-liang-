"""
多模态弃因分类模型: ResNet(视觉特征) + 结构化特征 → MLP融合分类
支持: resnet18 / resnet34 / resnet50
"""
import torch
import torch.nn as nn
import torchvision.models as models


class StructuredEncoder(nn.Module):
    """将结构化特征编码为128维向量"""

    def __init__(self, input_dim, hidden_dim=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(64, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)


class WasteCauseClassifier(nn.Module):
    """多模态融合分类器"""

    def __init__(self, structured_dim, num_classes, resnet_variant="resnet18", pretrained=True):
        super().__init__()

        resnet_config = {
            "resnet18": (models.resnet18, 512),
            "resnet34": (models.resnet34, 512),
            "resnet50": (models.resnet50, 2048),
        }
        if resnet_variant not in resnet_config:
            raise ValueError(f"不支持的ResNet变体: {resnet_variant}，可选: {list(resnet_config.keys())}")

        backbone_fn, self.visual_dim = resnet_config[resnet_variant]
        try:
            backbone = backbone_fn(weights="IMAGENET1K_V1" if pretrained else None)
        except Exception as e:
            print(f"⚠ 预训练权重下载失败，使用随机初始化: {e}")
            backbone = backbone_fn(weights=None)

        # 去掉最后的fc层
        self.visual_backbone = nn.Sequential(*list(backbone.children())[:-1])
        self.visual_fc = nn.Sequential(
            nn.Linear(self.visual_dim, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
        )

        # 结构化特征编码器
        self.structured_encoder = StructuredEncoder(structured_dim, hidden_dim=128)

        # 融合分类头
        fusion_dim = 256 + 128
        self.classifier = nn.Sequential(
            nn.Linear(fusion_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.4),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.Linear(64, num_classes),
        )

    def forward(self, image, structured_features):
        v = self.visual_backbone(image)
        v = torch.flatten(v, 1)
        v = self.visual_fc(v)

        s = self.structured_encoder(structured_features)

        fused = torch.cat([v, s], dim=1)
        logits = self.classifier(fused)
        return logits
