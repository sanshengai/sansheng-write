import json, subprocess, sys
import os
PIPE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "pipeline.py")

def run(args, cwd):
    return subprocess.run([sys.executable, PIPE, *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")

def test_init_writes_orchestrator_field(tmp_path):
    run(["init"], tmp_path)
    st = json.loads((tmp_path/".state.json").read_text(encoding="utf-8"))
    # 🔴 钉死默认值本身。旧断言 `in ("on","off")` 是弱断言——默认值被改成 off
    #    也照样绿，而 outline.md 的编排开关语义正是围绕「init 默认 on」写的
    #    （2026-08-16 审计抓到文档一度写反）。默认值变更必须是显式决策。
    assert st["orchestrator"] == "on"
    assert st.get("state_writer") == "orchestrator"     # 单一写者标记

def test_orchestrator_toggle_off(tmp_path):
    run(["init"], tmp_path)
    run(["orchestrator", "off"], tmp_path)
    st = json.loads((tmp_path/".state.json").read_text(encoding="utf-8"))
    assert st["orchestrator"] == "off"

def test_orchestrator_toggle_back_on(tmp_path):
    run(["init"], tmp_path)
    run(["orchestrator", "off"], tmp_path)
    run(["orchestrator", "on"], tmp_path)
    st = json.loads((tmp_path/".state.json").read_text(encoding="utf-8"))
    assert st["orchestrator"] == "on"
