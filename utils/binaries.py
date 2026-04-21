import os
import sys


def get_binary_path(name: str) -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)

    # User data dir (populated by auto_download on first run)
    from utils.auto_download import bin_dir
    user_bin = os.path.join(bin_dir(), name)
    if os.path.isfile(user_bin):
        return user_bin

    # Dev fallback: project root
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), name)
