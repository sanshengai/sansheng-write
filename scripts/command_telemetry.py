"""命令级失败留痕：任何入口非零退出都写一条运行观察。

2026-09-23 审计 G6：观察日志（profile/flywheel/_skill-observations.jsonl）只记录跑完的
闸门——预检失败、发布前硬门失败、排版前置门失败、播客上传失败、官网同步失败都在
写日志之前就退出了，曾经一天 8 类失败一条都没留下，「skill 自省」看到的只是
成功路径。这里在入口处统一兜底：命令执行期间旁听标准输出里带 ❌ / 🔴 / ✗ 的行，
非零退出或未捕获异常时连同退出码写一条 ``command_exit`` 观察，然后照常退出。

记日志出任何错都不影响主流程（与 contracts.log_observation 同一原则）。
"""
from __future__ import annotations

import collections
import sys
from typing import Any, Callable

FAIL_MARKERS = ("❌", "🔴", "✗")
_RECENT: collections.deque[str] = collections.deque(maxlen=8)


def note(line: str) -> None:
    """登记一行失败信息；失败时取最近几行写进观察的 detail。"""
    text = str(line or "").strip()
    if text:
        _RECENT.append(text[:160])


class _Tee:
    """把写入转发给原 stdout，同时把带失败标记的行登记下来。"""

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._pending = ""

    def write(self, data: str) -> int:
        written = self._stream.write(data)
        try:
            self._pending += data
            *lines, self._pending = self._pending.split("\n")
            for line in lines:
                if any(marker in line for marker in FAIL_MARKERS):
                    note(line)
        except Exception:  # noqa: BLE001 - 旁听失败不能影响输出
            self._pending = ""
        return written

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def _resolve(value: str | Callable[[], str]) -> str:
    try:
        return value() if callable(value) else str(value or "")
    except Exception:  # noqa: BLE001
        return ""


def _record(stage: str, code: object, article: str, extra: str = "") -> None:
    try:
        from contracts import log_observation

        tail = " | ".join(list(_RECENT)[-3:])
        detail = f"exit={code}" + (f"; {tail}" if tail else "") + (f" | {extra[:120]}" if extra else "")
        log_observation(
            stage, "command_exit", "fail", detail[:200], article=article,
            issue_codes=[f"exit_{code}"], metrics={"exit": str(code)},
        )
    except Exception:  # noqa: BLE001 - 自省是附加价值，不是关键路径
        pass


def run_observed(stage: str | Callable[[], str], func: Callable[..., Any], *args: Any,
                 article: str | Callable[[], str] = "", **kwargs: Any) -> Any:
    """执行 ``func``；非零退出、返回非零整数或抛异常时写一条观察后照常传播。

    ``stage`` / ``article`` 可以是字符串，也可以是无参函数（命令解析完参数后才知道
    子命令名与文章目录时用）。
    """
    _RECENT.clear()
    original = sys.stdout
    sys.stdout = _Tee(original)
    try:
        result = func(*args, **kwargs)
    except SystemExit as exc:
        if exc.code not in (0, None):
            _record(_resolve(stage), exc.code, _resolve(article))
        raise
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        _record(_resolve(stage), f"exception:{type(exc).__name__}", _resolve(article), str(exc))
        raise
    finally:
        sys.stdout = original
    if isinstance(result, int) and not isinstance(result, bool) and result != 0:
        _record(_resolve(stage), result, _resolve(article))
    return result
