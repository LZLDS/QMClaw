# -*- coding: utf-8 -*-
"""
QubitClient Service 启动入口
"""

import sys
import os

# 确保项目根目录在 Python 路径中
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services.qubitclient_service.server import main

if __name__ == "__main__":
    main()
