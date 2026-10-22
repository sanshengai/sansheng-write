"""命令执行观察：记录成功、失败、明确的等待状态与本次耗时。

只按各命令的退出码合同解释等待；失败后的成功也必须留痕，不能用旧的
单向失败记录推断最终失败率。execution_kind 区分生产、测试与未知运行。
记录失败不影响业务执行、标准输出或原退出码。
"""
from __future__ import annotations

import collections
import os
import sys
import time
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


def _record(stage: str, code: object, article: str, extra: str = "", *, elapsed_ms: float = 0) -> None:
    try:
        from contracts import log_observation

        tail = " | ".join(list(_RECENT)[-3:])
        detail = f"exit={code}" + (f"; {tail}" if tail else "") + (f" | {extra[:120]}" if extra else "")
        # Exit codes are command contracts: 3 is not globally a waiting state.
        waiting = stage == "pipeline.render-visuals" and code == 3
        verdict = "waiting_tool" if waiting else "ok" if code in (0, None) else "fail"
        kind = os.environ.get("SANSHENG_WRITE_EXECUTION_KIND", "unknown")
        if kind not in {"production", "test", "unknown"}:
            kind = "unknown"
        log_observation(
            stage, "command_exit", verdict, detail[:200], article=article,
            issue_codes=(["pending_host"] if waiting else [] if verdict == "ok" else [f"exit_{code}"]),
            metrics={"exit": str(code), "outcome": verdict, "execution_kind": kind},
            elapsed_ms=elapsed_ms,
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
    started = time.monotonic()

    def record(code: object, extra: str = "") -> None:
        _record(_resolve(stage), code, _resolve(article), extra,
                elapsed_ms=round((time.monotonic() - started) * 1000, 3))

    original = sys.stdout
    sys.stdout = _Tee(original)
    try:
        result = func(*args, **kwargs)
    except SystemExit as exc:
        record(0 if exc.code is None else exc.code)
        raise
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        record(f"exception:{type(exc).__name__}", str(exc))
        raise
    finally:
        sys.stdout = original
    record(result if isinstance(result, int) and not isinstance(result, bool) else 0)
    return result
