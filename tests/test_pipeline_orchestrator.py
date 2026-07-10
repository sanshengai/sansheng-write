import json, subprocess, sys
import os
PIPE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "pipeline.py")

def run(args, cwd):
    return subprocess.run([sys.executable, PIPE, *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")

def test_init_writes_orchestrator_field(tmp_path):
    run(["init"], tmp_path)
    st = json.loads((tmp_path/".state.json").read_text(encoding="utf-8"))
    assert st["orchestrator"] in ("on", "off")          # 默认字段存在
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
