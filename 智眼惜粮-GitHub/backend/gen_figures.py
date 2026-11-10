# -*- coding: utf-8 -*-
"""生成论文 9 张结构/架构示意图，保存到 backend/figures/。
所有尺寸/类别数/特征维度均与代码及论文完全一致：
  YOLOv8 imgsz=800; U-Net 3下采样/512瓶颈/3分类/256输入;
  ResNet50 Bottleneck; 多模态 256+128=384 -> 3类(模型)+2类(规则)。
CJK 字体使用系统 SimHei。
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

FONT = "C:\\Windows\\Fonts\\simhei.ttf"
if os.path.exists(FONT):
    from matplotlib import font_manager
    font_manager.fontManager.addfont(FONT)
    plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.family"] = "sans-serif"

OUT = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(OUT, exist_ok=True)

# 调色板
C_INPUT = "#e8eef5"
C_VIS = "#cfe0f3"
C_VIS2 = "#aecbe8"
C_STR = "#d6ecd9"
C_HEAD = "#f6d9c2"
C_OUT = "#f3c9d2"
C_DATA = "#e3d6f0"
C_EXT = "#cdeae4"
C_RULE = "#fbe7b2"


def box(ax, x, y, w, h, text, fc, ec="#2c5a8a", fs=10, bold=False, tc="#1a1a1a"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.12",
                                fc=fc, ec=ec, lw=1.3, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            fontweight=("bold" if bold else "normal"), color=tc, zorder=3, linespacing=1.25)


def arrow(ax, x1, y1, x2, y2, color="#3a3a3a", rad=0, style="-|>", ls="solid", lw=1.3):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=13,
                                 color=color, lw=lw, connectionstyle=f"arc3,rad={rad}",
                                 linestyle=ls, zorder=1))


def txt(ax, x, y, s, fs=9, color="#333", ha="left", va="center", bold=False):
    ax.text(x, y, s, fontsize=fs, color=color, ha=ha, va=va,
            fontweight=("bold" if bold else "normal"))


# ---------------------------------------------------------------------------
def fig_yolov8():
    fig, ax = plt.subplots(figsize=(7.2, 9.2))
    ax.set_xlim(0, 12); ax.set_ylim(0, 19); ax.axis("off")
    cx = 6
    box(ax, cx - 2.6, 17.2, 5.2, 1.4, "输入图像\n800 × 800 × 3", C_INPUT, fs=11, bold=True)
    box(ax, cx - 3, 13.4, 6, 3.0,
        "Backbone：CSP-Darknet\nConv stem（3→64）\nC2f × 3（64→128→256→512）\nSPPF 空间金字塔池化", C_VIS, fs=9.5)
    box(ax, cx - 3, 9.4, 6, 3.0,
        "Neck：PAN-FPN\n上采样 + 拼接（C2f）\n多尺度特征融合（深→浅）", C_VIS2, fs=9.5)
    box(ax, cx - 3, 5.0, 6, 3.2,
        "Head：无锚框解耦检测头\n3 个检测分支（分类 / 回归 分离）\n输出特征图 100 / 50 / 25", C_HEAD, fs=9.5)
    box(ax, cx - 2.6, 1.0, 5.2, 2.6,
        "输出：类别 + 置信度 + 边界框\nNMS 非极大抑制后处理\n（最大检测数 20，置信度 0.3）", C_OUT, fs=9.5, bold=True)
    for y0, y1 in [(17.2, 16.4), (13.4, 12.4), (9.4, 8.4), (5.0, 3.6), (5.0, 3.6)]:
        arrow(ax, cx, y0, cx, y1)
    arrow(ax, cx, 5.0, cx, 3.6)
    arrow(ax, cx, 1.0 + 2.6, cx, 1.0 + 0.2)
    # 右侧标注
    txt(ax, 9.4, 14.9, "YOLOv8", fs=10, bold=True, color="#1f4e79")
    txt(ax, 9.4, 11.0, "单次前向\n实时检测", fs=8.5, color="#555")
    fig.savefig(os.path.join(OUT, "fig2-1_yolov8.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_unet():
    fig, ax = plt.subplots(figsize=(8.4, 9.2))
    ax.set_xlim(0, 12); ax.set_ylim(0, 18); ax.axis("off")
    # 编码器（左）
    box(ax, 0.3, 15.6, 2.6, 1.7, "输入\n256 × 256", C_INPUT, fs=9.5, bold=True)
    box(ax, 0.3, 12.9, 2.6, 1.7, "下采样\n64 通道", C_VIS, fs=9)
    box(ax, 0.3, 10.2, 2.6, 1.7, "下采样\n128 通道", C_VIS, fs=9)
    box(ax, 0.3, 7.5, 2.6, 1.7, "下采样\n256 通道", C_VIS, fs=9)
    box(ax, 0.3, 4.8, 2.6, 1.7, "下采样\n512 通道", C_VIS2, fs=9)
    # 瓶颈（中）
    box(ax, 4.4, 4.6, 3.2, 2.1, "瓶颈 512 通道\n（3×下采样）\n双层卷积", C_VIS2, fs=9.5, bold=True)
    # 解码器（右）
    box(ax, 9.1, 7.5, 2.6, 1.7, "上采样\n256 通道", C_VIS, fs=9)
    box(ax, 9.1, 10.2, 2.6, 1.7, "上采样\n128 通道", C_VIS, fs=9)
    box(ax, 9.1, 12.9, 2.6, 1.7, "上采样\n64 通道", C_VIS, fs=9)
    box(ax, 9.1, 15.6, 2.6, 1.7, "输出 256×256\n1×1 卷积\n3 分类掩码", C_OUT, fs=9, bold=True)
    # 主链箭头
    arrow(ax, 1.6, 15.6, 1.6, 14.6); arrow(ax, 1.6, 12.9, 1.6, 11.9)
    arrow(ax, 1.6, 10.2, 1.6, 9.2); arrow(ax, 1.6, 7.5, 1.6, 6.5)
    arrow(ax, 2.9, 5.65, 4.4, 5.65)
    arrow(ax, 7.6, 5.65, 9.1, 8.0); arrow(ax, 10.4, 7.5, 10.4, 9.2)
    arrow(ax, 10.4, 10.2, 10.4, 11.2); arrow(ax, 10.4, 12.9, 10.4, 13.9)
    # 跳跃连接（虚线）
    arrow(ax, 2.9, 13.75, 9.1, 13.75, color="#888", ls="dashed", rad=0)
    arrow(ax, 2.9, 11.05, 9.1, 11.05, color="#888", ls="dashed")
    arrow(ax, 2.9, 8.35, 9.1, 8.35, color="#888", ls="dashed")
    txt(ax, 4.7, 16.6, "编码器Encoder", fs=9, color="#1f4e79", bold=True)
    txt(ax, 9.4, 16.6, "解码器Decoder", fs=9, color="#1f4e79", bold=True)
    txt(ax, 3.0, 17.3, "U-Net 语义分割（背景 / 餐盘 / 食物 三分类）", fs=9.5, color="#333", bold=True)
    fig.savefig(os.path.join(OUT, "fig2-2_unet.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_resnet():
    fig, ax = plt.subplots(figsize=(8.6, 7.6))
    ax.set_xlim(0, 13); ax.set_ylim(0, 15.5); ax.axis("off")
    cx = 4.2
    box(ax, cx - 2.4, 13.6, 4.8, 1.4, "输入图像 224 × 224 × 3", C_INPUT, fs=10, bold=True)
    box(ax, cx - 3, 11.0, 6, 1.7, "Conv1（7×7, /2）+ BN + ReLU + MaxPool", C_VIS, fs=9)
    box(ax, cx - 3, 8.9, 6, 1.5, "Stage1：Bottleneck × 3（64 通道）", C_VIS, fs=9)
    box(ax, cx - 3, 6.9, 6, 1.5, "Stage2：Bottleneck × 4（128 通道, /2）", C_VIS2, fs=9)
    box(ax, cx - 3, 4.9, 6, 1.5, "Stage3：Bottleneck × 6（256 通道, /2）", C_VIS2, fs=9)
    box(ax, cx - 3, 2.9, 6, 1.5, "Stage4：Bottleneck × 3（512 通道, /2）", C_VIS2, fs=9)
    box(ax, cx - 3, 0.6, 6, 1.6, "全局平均池化 → 特征向量（本文去 FC）", C_STR, fs=9)
    for y0, y1 in [(13.6, 12.7), (11.0, 10.4), (8.9, 8.4), (6.9, 6.4), (4.9, 5.4), (2.9, 2.2)]:
        arrow(ax, cx, y0, cx, y1)
    # 残差块细节（右侧）
    box(ax, 9.3, 6.5, 3.4, 5.2,
        "残差块（Bottleneck）\n─────────────\n1×1 降维卷积\n3×3 卷积\n1×1 升维卷积\n+ 快捷连接\n（下采样时 1×1 对齐）", C_HEAD, fs=8.8)
    arrow(ax, 7.2, 7.6, 9.3, 8.4, color="#b5651d")
    txt(ax, 9.3, 12.2, "ResNet50\n瓶颈结构", fs=9.5, bold=True, color="#8a4b1d")
    fig.savefig(os.path.join(OUT, "fig2-3_resnet.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_agent():
    fig, ax = plt.subplots(figsize=(8.8, 6.6))
    ax.set_xlim(0, 13); ax.set_ylim(0, 9); ax.axis("off")
    box(ax, 0.3, 3.6, 2.0, 1.8, "用户", C_INPUT, fs=10, bold=True)
    box(ax, 2.8, 3.6, 2.4, 1.8, "前端 Vue3\n对话界面", C_VIS, fs=9)
    box(ax, 5.7, 3.6, 2.6, 1.8, "后端 FastAPI\n/api/ai/chat", C_VIS2, fs=9)
    box(ax, 8.8, 3.6, 2.4, 1.8, "Coze API\napi.coze.cn", C_EXT, fs=9)
    box(ax, 8.8, 0.5, 2.4, 1.9, "Coze 智能体\n挂载“餐食浪费\n分析”插件", C_EXT, fs=8.8)
    box(ax, 5.7, 0.5, 2.6, 1.9, "大模型\n(LLM)", C_HEAD, fs=9)
    for x0, x1 in [(2.3, 2.8), (5.2, 5.7), (8.3, 8.8)]:
        arrow(ax, x0, 4.5, x1, 4.5)
    arrow(ax, 10.0, 3.6, 10.0, 2.4)
    # LLM <-> 聚合接口 双向回调
    box(ax, 2.8, 0.5, 2.4, 1.9, "后端聚合接口\n/api/aggregate\n-analysis", C_STR, fs=8.6)
    ax.add_patch(FancyArrowPatch((8.8, 1.45), (5.2, 1.45), arrowstyle="-|>",
                 color="#2e7d32", lw=1.2, connectionstyle="arc3,rad=-0.35", linestyle="dashed"))
    ax.add_patch(FancyArrowPatch((5.2, 1.20), (8.8, 1.20), arrowstyle="-|>",
                 color="#2e7d32", lw=1.2, connectionstyle="arc3,rad=0.35", linestyle="dashed"))
    txt(ax, 6.6, 6.2, "大模型智能体（Coze）调用链路", fs=10.5, bold=True, color="#1f4e79")
    txt(ax, 6.8, 0.2, "插件回调：查询/分析", fs=8, color="#2e7d32")
    fig.savefig(os.path.join(OUT, "fig2-4_agent.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_arch():
    fig, ax = plt.subplots(figsize=(7.4, 10.2))
    ax.set_xlim(0, 13); ax.set_ylim(0, 19); ax.axis("off")
    w = 8.2
    box(ax, 1.9, 16.2, w, 2.0, "前端展示层\nVue3 单页应用（交互 / 结果展示 / 数据可视化）", C_INPUT, fs=9.5, bold=True)
    box(ax, 1.9, 12.4, w, 2.0, "后端服务层\nFastAPI RESTful 接口（业务逻辑 / 接口鉴权 / 数据聚合）", C_VIS, fs=9.5)
    box(ax, 1.9, 8.6, w, 2.0, "模型推理层\nYOLOv8 检测  ·  U-Net 分割  ·  ResNet50 弃因分类", C_VIS2, fs=9.5)
    box(ax, 1.9, 4.8, w, 2.0, "数据存储层\nMySQL（检测记录 / 菜品明细 / 配置 / 用户）", C_DATA, fs=9.5)
    for y0, y1 in [(16.2, 14.4), (12.4, 10.6), (8.6, 6.8)]:
        arrow(ax, 6.0, y0, 6.0, y1)
    # 右侧 Coze 旁路
    box(ax, 10.1, 12.4, 2.2, 3.6, "大模型\n智能体\n(Coze)", C_EXT, fs=8.6)
    box(ax, 10.1, 7.8, 2.2, 2.4, "内网穿透\ncpolar\n暴露公网", C_EXT, fs=8.6)
    arrow(ax, 11.2, 12.4, 11.2, 10.6, color="#0a7d6b")
    arrow(ax, 11.2, 7.8, 11.2, 8.6, color="#0a7d6b")
    ax.add_patch(FancyArrowPatch((11.2, 8.6), (10.1, 11.0), arrowstyle="-|>",
                 color="#0a7d6b", lw=1.2, connectionstyle="arc3,rad=0.2"))
    txt(ax, 10.1, 16.4, "旁路", fs=8, color="#0a7d6b")
    fig.savefig(os.path.join(OUT, "fig3-1_arch.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_modules():
    fig, ax = plt.subplots(figsize=(8.6, 9.8))
    ax.set_xlim(0, 13); ax.set_ylim(0, 17.5); ax.axis("off")
    mods = [
        (0.4, 12.8, "检测模块", "单张/批量/摄像头\n检测·分割·浪费率"),
        (6.6, 12.8, "弃因分析模块", "结构化特征\n多模态分类·规则前置"),
        (0.4, 9.4, "统计分析模块", "多维聚合\n趋势/排行/分布"),
        (6.6, 9.4, "记录管理模块", "历史记录\n查询·筛选·分页"),
        (0.4, 6.0, "评委打分模块", "人工复核\n判定·准确率统计"),
        (6.6, 6.0, "智能分析模块", "Coze 对接\n聚合接口·对话代理"),
        (3.5, 2.6, "系统配置模块", "运行参数\n定时清理调度"),
    ]
    for x, y, t, d in mods:
        box(ax, x, y, 5.8, 2.6, f"{t}\n{d}", C_VIS, fs=9.2, bold=True)
    box(ax, 4.6, 15.0, 3.6, 1.2, "系统功能模块", C_INPUT, fs=10.5, bold=True)
    arrow(ax, 6.4, 15.0, 3.3, 13.6); arrow(ax, 6.6, 15.0, 9.5, 13.6)
    arrow(ax, 3.3, 12.8, 3.3, 11.4); arrow(ax, 9.5, 12.8, 9.5, 11.4)
    arrow(ax, 3.3, 9.4, 3.3, 8.0); arrow(ax, 9.5, 9.4, 9.5, 8.0)
    arrow(ax, 3.3, 6.0, 6.4, 4.4); arrow(ax, 9.5, 6.0, 6.6, 4.4)
    fig.savefig(os.path.join(OUT, "fig3-2_modules.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def _er_entity(ax, x, y, w, h, title, attrs, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02",
                                fc=color, ec="#5a3d8a", lw=1.3, zorder=2))
    ax.add_patch(FancyBboxPatch((x, y + h - 0.55), w, 0.55, boxstyle="round,pad=0.02",
                                fc="#5a3d8a", ec="#5a3d8a", lw=1.3, zorder=2))
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="center", fontsize=9.5,
            color="white", fontweight="bold", zorder=3)
    for i, a in enumerate(attrs):
        ax.text(x + 0.15, y + h - 0.85 - i * 0.42, a, ha="left", va="center", fontsize=8.3, zorder=3)


def fig_er():
    fig, ax = plt.subplots(figsize=(9.4, 10.4))
    ax.set_xlim(0, 13); ax.set_ylim(0, 17); ax.axis("off")
    _er_entity(ax, 0.3, 11.2, 5.0, 5.0, "detection_records",
               ["id  (PK)", "record_type", "file_name", "wastage_rate",
                "status", "create_time", "（主记录）"], C_DATA)
    _er_entity(ax, 0.3, 4.0, 5.0, 4.0, "detection_items",
               ["id  (PK)", "record_id  (FK)", "food_name", "confidence",
                "bbox_x1/y1/x2/y2", "（级联删除）"], C_DATA)
    _er_entity(ax, 7.0, 13.4, 3.2, 1.5, "system_config", ["key (PK)", "value"], C_STR)
    _er_entity(ax, 7.0, 10.8, 3.2, 1.8, "system_users", ["id/username (PK)", "password", "role"], C_STR)
    _er_entity(ax, 7.0, 7.8, 3.2, 1.8, "judge_evaluations", ["id (PK)", "record_id", "result"], C_RULE)
    _er_entity(ax, 7.0, 5.4, 3.2, 1.5, "judge_config", ["key (PK)", "value"], C_RULE)
    # 关系：records 1—N items
    ax.add_patch(FancyArrowPatch((5.3, 12.6), (0.3 + 0.6, 6.2), arrowstyle="-|>",
                 color="#5a3d8a", lw=1.4, connectionstyle="arc3,rad=-0.15"))
    ax.text(5.7, 9.6, "1 : N\n(record_id)", fontsize=8.5, color="#5a3d8a", va="center")
    txt(ax, 0.3, 16.6, "数据库 E-R 图（主库 + 评委打分独立库）", fs=10.5, bold=True, color="#5a3d8a")
    fig.savefig(os.path.join(OUT, "fig3-3_er.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_pipeline():
    fig, ax = plt.subplots(figsize=(8.4, 12.2))
    ax.set_xlim(0, 12); ax.set_ylim(0, 21); ax.axis("off")
    cx = 5.0
    steps = [
        (18.6, "① 图片输入\n单张 / 批量 / 摄像头", C_INPUT),
        (16.0, "② 预处理\n白平衡校正 + letterbox 缩放至 800", C_VIS),
        (13.4, "③ YOLOv8 检测\n菜品类别 + 置信度 + 边界框", C_VIS),
        (10.8, "④ U-Net 分割\n餐盘 / 食物 三分类掩码", C_VIS2),
        (8.2, "⑤ 浪费率计算\nfood/(food+plate)  （公式 4-1）", C_HEAD),
        (5.6, "⑥ 结构化特征提取\n29 维特征", C_STR),
        (3.0, "⑦ 多模态弃因分类\nResNet50 + 29 维 → 3 类", C_HEAD),
        (0.8, "⑧ 结果存储与展示\nMySQL 写入 + 前端可视化", C_OUT),
    ]
    for y, t, c in steps:
        box(ax, cx - 2.8, y, 5.6, 1.9, t, c, fs=9)
    for i in range(len(steps) - 1):
        arrow(ax, cx, steps[i][0], cx, steps[i + 1][0] + 1.9)
    # 规则前置判断（旁路，汇入 ⑦）
    box(ax, 8.7, 4.6, 3.0, 2.0, "规则前置判断\n无餐盘/空盘\n油腻不适", C_RULE, fs=8.8, bold=True)
    arrow(ax, 8.7, 5.6, cx + 2.8, 5.6, color="#b8860b", ls="dashed")
    arrow(ax, 8.7 + 1.5, 4.6, 8.7 + 1.5, 3.9, color="#b8860b", ls="dashed")
    ax.add_patch(FancyArrowPatch((10.2, 3.9), (cx + 2.2, 3.9), arrowstyle="-|>",
                 color="#b8860b", lw=1.2, connectionstyle="arc3,rad=0.3", linestyle="dashed"))
    fig.savefig(os.path.join(OUT, "fig4-1_pipeline.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_multimodal():
    fig, ax = plt.subplots(figsize=(9.4, 7.8))
    ax.set_xlim(0, 14); ax.set_ylim(0, 11); ax.axis("off")
    # 视觉分支
    box(ax, 0.3, 7.4, 3.4, 2.0, "输入图像", C_INPUT, fs=10, bold=True)
    box(ax, 0.3, 4.6, 3.4, 2.2, "ResNet50 骨干\n（去最后 FC）\n全局平均池化", C_VIS, fs=9)
    box(ax, 0.3, 1.6, 3.4, 2.0, "视觉特征\n256 维", C_VIS2, fs=10, bold=True)
    arrow(ax, 2.0, 7.4, 2.0, 6.8); arrow(ax, 2.0, 4.6, 2.0, 3.6)
    # 结构化分支
    box(ax, 4.4, 4.6, 3.4, 2.2, "29 维结构化特征\n（图像/检测/分割/分布）", C_STR, fs=9)
    box(ax, 4.4, 1.6, 3.4, 2.0, "结构化编码器\n2×FC+BN+ReLU+Dropout\n128 维", C_STR, fs=9)
    arrow(ax, 6.1, 4.6, 6.1, 3.6)
    # 融合
    box(ax, 8.4, 4.3, 3.0, 2.6, "特征拼接\n256 + 128 = 384 维", C_HEAD, fs=9.5, bold=True)
    arrow(ax, 3.7, 2.6, 8.4, 3.6, color="#444")
    arrow(ax, 7.8, 3.0, 8.4, 4.0, color="#444")
    box(ax, 8.4, 0.9, 3.0, 2.2, "MLP 分类头\n384→128→64→3\n（交叉熵加权）", C_HEAD, fs=9)
    arrow(ax, 9.9, 4.3, 9.9, 3.1)
    box(ax, 11.9, 0.9, 2.1, 2.2, "3 类模型结果\n份量过大\n口味偏好/质量\n正常范围", C_OUT, fs=8.5, bold=True)
    arrow(ax, 11.4, 2.0, 11.9, 2.0)
    # 规则前置汇合
    box(ax, 11.9, 4.3, 2.1, 2.2, "规则前置\n无餐盘/空盘\n油腻不适", C_RULE, fs=8.5, bold=True)
    box(ax, 11.9, 7.2, 2.1, 2.2, "五类弃因\n结果", C_OUT, fs=10, bold=True)
    arrow(ax, 11.9, 7.2, 11.9, 6.5)
    arrow(ax, 13.0, 6.5, 13.0, 6.5, color="#b8860b")
    ax.add_patch(FancyArrowPatch((12.95, 6.5), (12.95, 5.0), arrowstyle="-|>",
                 color="#b8860b", lw=1.2, linestyle="dashed"))
    txt(ax, 0.3, 10.2, "多模态弃因分类模型结构", fs=11, bold=True, color="#1f4e79")
    fig.savefig(os.path.join(OUT, "fig4-3_multimodal.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_yolov8(); fig_unet(); fig_resnet(); fig_agent()
    fig_arch(); fig_modules(); fig_er(); fig_pipeline(); fig_multimodal()
    print("已生成 9 张图到:", OUT)
    for f in sorted(os.listdir(OUT)):
        print(" -", f)
