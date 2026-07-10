# tests/golden/_synthetic_review/make_fixtures.py
"""确定性合成审稿 verdicts fixture 生成器（P5.2 tier-2 验证门测试用）。

与 _synthetic_research / _synthetic_content_enhance/make_fixtures.py 同构：
审稿 team fan-out 收齐后产物是 **纯 list[dict]**（verdicts 每项
{role,issues,pass}），无二进制、无磁盘 IO —— verify_review_set 是纯函数，
只读入参。故本生成器不需临时目录，直接手构确定性组，单一事实源由
regression_baseline.py P5 门 与 pytest 共用，hermetic、零仓库膨胀、
不烧任何 LLM 审稿配额（真实 TeamCreate 三角色端到端延 P6/人工）。

每组返回 verdicts(list[dict])，交给 contracts.verify_review_set 校验：
  - compliant            合规：三角色齐、pass=false 均带 issues、无 pass-true-却带 issues
  - bad_too_few_roles    违规①：只覆盖 2 个不同 role（缺事实核查维度）
  - bad_fail_no_issues   违规②：某 role pass=false 但 issues 为空（无效裁决）
  - bad_inconsistent     违规③：某 role pass=true 却携带非空 issues（弱不一致）

设计要点（与 research/content_enhance fixture「单一违因」精神一致）：
每个 bad_* 组**只**从合规基线变异**一个**维度，其余保持合规基线原样，
确保该组只精确触发目标规则、不夹带无关噪声（便于 pytest/P5 门按规则名
精确断言）。三角色 = 风格审 / 铁律审 / 事实核查，与 autopilot.md 审稿
team SOP / agent-contracts.md review 节对齐，但内容是确定性手构桩，
不代表任何真实审稿产出。
"""

# 合规基线三角色：覆盖 ≥3 不同 role；pass=false 的均带非空 issues；
# pass=true 的 issues 为空（无 pass-true-却带 issues 的弱不一致）。
_BASE = [
    {"role": "风格审", "issues": [], "pass": True},
    {"role": "铁律审", "issues": ["第3段出现尾部总结句，违反无尾部总结铁律"],
     "pass": False},
    {"role": "事实核查", "issues": ["第5段价格未标官网信源"], "pass": False},
]


def build_groups():
    """返回 dict[str, list[dict]]。全确定性手构。
    每个 bad_* 组从 _BASE 深拷贝后只改一个维度（单一违因）。"""
    def _clone():
        return [dict(v, issues=list(v["issues"])) for v in _BASE]

    groups = {}

    groups["compliant"] = _clone()

    # 违规①：只覆盖 2 个不同 role（去掉事实核查那条，且把铁律审复制
    # 一份凑数 —— 去重后仍只 2 个 role，触发 roles_min）。其余裁决本身
    # 合规（pass=false 带 issues），故只精确触发规则①。
    few = [
        {"role": "风格审", "issues": [], "pass": True},
        {"role": "铁律审", "issues": ["第3段尾部总结句"], "pass": False},
        {"role": "铁律审", "issues": ["第7段连续两句副词开头"], "pass": False},
    ]
    groups["bad_too_few_roles"] = few

    # 违规②：事实核查 pass=false 但 issues 空（无效裁决）。三角色仍齐、
    # 其余两条合规，故只精确触发规则② fail_needs_issues。
    fni = _clone()
    fni[2] = {"role": "事实核查", "issues": [], "pass": False}
    groups["bad_fail_no_issues"] = fni

    # 违规③：风格审 pass=true 却携带非空 issues（弱不一致）。三角色仍齐、
    # pass=false 的均带 issues，故只精确触发规则③ verdict_consistency。
    inc = _clone()
    inc[0] = {"role": "风格审",
              "issues": ["句长方差不足但仍判通过"], "pass": True}
    groups["bad_inconsistent"] = inc

    return groups
