import sys, os, tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# 测试必须确定性地跑在仓内 profile.example 上，且绝不受维护者本机 .env 影响
# ——.env 里的 SANSHENG_WRITE_PROFILE_DIR / SANSHENG_WRITE_DATA_DIR 会把 profile 指向
# 真实品牌值、data 指向真实数据目录。os.environ 优先级高于 .env，这里显式钉死：
#   · profile → profile.example（冻结基线断言的是中性默认色，如 #2F6F8F / #d7e3ea）
#   · data    → 全新临时目录（多一道保险，任何用到 data_dir 的测试都不会碰真实作品库）
os.environ["SANSHENG_WRITE_PROFILE_DIR"] = str(_HERE / "profile.example")
_TEST_DATA = tempfile.mkdtemp(prefix="sansheng-write-test-")
os.environ["SANSHENG_WRITE_DATA_DIR"] = _TEST_DATA
# 同族指针一并钉死（.env 里它们可能直指真实作品库/私有飞轮——测试绝不能碰）。
# ⚠ 必须钉**非空实路径**：空串挡不住解析器（os env 为空会继续回落 .env）。
os.environ["SANSHENG_WRITE_WORKS_FILE"] = str(Path(_TEST_DATA) / "works.yaml")
os.environ["SANSHENG_WRITE_FLYWHEEL_DIR"] = _TEST_DATA
