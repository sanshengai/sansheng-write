# tests/golden/_synthetic_content_enhance/make_fixtures.py
"""确定性合成内容增强 fixture 生成器（P3.2 tier-2 验证门测试用）。

与 _synthetic_research/make_fixtures.py 同构：content_enhance 合并后产物是
**纯 dict**（strategies 四键 + 可选 article_body），无二进制、无磁盘 IO ——
verify_content_enhance_set 是纯函数，只读入参。故本生成器不需临时目录，
直接手构确定性 dict 组，单一事实源由 regression_baseline.py P3 门 与
pytest 共用，hermetic、零仓库膨胀、不烧任何 LLM 增强配额。

每组返回 (strategies, article_body) 二元组，交给
contracts.verify_content_enhance_set 校验：
  - compliant            合规：4 策略各司其职、不雷同、不矛盾、有实质、与正文不脱节
  - bad_duplicate        违规①：两策略大段雷同（复制粘贴凑数）
  - bad_contradiction    违规②：某策略自相矛盾（对冲词同现）
  - bad_placeholder      违规③：某策略占位/过短（无实质）
  - bad_disjoint         违规④：某策略与正文完全脱节（跑错题）

设计要点（与 research fixture「单一违因」精神一致）：每个 bad_* 组**只**
从合规基线变异**一个**策略的**一个**维度，其余三策略保持合规基线原样，
确保该组只精确触发目标规则、不夹带无关噪声（便于 pytest/P3 门按关键词
精确断言）。策略文本刻意写成「针对初稿的增强说明」，与 content-enhance.md
四策略（angle 角度发现 / density 密度强化 / detail 细节锚定 /
texture 真实体感）语义对齐，但内容是确定性手构桩，不代表任何真实产出。
"""

# 一篇确定性「正文」桩：围绕「AI 写作工具横评」选题，供脱节关比对。
_ARTICLE_BODY = (
    "这篇文章对比了三款 AI 写作工具的真实体验。我们关注它们在长文"
    "生成、事实准确、排版导出三个场景下的表现，以及普通用户上手时"
    "最容易踩的坑。结论先行：没有全能选手，选型取决于你的具体场景。"
)

# 合规基线四策略：各司其职、均与正文相关、长度充足、无对冲词、两两不雷同。
# 所有 bad_* 组从此基线只变异一个策略的一个维度（其余三策略原样）。
_BASE = {
    "angle": "原稿平铺三款工具功能，改从「没有全能选手」这个反共识"
             "结论切入，让读者一开始就有立场与态度。",
    "density": "第二段把空泛的「体验不错」压成可操作判据：长文场景"
               "给出字数与卡顿阈值，事实场景给出出错率，排版导出"
               "场景给出格式清单。",
    "detail": "把「用户容易踩的坑」落到具体场景：导出微信公众号时"
              "某工具丢失加粗，附上当时的字数与报错画面。",
    "texture": "去掉评测腔的书面长句，换成口语短句节奏，用「你」"
               "直接对话读者，贴近真实选型时的犹豫与场景。",
}


def build_groups():
    """返回 dict[str, (strategies, article_body)]。全确定性手构。
    每个 bad_* 组从 _BASE 浅拷贝后只改一个键（单一违因）。"""
    groups = {}

    groups["compliant"] = (dict(_BASE), _ARTICLE_BODY)

    # 违规①：detail 整段照抄 density（复制粘贴凑数）——只改 detail，
    # 其余三策略原样（density 仍合规），故只触发 dedup。
    dup = dict(_BASE)
    dup["detail"] = _BASE["density"]
    groups["bad_duplicate"] = (dup, _ARTICLE_BODY)

    # 违规②：texture 内部自相矛盾——「更口语」与「更书面」同现。
    # 仍保留正文相关 token（场景/读者/评测），故只触发 no_contradiction。
    contra = dict(_BASE)
    contra["texture"] = ("整体应该改得更口语、句子更短更亲切贴近选型"
                         "场景；同时又要更书面、更严谨、更像正式评测"
                         "报告给读者——两个方向都做。")
    groups["bad_contradiction"] = (contra, _ARTICLE_BODY)

    # 违规③：detail 是占位/过短（无实质）——只改 detail。
    ph = dict(_BASE)
    ph["detail"] = "TODO 待补"  # 7 字符 < 12 且命中占位词
    groups["bad_placeholder"] = (ph, _ARTICLE_BODY)

    # 违规④：angle 与正文完全脱节（写成另一选题烹饪，零公共 token）。
    # 其余三策略原样（与正文相关），故只触发 not_disjoint 且仅 angle。
    dj = dict(_BASE)
    dj["angle"] = ("建议从家常红烧肉的火候掌控讲起，先焯水再冰糖"
                   "炒色，铁锅厚底受热均匀风味更佳。")
    groups["bad_disjoint"] = (dj, _ARTICLE_BODY)

    return groups
