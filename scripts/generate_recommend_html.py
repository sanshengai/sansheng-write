#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成推荐文章 HTML 模块
默认从 <数据目录>/works.yaml(SSOT) 取已发布、按「一三五篇」规则（第 1、3、5 篇，跳过第 2、4 篇）、仅推有封面、缺封面顺延就近不重复，挑 3 篇生成纯封面推荐卡片 HTML。
（articles.md 解析器 parse_articles_from_markdown 仅留作新旧一致性校验，不再是主数据源。）

使用方式:
  python generate_recommend_html.py [输出格式: html|copy]

输出:
  - html: 保存到文件 recommend_articles.html
  - copy: 复制到剪贴板，可直接粘贴到定稿.html
"""

import os
import sys
import re
from pathlib import Path

# Windows GBK 控制台 / 被 subprocess 调用时 stdout 默认 GBK 编码，强制 UTF-8。
# 否则父进程(format_layout)按 encoding="utf-8" 读本脚本输出会 UnicodeDecodeError(0xd5)，
# 被误判 returncode!=0、静默跳过文末「推荐阅读+关注卡片」。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, os.path.dirname(__file__))
from works_registry import load_works
import profile_config as pc

# 旧数据源（保留用于新旧产出一致性校验；推荐卡已切换为读 works.yaml）
ARTICLES_DB_PATH = pc.data_dir() / "articles.md"


def resolve_cover(cv: str) -> str:
    """把 works.yaml / articles.md 里的 cover 值还原为绝对路径。

    兼容三种历史形态：`<数据目录>/` 占位符（archive 现行写法）、
    相对数据目录、相对数据目录父目录（旧库存量条目的基准）。
    """
    if not cv or cv.startswith(("http://", "https://")):
        return cv
    if cv.startswith("<数据目录>/"):
        return str(pc.data_dir() / cv[len("<数据目录>/"):])
    if Path(cv).is_absolute():
        return cv
    primary = pc.data_dir() / cv
    if primary.exists():
        return str(primary)
    legacy = pc.data_dir().parent / cv
    if legacy.exists():
        return str(legacy)
    return str(primary)


def parse_articles_from_markdown():
    """从 articles.md 提取文章信息"""
    if not ARTICLES_DB_PATH.exists():
        print(f"❌ 找不到文件: {ARTICLES_DB_PATH}")
        return []

    with open(ARTICLES_DB_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    articles = []

    # 匹配每个以 ### N. 开头的区块
    parts = re.split(r"### \d+\.\s+", content)[1:]
    for part in parts:
        lines = part.strip().split("\n")
        title = lines[0].strip()
        
        article = {
            "title": title,
            "date": "",
            "cover": "",
            "digest": "",
            "link": ""
        }
        
        for line in lines:
            line = line.strip()
            if "| **发布日期** |" in line:
                article["date"] = line.split("|")[2].strip()
            elif "| **封面** |" in line:
                # ![cover](C:\...)
                cover_match = re.search(r"!\[.*?\]\((.+?)\)", line)
                if cover_match:
                    article["cover"] = cover_match.group(1).strip()
            elif "| **摘要** |" in line:
                article["digest"] = line.split("|")[2].strip()
            elif "| **微信链接** |" in line:
                link_match = re.search(r"\[.*?\]\((.+?)\)", line)
                if link_match:
                    article["link"] = link_match.group(1).strip()
                    
        # 封面路径统一走 resolve_cover（占位符 / 相对 / 旧基准三兼容）
        article["cover"] = resolve_cover(article["cover"])

        if article["title"] and article["link"]:
            articles.append(article)

    return articles


def parse_articles_from_works():
    """从 works.yaml 提取已发布文章信息，输出与 parse_articles_from_markdown 同构的列表。

    顺序：按发布日期倒序（最新在前），与导读栏「一三五篇」选篇规则一致。
    cover 还原成绝对路径（与旧 articles.md 里的绝对封面路径等价），便于卡片做存在性校验。
    """
    works = load_works()
    pub = [w for w in works if w.get("status") == "published" and w.get("wechat_url")]
    pub.sort(key=lambda w: w.get("date", ""), reverse=True)
    articles = []
    for w in pub:
        cover_abs = resolve_cover(w.get("cover") or "")
        articles.append({
            "title": w.get("title", ""),
            "date": w.get("date", ""),
            "cover": cover_abs,
            "digest": w.get("digest", ""),
            "link": w.get("wechat_url", ""),
        })
    return articles


def _has_cover(article):
    """封面可用：非空，且为 http 链接或本地文件存在。"""
    cover = article.get("cover") or ""
    if not cover:
        return False
    if cover.startswith("http"):
        return True
    return Path(cover).exists()


def sanitize_digest(digest):
    """清理摘要文本"""
    # 移除 markdown 格式
    digest = digest.replace("**", "").replace("`", "")
    # 限制长度
    if len(digest) > 50:
        digest = digest[:50] + "..."
    return digest


def generate_single_card_html(article, index):
    """生成单篇推荐卡片的 HTML（纯封面长条：整卡 = 一张全宽封面图，可点击跳转，无右侧文字）"""
    title = article["title"]
    link = article["link"]
    cover = article["cover"]
    # 兼容处理无封面的老文章以及路径不存在的情况：降级用你 profile 里的头像作占位。
    # 没配头像就不渲染这张卡（宁可少一张，也不挂一张破图）。
    fallback_cover = (pc.identity().get("headimg") or "").strip()

    if not cover:
        cover = fallback_cover
    if not cover:
        return ""
    
    # 验证本地图片是否存在
    if not cover.startswith("http"):
        local_path = Path(cover)
        if not local_path.exists():
            print(f"⚠️ 图片丢失，降级使用默认图: {cover}")
            cover = fallback_cover

    # 纯封面版不再渲染摘要文字（digest 字段保留在数据层，卡片不用）
    # 如果是网络 URL，直接使用；否则认为是本地路径，同时生成 data-local-path
    if cover.startswith("http"):
        cover_src = cover
        cover_local_attr = ""
    else:
        cover_src = cover
        # 规范化为正斜杠路径
        cover_local = cover.replace("\\", "/")
        cover_local_attr = f' data-local-path="{cover_local}"'

    # 纯封面图版（2026-05-30）：取消右侧文字，整卡 = 一张全宽封面长条（可点击跳转）。
    # 微信兼容性规则：
    #   1. <a> 绝不能包裹块级元素 → 用 <section> 包 <a> 包 <img>（块包行内）
    #   2. box-shadow 等微信不支持的属性已禁用
    #   3. title 仅作 alt（无障碍/图丢时占位），不再渲染文字
    html = f'''  <section style="margin: 0 0 12px; line-height: 0;">
    <a href="{link}"><img src="{cover_src}"{cover_local_attr} alt="{title}" style="display:block; width:100%; height:auto; border-radius:8px;" /></a>
  </section>'''
    return html


def generate_recommend_html(articles=None):
    """生成完整的推荐阅读 HTML。articles 不传则默认读 works.yaml。"""
    if articles is None:
        articles = parse_articles_from_works()

    if not articles:
        print("❌ 未找到任何文章")
        return None

    # 寻找包含有效链接的文章
    valid_articles = [a for a in articles if a["link"] and a["link"] != "暂无" and not a["link"].startswith("#")]

    # 跳过日更类文章（日报 / 晨报会淹没推荐池）。
    # 判据：标题以 profile 里配置的任一前缀开头。默认空列表 = 不过滤。
    #   profile/brand.yaml → writing.daily_title_prefixes: ["早报【", "日报【"]
    _prefixes = pc.brand().get("writing", {}).get("daily_title_prefixes") or []

    def _is_daily(article):
        title = (article.get("title") or "").lstrip()
        return any(title.startswith(p) for p in _prefixes)

    valid_articles = [a for a in valid_articles if not _is_daily(a)]

    # 纯封面图版（2026-05-30）：只推「有封面」的文章，按「一三五」取第 1/3/5 篇。
    # 某篇拉不到封面则被过滤掉、自动顺延到就近的有封面文章；3 篇天然不重复。
    cover_articles = [a for a in valid_articles if _has_cover(a)]
    top_articles = cover_articles[0:5:2]

    if len(top_articles) < 3:
        print(f"⚠️ 有封面的有效文章不足 5 篇（当前仅 {len(cover_articles)} 篇），无法按「一三五」取出 3 篇推荐")
        return None

    html_parts = [
        '<!-- 推荐阅读 -->',
        '<section style="margin: 48px 8px 0;">',
        '  <section style="text-align: center; margin-bottom: 24px;">',
        '    <section style="display: inline-block; font-size: 17px; font-weight: bold; color: #333333; letter-spacing: 2px;">推荐阅读</section>',
        '    <section style="width: 56px; height: 4px; background: #2F6F8F; border-radius: 2px; margin: 8px auto 0;"></section>',
        '  </section>'
    ]

    # 添加三篇推荐卡片（纯封面长条，靠卡片自身 margin 间隔，不再加分割线）
    for idx, article in enumerate(top_articles):
        card_html = generate_single_card_html(article, idx)
        html_parts.append(card_html)

    html_parts.append('</section>')
    
    # 关注卡片（微信官方组件）—— 身份卡字段全部来自 profile/brand.yaml 的 identity 节。
    # identity.platform != "wechat" 时整块不渲染（比如你不发公众号）。
    # ⚠️ 三个必须条件（排查确认，勿改结构）：
    #   1. data-id 必须完整 Base64 padding（双等号 ==）
    #   2. 外层 section 必须带 class="mp_profile_iframe_wrp custom_select_card_wrp"
    #   3. mp-common-profile 必须带 class 和 data-pluginname
    ident = pc.identity()
    if (ident.get("platform") or "").lower() == "wechat" and ident.get("biz_id"):
        html_parts.append(f'''
<!-- 关注卡片（微信官方组件） -->
<section class="mp_profile_iframe_wrp custom_select_card_wrp">
  <mp-common-profile
    class="mpprofile js_uneditable custom_select_card mp_profile_iframe"
    data-pluginname="mpprofile"
    data-nickname="{ident.get('nickname', '')}"
    data-alias="{ident.get('alias', '')}"
    data-headimg="{ident.get('headimg', '')}"
    data-signature="{ident.get('signature', '')}"
    data-id="{ident.get('biz_id', '')}"
    data-service_type="1">
  </mp-common-profile>
</section>
''')
    html_parts.append('')

    full_html = '\n'.join(html_parts)
    return full_html, top_articles


def copy_to_clipboard(text):
    """复制到剪贴板"""
    try:
        import subprocess
        # Windows 使用 clip
        process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-8'))
        return True
    except:
        try:
            # macOS 使用 pbcopy
            import subprocess
            process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            return True
        except:
            return False


def main():
    """主流程"""
    output_format = sys.argv[1].lower() if len(sys.argv) > 1 else "copy"

    print("🔄 正在生成推荐文章 HTML...")

    result = generate_recommend_html()
    if result is None:
        return 1

    html, articles = result

    print("\n" + "=" * 60)
    print("📋 推荐文章信息")
    print("=" * 60)
    for idx, article in enumerate(articles, 1):
        print(f"\n{idx}. {article['title']}")
        print(f"   日期: {article['date']}")
        print(f"   摘要: {article['digest'][:40]}...")
        print(f"   链接: {article['link']}")

    print("\n" + "=" * 60)
    print("✅ 已生成 HTML")
    print("=" * 60)

    if output_format == "copy":
        # 复制到剪贴板
        if copy_to_clipboard(html):
            print("✅ HTML 已复制到剪贴板！")
            print("   现在可以直接粘贴到 定稿.html 中")
            print("\n📌 替换位置:")
            print("   找到: <!-- 推荐阅读 -->")
            print("   替换: 从这里到 </section>")
        else:
            print("⚠️  无法复制到剪贴板，改为显示 HTML:")
            print("\n" + html)

    else:
        # 保存到数据目录（SEP-10：产物含你的真实身份卡，属个人数据，不落公开仓工作树）
        output_path = pc.data_dir() / "recommend_articles.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ HTML 已保存到: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
