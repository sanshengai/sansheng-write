# tests/golden/_synthetic_research/make_fixtures.py
"""确定性合成调研 fixture 生成器（P2.2 tier-2 验证门测试用）。

与 _synthetic_infographic/make_fixtures.py 同构，但 research 产物是**纯 dict**
（findings/sources），无二进制、无磁盘 IO —— verify_research_set 是纯函数，
只读入参。故本生成器不需临时目录，直接手构确定性 dict 组，单一事实源由
regression_baseline.py P2 门 与 pytest 共用，hermetic、零仓库膨胀、
不烧 AnySearch/Tavily 检索配额。

每组返回 (findings, sources) 二元组，交给 contracts.verify_research_set 校验：
  - compliant            合规：findings 有实质 support、≥3 去重源、版本类有官网源
  - bad_no_support       违规①：finding 缺 support
  - bad_sources_few      违规②：去重后仅 2 条源（< _MIN_SOURCES=3）
  - bad_vpd_no_official   违规③：版本/价格类 finding 但全集无官网级源
  - bad_empty_url        违规④：某 source url 为空
"""

# 官网级 source（tier=官网 / 官方 host 前缀 / 官方路径）——合规组用
_SRC_OFFICIAL = {"title": "OpenAI 官方定价页", "url": "https://openai.com/pricing",
                 "tier": "官网", "accessed": "2026-05-19"}
_SRC_MEDIA = {"title": "The Verge 报道", "url": "https://www.theverge.com/2026/ai-news",
              "tier": "权威媒体", "accessed": "2026-05-19"}
_SRC_DOCS = {"title": "API 文档", "url": "https://docs.example-ai.com/changelog",
             "tier": "官网", "accessed": "2026-05-19"}
# 二手转述（社媒/UGC）—— 命中 _NON_OFFICIAL_HOSTS，非官网级
_SRC_ZHIHU = {"title": "知乎讨论", "url": "https://zhuanlan.zhihu.com/p/12345",
              "tier": "社区", "accessed": "2026-05-19"}
_SRC_36KR = {"title": "36氪转述", "url": "https://36kr.com/p/678",
             "tier": "权威媒体", "accessed": "2026-05-19"}
_SRC_WEIBO = {"title": "微博热议", "url": "https://weibo.com/abc",
              "tier": "社区", "accessed": "2026-05-19"}


def build_groups():
    """返回 dict[str, (findings, sources)]。全确定性手构。"""
    groups = {}

    # 合规：finding 有 claim+support；版本类 finding 有官网源；去重 3 源
    groups["compliant"] = (
        [
            {"claim": "GPT 新版定价为每百万 token 5 美元",
             "support": "官网 pricing 页明确列出该价格",
             "confidence": "high"},
            {"claim": "用户更倾向线下体验",
             "support": "竞品文章与社区讨论均指向此趋势",
             "confidence": "need_verify"},
        ],
        [_SRC_OFFICIAL, _SRC_MEDIA, _SRC_ZHIHU],  # 去重后 3 条
    )

    # 违规①：finding 缺 support（结论无证据）
    groups["bad_no_support"] = (
        [
            {"claim": "某趋势成立", "support": "", "confidence": "high"},
            {"claim": "另一观点"},  # 连 support 键都没有
        ],
        [_SRC_OFFICIAL, _SRC_MEDIA, _SRC_DOCS],
    )

    # 违规②：去重后仅 2 条源（_SRC_MEDIA 重复一次仍算 1）
    groups["bad_sources_few"] = (
        [
            {"claim": "纯观点结论", "support": "有社区与媒体讨论佐证",
             "confidence": "need_verify"},
        ],
        [_SRC_MEDIA, dict(_SRC_MEDIA), _SRC_ZHIHU],  # 归一化后只剩 2 个不同 url
    )

    # 违规③：版本/价格类 finding，但全集无官网级源（全是社媒/二手）
    groups["bad_vpd_no_official"] = (
        [
            {"claim": "新模型价格从 v3 涨到每月 200 美元",
             "support": "多个社区帖子提到这个数字",
             "confidence": "high"},
            {"claim": "普通观点", "support": "有讨论支撑",
             "confidence": "need_verify"},
        ],
        [_SRC_ZHIHU, _SRC_36KR, _SRC_WEIBO],  # 3 条但全非官网级
    )

    # 违规④：某 source url 为空
    groups["bad_empty_url"] = (
        [
            {"claim": "结论 A", "support": "证据 A", "confidence": "high"},
        ],
        [_SRC_OFFICIAL, {"title": "无链接源", "url": "", "tier": "社区"},
         _SRC_MEDIA, _SRC_ZHIHU],
    )

    return groups
