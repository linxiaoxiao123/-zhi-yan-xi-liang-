"""
聚类生成弃因伪标签
运行方式: python cluster_labels.py
输入: waste_cause_features.csv
输出: waste_cause_features_labeled.csv (新增cluster列)
      cluster_summary.png (每个聚类的可视化摘要)
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

# ========== 配置 ==========
N_CLUSTERS = 5          # 聚成几类，6-8比较合适，先试6
RANDOM_SEED = 42
INPUT_CSV = "waste_cause_features.csv"
OUTPUT_CSV = "waste_cause_features_labeled.csv"
OUTPUT_PNG = "cluster_summary.png"

# ========== 1. 加载数据 ==========
print("[1/4] 加载特征数据...")
df = pd.read_csv(INPUT_CSV)
print(f"       数据形状: {df.shape}")

# ========== 2. 修复：浪费率截断到0-100，修正waste_level_int ==========
# 原始waste_rate_raw可能>100%（U-Net分割异常），截断后再聚类
df["waste_rate_capped"] = df["waste_rate_raw"].clip(0, 100)
df["waste_ratio_capped"] = df["waste_ratio"].clip(0, 1.0)
# 重新计算浪费等级
df["waste_level_int"] = 0
df.loc[df["waste_rate_capped"] >= 5, "waste_level_int"] = 1
df.loc[df["waste_rate_capped"] >= 20, "waste_level_int"] = 2

# ========== 3. 选择用于聚类的特征列 ==========
exclude_cols = ["filename", "image_path", "detected_dishes", "waste_level",
                "waste_rate_raw", "waste_ratio",  # 用截断版替代
                ]
feature_cols = [c for c in df.columns
                if c not in exclude_cols
                and df[c].dtype in ['int64', 'float64', 'int32']]
print(f"       用于聚类的特征: {len(feature_cols)} 维")
print(f"       {feature_cols}")

X = df[feature_cols].copy()
X = X.fillna(0)

# ========== 3. 标准化 + 聚类 ==========
print(f"[2/4] KMeans聚类 (k={N_CLUSTERS})...")
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_SEED, n_init=10, max_iter=300)
df["cluster"] = kmeans.fit_predict(X_scaled)

# ========== 4. 分析每个聚类 ==========
print("[3/4] 分析聚类结果...\n")
rice_kw = ["米饭", "米", "饭"]
meat_kw = ["肉", "鸡", "鸭", "鱼", "虾", "猪", "牛", "蛋", "翅", "腿", "丸", "排"]
veg_kw = ["菜", "茄", "豆", "菇", "瓜", "椒", "蔬", "笋", "菌", "粉"]

for c in range(N_CLUSTERS):
    cluster_data = df[df["cluster"] == c]
    n_samples = len(cluster_data)
    pct = n_samples / len(df) * 100

    avg_waste = cluster_data["waste_rate_capped"].mean()
    avg_food_px = cluster_data["food_pixels"].mean()
    avg_oil = cluster_data["oil_ratio"].mean()
    avg_count = cluster_data["detected_count"].mean()

    # 统计高频菜品
    all_dishes = []
    for dishes_str in cluster_data["detected_dishes"].dropna():
        all_dishes.extend(dishes_str.split("|"))
    top_dishes = Counter(all_dishes).most_common(5)
    top_dishes_str = ", ".join([f"{d}({c}次)" for d, c in top_dishes])

    # 浪费等级分布
    waste_dist = cluster_data["waste_level"].value_counts().to_dict()

    # 米饭和肉类比例
    has_rice_pct = cluster_data["has_rice"].mean() * 100

    print(f"{'='*60}")
    print(f"聚类 {c}: {n_samples} 样本 ({pct:.1f}%)")
    print(f"  平均浪费率(raw): {avg_waste:.1f}%")
    print(f"  平均食物像素: {avg_food_px:.0f}")
    print(f"  平均油渍比: {avg_oil:.4f}")
    print(f"  平均检测菜品数: {avg_count:.1f}")
    print(f"  含米饭比例: {has_rice_pct:.0f}%")
    print(f"  浪费分布(low/med/high): {waste_dist}")
    print(f"  TOP5高频菜品: {top_dishes_str}")
    print()

# ========== 5. PCA可视化 ==========
print("[4/4] 生成PCA可视化...")
pca = PCA(n_components=2, random_state=RANDOM_SEED)
X_pca = pca.fit_transform(X_scaled)

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# 图1：聚类散点图
scatter = axes[0].scatter(X_pca[:, 0], X_pca[:, 1], c=df["cluster"],
                          cmap="tab10", alpha=0.6, s=20)
axes[0].set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})")
axes[0].set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})")
axes[0].set_title(f"KMeans Clustering (k={N_CLUSTERS})")
plt.colorbar(scatter, ax=axes[0], label="Cluster")

# 图2：各聚类的浪费率分布
for c in range(N_CLUSTERS):
    c_data = df[df["cluster"] == c]["waste_rate_capped"]
    axes[1].hist(c_data, bins=25, alpha=0.5, label=f"Cluster {c} (n={len(c_data)})")
axes[1].set_xlabel("Waste Rate (%)")
axes[1].set_ylabel("Count")
axes[1].set_title("Waste Rate Distribution by Cluster")
axes[1].legend(fontsize=8)

plt.tight_layout()
plt.savefig(OUTPUT_PNG, dpi=150)
print(f"       图表已保存: {OUTPUT_PNG}")

# ========== 6. 保存 ==========
df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
print(f"       数据已保存: {OUTPUT_CSV}")

# 肘部法则——帮用户判断k值是否合理
print(f"\n各聚类样本分布:")
for c in range(N_CLUSTERS):
    print(f"  聚类 {c}: {len(df[df['cluster']==c])} 样本")
print(f"\n现在打开 {OUTPUT_PNG} 查看聚类效果。")
print(f"然后根据每个聚类的特征，给它们命名弃因（口味偏好/份量过大/油腻不适/整体质量/正常范围/搭配不当）。")
