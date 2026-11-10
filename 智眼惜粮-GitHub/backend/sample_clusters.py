"""
从每个聚类随机采样图片，复制到 cluster_samples/ 目录供人工审查
运行方式: python sample_clusters.py
"""
import pandas as pd
import os
import shutil
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "waste_cause_features_labeled.csv")
OUT_DIR = os.path.join(BASE_DIR, "cluster_samples")
SAMPLES_PER_CLUSTER = 15
RANDOM_SEED = 42

random.seed(RANDOM_SEED)

df = pd.read_csv(CSV_FILE)
print(f"加载数据: {len(df)} 条记录\n")

# 清空并重建输出目录
if os.path.exists(OUT_DIR):
    shutil.rmtree(OUT_DIR)

for c in sorted(df["cluster"].unique()):
    cluster_data = df[df["cluster"] == c]
    n = len(cluster_data)

    # 统计
    avg_waste = cluster_data["waste_rate_capped"].mean()
    avg_dishes = cluster_data["detected_count"].mean()
    rice_pct = cluster_data["has_rice"].mean() * 100
    avg_oil = cluster_data["oil_ratio"].mean()

    print(f"聚类 {c}: {n} 样本 | 平均浪费率={avg_waste:.1f}% | 平均菜品数={avg_dishes:.1f} | 含米饭={rice_pct:.0f}% | 油渍比={avg_oil:.4f}")

    # 随机采样
    sample_n = min(SAMPLES_PER_CLUSTER, n)
    samples = cluster_data.sample(n=sample_n, random_state=RANDOM_SEED)

    cluster_dir = os.path.join(OUT_DIR, f"cluster_{c}")
    os.makedirs(cluster_dir, exist_ok=True)

    for _, row in samples.iterrows():
        src = row["image_path"]
        if os.path.exists(src):
            dst = os.path.join(cluster_dir, row["filename"])
            shutil.copy2(src, dst)

    # 写入该簇的统计信息
    info_path = os.path.join(cluster_dir, "_info.txt")
    with open(info_path, "w", encoding="utf-8") as f:
        f.write(f"聚类 {c} 统计信息\n")
        f.write(f"{'='*40}\n")
        f.write(f"样本数: {n}\n")
        f.write(f"平均浪费率(capped): {avg_waste:.1f}%\n")
        f.write(f"平均检测菜品数: {avg_dishes:.1f}\n")
        f.write(f"含米饭比例: {rice_pct:.0f}%\n")
        f.write(f"平均油渍比: {avg_oil:.4f}\n")
        f.write(f"\n弃因命名: ____________\n")

    print(f"  → 已采样 {sample_n} 张到 {cluster_dir}")

print(f"\n完成! 请打开 {OUT_DIR} 查看各簇的样本图片。")
print(f"每个簇文件夹内有 _info.txt，请在其中填写弃因名称。")
print(f"\n建议的弃因类别: 正常范围 / 口味偏好 / 份量过大 / 油腻不适 / 菜品质量问题 / 搭配不当 / 无餐盘或空盘")
