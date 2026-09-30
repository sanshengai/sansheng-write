# 内置第三方库（纯 Python，MIT）

为免用户环境被系统 Python 的 pip 限制（PEP 668）拦住，`md_render.py` 用到的 Markdown 解析库直接随仓提供：

- `markdown_it/` — markdown-it-py 4.2.0（MIT，© Chris Sewell / executablebooks），许可见 `markdown_it_py-4.2.0.dist-info/licenses/`
- `mdurl/` — mdurl 0.1.2（MIT，© Taneli Hukkinen 等），许可见 `mdurl-0.1.2.dist-info/LICENSE`

升级时替换整个目录并重跑 `tests/test_md_render.py`。
