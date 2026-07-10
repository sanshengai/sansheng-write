# -*- coding: utf-8 -*-
"""合成一份「排版后定稿.html」夹具，替代真实文章 golden。

为什么不用真实文章：公开仓不含任何真实已发布内容（版权 + 隐私）。

这份合成件是**完整可发布文档**，同时充当两个角色：
  1. `verify_final_html` 的产物关夹具 -- 覆盖它的全部校准点：
     `<div id="output">` 外壳与 `class=` 属性（合法，不得误杀）、`display:flex`（合法）、
     居中的 dashed 占位块（应豁免 WARN）；不含任何硬违规
     （<style>/<script>/position:fixed/grid/var(--)/@media/@keyframes/@import）。
  2. `format_layout.py --check` 的预发布自检夹具 -- 含 <head>/</body>、导读栏、
     PART 编号 H2、推荐阅读、关注卡片，跑出来应当 0 错误。

身份卡字段用占位符（真值由 profile 填入），不含任何真实账号信息。

重新生成：python tests/golden/_synthetic_final/make_fixture.py
"""
from pathlib import Path

OUT = Path(__file__).parent / "定稿.html"

HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="description" content="一份用于回归测试的合成样例，不含任何真实文章内容。">
<title>合成样例</title>
</head>
<body>
<div id="output">
<section class="wrap" style="font-size:16px;line-height:1.75;color:#333333;">

  <!-- 导读栏（结构与 templates/lead-section.html 对齐；check_all 靠 table-cell 标记识别） -->
  <section class="lead-section" style="margin:0 0 24px;padding:16px;border-radius:12px;background:#f2f7f9;border:1px solid #d7e3ea;">
    <section style="display: table; width: 100%;">
      <section style="display: table-cell; width: 64%; vertical-align: middle; text-align: left !important;">
        <section style="font-weight:bold;color:#26333a;">导读</section>
        <p style="margin:8px 0 0;color:#8a929a;font-size:14px;">一篇合成样例，用于回归测试，不含任何真实文章内容。</p>
      </section>
      <section style="display: table-cell; width: 36%; vertical-align: middle;">
        <section style="display:flex;align-items:center;justify-content:flex-end;">
          <section style="width:4px;height:20px;background:#2F6F8F;border-radius:2px;"></section>
        </section>
      </section>
    </section>
  </section>

  <!-- PART 编号 H2（format_layout 的 _build_part_h2 会注入 PART_H2_STYLE 标记注释） -->
  <!-- PART_H2_STYLE:第一节标题 -->
  <section class="h2-header" style="margin:32px 0 16px;">
    <section style="font-size:20px;font-weight:bold;color:#2F6F8F;">PART 01 &nbsp;第一节标题</section>
    <section style="height:2px;background:#d7e3ea;margin-top:8px;"></section>
  </section>

  <p style="margin:16px 0;">正文段落。段首给一个具体的数字：<span style="color:#2F6F8F;font-weight:bold;">47</span> 个版本，
  这是他给同一份方案存的文件数。</p>

  <!-- 要点卡 -->
  <section class="key-takeaway" style="margin:20px 0;padding:14px 16px;border-left:4px solid #2F6F8F;background:rgba(47, 111, 143,0.05);border-radius:10px;">
    <p style="margin:0;color:#26333a;">要点：具体到可以被证伪的细节，比形容词更值钱。</p>
  </section>

  <!-- 金句卡（出处行 = 发丝线 + 淡化右对齐；禁装饰引号实体） -->
  <section class="quote-card" style="margin:20px 0;padding:16px;border-left:4px solid #2F6F8F;background:rgba(47, 111, 143,0.05);border-radius:10px;">
    <p style="margin:0;color:#26333a;">「工具选错的代价不是效率低，是你会以为问题出在自己身上。」</p>
    <p style="margin:8px 0 0;text-align:right;font-size:13px;color:#8a929a;border-top:1px solid #eef0f2;padding-top:6px;">-- 合成样例</p>
  </section>

  <!-- 表格品牌化 -->
  <section style="overflow-x:auto;margin:20px 0;">
    <table style="width:100%;border-collapse:collapse;border-radius:10px;overflow:hidden;">
      <thead>
        <tr><th style="background:#2F6F8F;color:#ffffff;padding:10px;text-align:left;">列一</th>
            <th style="background:#2F6F8F;color:#ffffff;padding:10px;text-align:left;">列二</th></tr>
      </thead>
      <tbody>
        <tr><td style="padding:10px;border-bottom:1px solid #eef0f2;">甲</td>
            <td style="padding:10px;border-bottom:1px solid #eef0f2;">乙</td></tr>
        <tr style="background:rgba(47, 111, 143,0.03);">
            <td style="padding:10px;">丙</td><td style="padding:10px;">丁</td></tr>
      </tbody>
    </table>
  </section>

  <!-- 居中 dashed 占位块：按规则豁免 WARN -->
  <section style="text-align:center;margin:24px 0;padding:24px;border:1px dashed #d7e3ea;border-radius:10px;color:#8a929a;">
    配图占位（居中 dashed 块，按规则豁免）
  </section>

  <p style="margin:16px 0;color:#666666;font-size:14px;">如果你只想试一件事：把这份合成件跑一遍 verify_final_html。</p>

  <!-- 推荐阅读 -->
  <section style="margin: 48px 8px 0;">
    <section style="text-align: center; margin-bottom: 24px;">
      <section style="display: inline-block; font-size: 17px; font-weight: bold; color: #333333; letter-spacing: 2px;">推荐阅读</section>
      <section style="width: 56px; height: 4px; background: #2F6F8F; border-radius: 2px; margin: 8px auto 0;"></section>
    </section>
    <section style="margin: 0 0 12px; line-height: 0;">
      <a href="https://example.com/a/1"><img src="https://example.com/cover-1.png" alt="合成文章一" style="display:block; width:100%; height:auto; border-radius:8px;" /></a>
    </section>
  </section>

  <!-- 关注卡片：字段由 profile 的 identity 填入，这里是占位符 -->
  <section class="mp_profile_iframe_wrp custom_select_card_wrp">
    <mp-common-profile
      class="mpprofile js_uneditable custom_select_card mp_profile_iframe"
      data-pluginname="mpprofile"
      data-nickname="YOUR_ACCOUNT_NAME"
      data-alias="YOUR_ACCOUNT_ALIAS"
      data-headimg=""
      data-signature="一句话简介"
      data-id="REPLACE_WITH_YOUR_BIZ_ID"
      data-service_type="1">
    </mp-common-profile>
  </section>

</section>
</div>
</body>
</html>
"""

if __name__ == "__main__":
    OUT.write_text(HTML, encoding="utf-8")
    print(f"written: {OUT}")
