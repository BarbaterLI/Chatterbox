"""pytest 根级配置：将 src/ 加入 sys.path 以便测试发现包。

pyproject.toml 的 [tool.pytest.ini_options] 未配置 pythonpath，
因此通过 conftest.py 在导入前注入 src 路径。
"""
import sys
from pathlib import Path

_SRC_DIR = str(Path(__file__).parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
