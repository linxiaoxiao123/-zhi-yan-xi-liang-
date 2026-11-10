"""
半自动标注脚本：用旧弃因模型对未标注图片预标伪标签，输出低置信度清单供人工纠错。

流程：
1. 遍历图片目录，对每张图跑 YOLO + U-Net 提取特征（与训练 extract_features.py 一致）
2. 用旧弃因模型 waste_cause_3cls.pth 预标伪标签
3. 输出 CSV（特征 + 伪标签 cause_label + 置信度 confidence）
4. 输出低置信度清单（confidence < 阈值，供人工纠错）

用法:
    python pseudo_label.py --input_dir D:/path/to/images --output waste_cause_pseudo_labeled.csv --conf_threshold 0.6
"""
import os
import csv
import argparse
import time
from collections import Counter

from PIL import Image

from extract_features import extract_features_from_image
from waste_cause_inference import predict_with_rules


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", required=True, help="未标注图片目录")
    parser.add_argument("--output", default="waste_cause_pseudo_labeled.csv", help="输出CSV")
    parser.add_argument("--conf_threshold", type=float, default=0.6, help="低置信度阈值（默认0.6）")
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"ERROR: 图片目录不存在: {args.input_dir}")
        return

    image_files = sorted([
        f for f in os.listdir(args.input_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))
    ])
    print(f"扫描到 {len(image_files)} 张图片")

    rows = []
    low_conf = []
    t_start = time.time()

    for i, fname in enumerate(image_files):
        img_path = os.path.join(args.input_dir, fname)
        try:
            # 1. 提取特征（与训练 extract_features.py 同口径）
            feats = extract_features_from_image(img_path, fname)

            # 2. 字段映射：训练用的是 capped 版（与 cluster_labels.py 的 clip 逻辑一致）
            feats["waste_rate_capped"] = min(max(feats.get("waste_rate_raw", 0), 0), 100)
            feats["waste_ratio_capped"] = min(max(feats.get("waste_ratio", 0), 0), 1.0)

            # 3. 旧模型预标
            img = Image.open(img_path).convert("RGB")
            result = predict_with_rules(feats, img)
            cause = result["cause"]
            conf = result.get("confidence", 0.0)

            feats["cause_label"] = cause
            feats["confidence"] = round(conf, 4)
            rows.append(feats)

            # 低置信度（规则命中的不算，模型预测的低置信度才需要纠错）
            if not result.get("rule_match") and conf < args.conf_threshold:
                low_conf.append((fname, cause, conf))

            if (i + 1) % 20 == 0:
                elapsed = time.time() - t_start
                speed = elapsed / (i + 1)
                eta = speed * (len(image_files) - i - 1)
                print(f"  [{i+1}/{len(image_files)}] 已耗时{elapsed:.0f}s 预计剩余{eta:.0f}s")

        except Exception as e:
            print(f"  WARNING {fname} 处理失败: {e}")

    # 输出完整 CSV
    if rows:
        keys = list(rows[0].keys())
        with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print(f"\n✅ 预标完成: {len(rows)} 张 → {args.output}")

    # 低置信度清单（按置信度升序，最需要纠错的排前面）
    low_conf.sort(key=lambda x: x[2])
    print(f"\n⚠️ 低置信度样本（需人工纠错）: {len(low_conf)} 张")
    for fname, cause, conf in low_conf[:50]:
        print(f"  {fname}: {cause} ({conf:.3f})")
    if len(low_conf) > 50:
        print(f"  ...（其余 {len(low_conf) - 50} 张见 CSV 中 confidence 列）")

    # 伪标签分布
    if rows:
        dist = Counter(r["cause_label"] for r in rows)
        print(f"\n伪标签分布:")
        for label, cnt in dist.most_common():
            print(f"  {label}: {cnt} ({cnt/len(rows)*100:.1f}%)")


if __name__ == "__main__":
    main()
