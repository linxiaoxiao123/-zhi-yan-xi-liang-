# -*- coding: utf-8 -*-
"""用云端训练日志的混淆矩阵画热力图（论文图 6-2）
矩阵来源：CloudStudio 训练日志（测试集 302 张，准确率 98.7%）
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

# 混淆矩阵（行=真实类别，列=预测类别；顺序：份量过大、口味偏好/菜品质量、正常范围）
cm = np.array([
    [76, 0, 0],
    [0, 61, 0],
    [4, 0, 161],
])
labels = ["份量过大", "口味偏好/菜品质量", "正常范围"]

acc = cm.diagonal().sum() / cm.sum()
print(f"准确率: {acc:.4f}（{cm.diagonal().sum()}/{cm.sum()}）")

plt.figure(figsize=(7, 6))
ax = sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                 xticklabels=labels, yticklabels=labels,
                 annot_kws={"size": 18, "weight": "bold"},
                 linewidths=0.8, linecolor="white",
                 cbar_kws={"label": "样本数"})
ax.set_xlabel("预测类别", fontsize=13)
ax.set_ylabel("真实类别", fontsize=13)
ax.set_title(f"弃因分类混淆矩阵（测试集 {cm.sum()} 张，准确率 {acc*100:.1f}%）", fontsize=14)
ax.tick_params(axis="both", labelsize=12)
plt.tight_layout()
plt.savefig("confusion_matrix.png", dpi=200, bbox_inches="tight")
print("✅ 已保存 confusion_matrix.png")
