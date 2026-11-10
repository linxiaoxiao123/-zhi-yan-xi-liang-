# -*- coding: utf-8 -*-
"""Markdown 论文初稿 → Word 转换脚本
用法：python md2docx.py
输入：毕设论文初稿.md
输出：毕设论文初稿.docx（标题层级 + 宋体正文 + 表格 + 引用块 + 公式）
"""
import re
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree
import os

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

SRC = "毕设论文初稿.md"
DST = "毕设论文初稿.docx"
FIG_WIDTH = Inches(5.0)
IMG_RE = re.compile(r"!\[(.*?)\]\((.*?)\)")


def set_run_font(run, cn_font="宋体", size=12, bold=False, color=None, italic=False):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), cn_font)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_rich_text(paragraph, text, cn_font="宋体", size=12, base_bold=False):
    """解析 **粗体** 和 `代码` 片段，添加到段落"""
    parts = re.split(r"(\*\*.*?\*\*|`[^`]*`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            set_run_font(run, cn_font, size, bold=True)
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            set_run_font(run, "Consolas", size - 1, bold=False)
            run._element.rPr.rFonts.set(qn("w:eastAsia"), cn_font)
        else:
            run = paragraph.add_run(part)
            set_run_font(run, cn_font, size, bold=base_bold)
    return paragraph


def set_cell_border(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tcPr.append(borders)


# ----------------------------------------------------------------------------
# Word 原生数学公式（OMML）渲染：支持 标识符(斜体) / 运算符 / 括号 / 分式 / 等式
# ----------------------------------------------------------------------------
def _mrun(text, italic=False):
    """生成一个 OMML 文本 run。"""
    rpr = '<m:rFonts m:ascii="Cambria Math" m:hAnsi="Cambria Math" />'
    if italic:
        rpr += "<m:i />"
    return f'<m:r><m:rPr>{rpr}</m:rPr><m:t xml:space="preserve">{text}</m:t></m:r>'


def _wrap(content, tag):
    return f"<{tag}>{content}</{tag}>"


def _split_top(expr, delim):
    """在 expr 顶层（不在括号内）按 delim 切分。"""
    depth = 0
    parts, cur = [], ""
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == delim and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _parse_atom(tok):
    tok = tok.strip()
    if len(tok) >= 2 and tok.startswith("(") and tok.endswith(")"):
        inner = tok[1:-1]
        return (f'<m:d><m:dPr><m:begChr m:val="(" /><m:endChr m:val=")" /></m:dPr>'
                f'{_parse_expr(inner)}</m:d>')
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok):
        return _mrun(tok, italic=True)
    return _mrun(tok, italic=False)


def _parse_expr(expr):
    expr = expr.strip()
    # 1) 等式（优先级最高）
    if len(_split_top(expr, "=")) > 1:
        parts = _split_top(expr, "=")
        out = _parse_expr(parts[0].strip())
        for p in parts[1:]:
            out += _mrun(" = ") + _parse_expr(p.strip())
        return out
    # 2) 分式 a / b
    if len(_split_top(expr, "/")) > 1:
        parts = _split_top(expr, "/")
        num = parts[0].strip()
        den = "/".join(parts[1:]).strip()
        return (f'<m:f><m:fPr />{_wrap(_parse_expr(num), "m:num")}'
                f'{_wrap(_parse_expr(den), "m:den")}</m:f>')
    # 3) 乘 / 加 / 减
    for delim in ("×", "+", "-"):
        if len(_split_top(expr, delim)) > 1:
            parts = _split_top(expr, delim)
            out = _parse_expr(parts[0].strip())
            for p in parts[1:]:
                out += _mrun(f" {delim} ") + _parse_expr(p.strip())
            return out
    return _parse_atom(expr)


def add_equation(doc, expr, label=None):
    """在文档中插入一个 Word 原生数学公式（居中），可选右括号编号。"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    inner = _parse_expr(expr)
    omml = f'<m:oMath xmlns:m="{M_NS}">{inner}</m:oMath>'
    elem = etree.fromstring(omml.encode("utf-8"))
    p._p.append(elem)
    if label:
        run = p.add_run(f"   ({label})")
        set_run_font(run, "Times New Roman", 12)
    return p


def main():
    with open(SRC, encoding="utf-8") as f:
        lines = f.read().split("\n")

    doc = Document()
    # 默认样式
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()

        # 分隔线
        if line.strip() == "---":
            i += 1
            continue

        # 代码块：若为公式（含数学运算符与编号）则渲染为 Word 原生 OMML 公式
        if line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结束 ```
            raw = "\n".join(code_lines).strip()
            is_formula = bool(re.search(r"\((\d+-\d+)\)\s*$", raw)) or ("wastage_rate" in raw)
            if is_formula:
                try:
                    mm = re.search(r"\((\d+-\d+)\)\s*$", raw)
                    label = mm.group(1) if mm else None
                    expr = raw[:mm.start()].strip() if mm else raw
                    add_equation(doc, expr, label)
                    continue
                except Exception:
                    # 公式渲染失败时回退为普通等宽文本
                    pass
            for cl in code_lines:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(cl)
                set_run_font(run, "Consolas", 12, bold=False)
            continue

        # 表格
        if line.strip().startswith("|"):
            table_lines = []
            while i < n and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            # 解析表格
            rows = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                if all(re.fullmatch(r":?-+:?", c) for c in cells):
                    continue  # 分隔行
                rows.append(cells)
            if rows:
                ncols = max(len(r) for r in rows)
                table = doc.add_table(rows=len(rows), cols=ncols)
                table.style = "Table Grid"
                for ri, row in enumerate(rows):
                    for ci in range(ncols):
                        text = row[ci] if ci < len(row) else ""
                        cell = table.cell(ri, ci)
                        cell.text = ""
                        p = cell.paragraphs[0]
                        add_rich_text(p, text, size=10.5)
                        set_cell_border(cell)
            continue

        # 引用块（图位说明 / 图片）
        if line.startswith("> "):
            quote_lines = []
            while i < n and lines[i].startswith(">"):
                quote_lines.append(lines[i][2:].strip())
                i += 1
            for ql in quote_lines:
                m_img = IMG_RE.match(ql)
                if m_img:
                    img_path = m_img.group(2)
                    if not os.path.isabs(img_path):
                        img_path = os.path.join(os.path.dirname(__file__), img_path)
                    try:
                        p = doc.add_picture(img_path, width=FIG_WIDTH)
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        p.paragraph_format.space_before = Pt(4)
                        p.paragraph_format.space_after = Pt(4)
                    except Exception as e:
                        p = doc.add_paragraph()
                        p.paragraph_format.left_indent = Pt(18)
                        add_rich_text(p, f"[图片加载失败：{m_img.group(2)} — {e}]", size=10.5, cn_font="楷体")
                else:
                    p = doc.add_paragraph()
                    p.paragraph_format.left_indent = Pt(18)
                    add_rich_text(p, ql, size=10.5, cn_font="楷体")
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            p = doc.add_paragraph()
            # 设置内置标题样式，使 Word 导航窗格与自动目录可识别章节层级
            try:
                p.style = doc.styles[f"Heading {level}"]
            except Exception:
                pass
            if level == 1:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif level == 2:
                p.paragraph_format.space_before = Pt(12)
                p.paragraph_format.space_after = Pt(6)
            elif level == 3:
                p.paragraph_format.space_before = Pt(8)
                p.paragraph_format.space_after = Pt(4)
            run = p.add_run(text)
            set_run_font(run, "黑体", {1: 16, 2: 14, 3: 13}.get(level, 12), bold=True)
            i += 1
            continue

        # 无序列表
        m = re.match(r"^-\s+(.*)", line)
        if m:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(21)
            add_rich_text(p, m.group(1).strip(), size=12)
            i += 1
            continue

        # 有序列表
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(21)
            add_rich_text(p, line.strip(), size=12)
            i += 1
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 普通段落
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        p.paragraph_format.first_line_indent = Pt(24)  # 首行缩进2字符
        add_rich_text(p, line.strip(), size=12)
        i += 1

    doc.save(DST)
    print(f"✅ 已生成 Word 文档：{DST}")


if __name__ == "__main__":
    main()
