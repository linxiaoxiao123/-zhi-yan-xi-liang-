"""
重算弃因训练 CSV 的浪费率特征为新公式 food/(food+plate)。
在云端训练前运行一次，把旧公式特征统一成新公式（与前端展示层一致）。

用法: python recompute_features.py [csv路径]
默认: waste_cause_features_labeled.csv
"""
import sys
import pandas as pd

CSV = sys.argv[1] if len(sys.argv) > 1 else "waste_cause_features_labeled.csv"

df = pd.read_csv(CSV)
print(f"读入 {len(df)} 行")

food = df["food_pixels"].astype(float)
plate = df["plate_pixels"].astype(float)
oil = df["oil_pixels"].astype(float)
total = food + plate
total_safe = total.replace(0, 1)

# 新公式 food/(food+plate)
df["waste_rate_raw"] = (food / total_safe * 100).round(2)
df["waste_ratio"] = (food / total_safe).round(4)
df["oil_ratio"] = (oil / total_safe).round(4)

# capped 版
df["waste_rate_capped"] = df["waste_rate_raw"].clip(0, 100)
df["waste_ratio_capped"] = df["waste_ratio"].clip(0, 1.0)

# 重算浪费等级
df["waste_level_int"] = 0
df.loc[df["waste_rate_capped"] >= 5, "waste_level_int"] = 1
df.loc[df["waste_rate_capped"] >= 20, "waste_level_int"] = 2

df.to_csv(CSV, index=False, encoding="utf-8-sig")
print(f"\n✅ 已用新公式重算特征并保存: {CSV}")
print(f"   waste_rate_raw 范围: {df['waste_rate_raw'].min():.1f}% ~ {df['waste_rate_raw'].max():.1f}%（应 ≤100%）")
print(f"   标签分布(不变): {df['cause_label'].value_counts().to_dict()}")
