"""项目根目录启动脚本。

支持直接 ``python main.py`` 运行，无需先安装包。

包源码位于 ``src/`` 下（见 :file:`pyproject.toml` 的
``package-dir = { "" = "src" }``）。未安装时，Python 不会自动将
``src`` 加入 :data:`sys.path`，故本脚本在导入 :mod:`chatterbox`
前显式插入 ``src`` 目录（已存在则跳过，保证幂等）。

已通过 ``pip install -e .`` 安装可编辑包时，:mod:`chatterbox` 已可直接
导入，本脚本插入 ``src`` 的操作为 no-op（``sys.path`` 去重保证）。
"""

from __future__ import annotations

import os
import sys


def _ensure_src_on_path() -> None:
    """将项目 ``src`` 目录加入 :data:`sys.path`（幂等）。

    通过 :data:`sys.path` 前缀插入保证优先级，已存在则跳过。
    使用绝对路径避免工作目录差异导致导入失败。
    """
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


def main() -> int:
    """程序入口：确保 ``src`` 在路径中后委托给 :func:`chatterbox.app.main`。"""
    _ensure_src_on_path()
    from chatterbox.app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
