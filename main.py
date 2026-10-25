"""Entry point executed by Decky Loader.

The actual implementation lives in ``py_modules`` so that it can be unit
tested without decky-loader. Adding the plugin directory to ``sys.path`` keeps
imports working no matter what the process working directory is.
"""

from __future__ import annotations

import os
import sys

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from py_modules.plugin import NavidromePlugin as Plugin  # noqa: E402

__all__ = ["Plugin"]
