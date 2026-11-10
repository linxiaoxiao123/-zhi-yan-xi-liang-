#!/bin/bash
# ==========================================
# 云GPU训练一键脚本
# 用法: bash cloud_run.sh
# 环境: Ubuntu 20.04/22.04 + CUDA 12.x GPU
# ==========================================
set -e

echo "=========================================="
echo "  智眼惜粮 - 弃因分析模型训练 (云GPU版)"
echo "=========================================="

# ---- 1. 环境检查 ----
echo "[1/6] 检查GPU..."
nvidia-smi | head -5
python -c "import torch; print('PyTorch CUDA:', torch.cuda.is_available())" || {
    echo "ERROR: PyTorch未安装或CUDA不可用"
    exit 1
}

# ---- 2. 安装依赖 (如果缺失) ----
echo "[2/6] 安装Python依赖..."
pip install pandas numpy opencv-python pillow scikit-learn tqdm matplotlib \
    ultralytics albumentations torchvision --quiet 2>&1 | tail -3
echo "      依赖就绪"

# ---- 3. 特征口径统一 + 数据增强 (云GPU加速!) ----
echo "[3/6] 特征口径统一（新公式 food/(food+plate)）..."
python recompute_features.py
echo "      口径统一完成"
echo "[3/6] 数据增强 ×9 (云GPU加速中)..."
python augment_dataset.py
echo "      增强完成"

# ---- 4. 模型训练 ----
echo "[4/6] 开始训练 ResNet-18 多模态融合模型..."
python train_waste_cause.py
echo "      训练完成"

# ---- 5. 验证 ----
echo "[5/6] 验证模型文件..."
if [ -f "model/waste_cause_3cls.pth" ]; then
    echo "      ✅ waste_cause_3cls.pth 已生成"
    ls -lh model/waste_cause_3cls.pth
else
    echo "      ❌ 模型文件未生成!"
    exit 1
fi

if [ -f "training_curves.png" ]; then
    echo "      ✅ training_curves.png 已生成"
fi

# ---- 6. 推理测试 ----
echo "[6/6] 推理测试..."
python -c "
from waste_cause_inference import predict_with_rules
# 规则测试
r1 = predict_with_rules({'detected_count': 0, 'oil_ratio': 0}, None)
print(f'  空盘检测: {r1[\"cause\"]}')
r2 = predict_with_rules({'detected_count': 3, 'oil_ratio': 0.05}, None)
print(f'  油腻检测: {r2[\"cause\"]}')
print('  推理模块正常')
"

echo ""
echo "=========================================="
echo "  🎉 训练全部完成!"
echo "  模型: model/waste_cause_3cls.pth"
echo "  曲线: training_curves.png"
echo "  下载这两个文件到本地即可"
echo "=========================================="
