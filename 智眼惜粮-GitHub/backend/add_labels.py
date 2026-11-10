"""
将聚类编号映射为弃因名称，写入CSV
运行方式: python add_labels.py
"""
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(BASE_DIR, "waste_cause_features_labeled.csv")

LABEL_MAP = {
    0: "无餐盘/空盘",
    1: "份量过大",
    2: "油腻不适",
    3: "正常范围",
    4: "口味偏好/菜品质量",
}

df = pd.read_csv(INPUT_CSV)
df["cause_label"] = df["cluster"].map(LABEL_MAP)

# 排除无餐盘/空盘的数据用于训练（废因分析只关心有餐盘的情况）
df_train = df[df["cause_label"] != "无餐盘/空盘"].copy()

df.to_csv(INPUT_CSV, index=False, encoding="utf-8-sig")
print(f"完整数据 ({len(df)} 条) 已更新: {INPUT_CSV}")
print(f"可用于训练的数据 ({len(df_train)} 条，已排除'无餐盘/空盘')")
print(f"\n标签分布:")
for label, count in df_train["cause_label"].value_counts().items():
    print(f"  {label}: {count} ({count/len(df_train)*100:.1f}%)")
