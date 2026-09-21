# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""QCA Service entry point."""

import os
import sys
from pathlib import Path

# Add this service's directory to path FIRST to ensure local imports take priority
service_dir = Path(__file__).parent
sys.path.insert(0, str(service_dir))

from server import app
import uvicorn


def main():
    """Run the QCA Service."""
    port = int(os.environ.get("PORT", 3011))
    host = os.environ.get("HOST", "0.0.0.0")

    print(f"Starting QCA Service on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
