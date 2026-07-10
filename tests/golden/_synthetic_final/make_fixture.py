# -*- coding: utf-8 -*-
"""合成一份「排版后定稿.html」夹具，替代真实文章 golden。

为什么不用真实文章：公开仓不含任何真实已发布内容（版权 + 隐私）。
这份合成件刻意覆盖 verify_final_html 的全部校准点：
  - baoyu 转换器产出的 `<div id="output">` 外壳与 `class=` 属性（合法，不得误杀）
  - `display:flex`（合法，不得误杀）
  - 主题色内联样式、表格、金句卡、要点卡等典型组件
  - 一个居中的 dashed 占位块（应豁免，不产生 WARN）
且不含任何硬违规（<style>/<script>/position:fixed/grid/var(--)/@media/@keyframes/@import）。

重新生成：python tests/golden/_synthetic_final/make_fixture.py
"""
from pathlib import Path

OUT = Path(__file__).parent / "定稿.html"

HTML = """<div id="output">
<section class="wrap" style="font-size:16px;line-height:1.75;color:#333333;">

  <section class="lead" style="margin:0 0 24px;padding:16px;border-radius:12px;background:#f2f7f9;border:1px solid #d7e3ea;">
    <section style="display:flex;align-items:center;">
      <section style="width:4px;height:20px;background:#2F6F8F;border-radius:2px;margin-right:8px;"></section>
      <section style="font-weight:bold;color:#26333a;">导读</section>
    </section>
    <p style="margin:8px 0 0;color:#8a929a;font-size:14px;">一篇合成样例，用于回归测试，不含任何真实文章内容。</p>
  </section>

  <section class="h2" style="margin:32px 0 16px;">
    <section style="font-size:20px;font-weight:bold;color:#2F6F8F;">PART 01 &nbsp;第一节标题</section>
    <section style="height:2px;background:#d7e3ea;margin-top:8px;"></section>
  </section>

  <p style="margin:16px 0;">正文段落。段首给一个具体的数字：<span style="color:#2F6F8F;font-weight:bold;">47</span> 个版本，
  这是他给同一份方案存的文件数。</p>

  <section class="takeaway" style="margin:20px 0;padding:14px 16px;border-left:4px solid #2F6F8F;background:rgba(47, 111, 143,0.05);border-radius:10px;">
    <p style="margin:0;color:#26333a;">要点：具体到可以被证伪的细节，比形容词更值钱。</p>
  </section>

  <section class="quote" style="margin:20px 0;padding:16px;border-left:4px solid #2F6F8F;background:rgba(47, 111, 143,0.05);border-radius:10px;">
    <p style="margin:0;color:#26333a;">「工具选错的代价不是效率低，是你会以为问题出在自己身上。」</p>
    <p style="margin:8px 0 0;text-align:right;font-size:13px;color:#8a929a;border-top:1px solid #eef0f2;padding-top:6px;">-- 合成样例</p>
  </section>

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

  <section style="text-align:center;margin:24px 0;padding:24px;border:1px dashed #d7e3ea;border-radius:10px;color:#8a929a;">
    配图占位（居中 dashed 块，按规则豁免 WARN）
  </section>

  <p style="margin:16px 0;color:#666666;font-size:14px;">如果你只想试一件事：把这份合成件跑一遍 verify_final_html。</p>

</section>
</div>
"""

if __name__ == "__main__":
    OUT.write_text(HTML, encoding="utf-8")
    print(f"written: {OUT}")
