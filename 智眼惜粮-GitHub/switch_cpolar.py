# -*- coding: utf-8 -*-
"""
cpolar 一键换地址脚本
=========================================
免费 cpolar 隧道重启后公网地址会变，需要同步以下两处：
  1. coze/openapi.json 的 servers.url      → Coze 插件认这个
  2. frontend/.env 的 VITE_API_BASE_URL    → 前端穿透演示时用

用法（在项目根目录执行）：
    python switch_cpolar.py https://新地址.r9.cpolar.top

注意：Coze 平台插件里的接口 URL 需手动到 Coze 后台同步改（脚本改不到 Coze 网页端）。
"""
import sys
import re
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def update_openapi(new_url):
    p = os.path.join(ROOT, "coze", "openapi.json")
    with open(p, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'"url"\s*:\s*"(https?://[^"]+)"', content)
    if not m:
        print("❌ openapi.json 里没找到 servers.url，请手动检查")
        return
    old = m.group(1)
    content = content.replace(old, new_url)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ openapi.json: {old} → {new_url}")


def update_env(new_url):
    p = os.path.join(ROOT, "frontend", ".env")
    with open(p, encoding="utf-8") as f:
        content = f.read()
    # 只替换行首的配置行（MULTILINE 模式 ^ 匹配行首），避免误改 # 注释里的示例行
    new_content = re.sub(
        r"(?m)^VITE_API_BASE_URL=.*$",
        f"VITE_API_BASE_URL={new_url}",
        content,
    )
    with open(p, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"✅ frontend/.env: VITE_API_BASE_URL → {new_url}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    new_url = sys.argv[1].strip().rstrip("/")
    if not new_url.startswith("http"):
        new_url = "https://" + new_url

    update_openapi(new_url)
    update_env(new_url)

    print("\n" + "=" * 50)
    print("还需要手动做（脚本改不到的地方）：")
    print("1. Coze 平台 → 你的插件 → 接口 URL 改成新地址（最重要，容易漏）")
    print("2. 重启后端（PyCharm 重新 Run）")
    print("3. 若走穿透演示前端：重启前端 npm run dev")
    print("=" * 50)


if __name__ == "__main__":
    main()
