import os
import sys

from pathlib import Path
import sgtk


def get_default_log_folder():
    try:
        lm = sgtk.LogManager()
        lf = lm.log_folder()
        if lf:
            return Path(lf)
    except Exception:
        pass
    if sys.platform.startswith("darwin"):
        return Path.home() / "Library" / "Logs" / "Shotgun"
    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Shotgun" / "logs"
        return Path.home() / "AppData" / "Roaming" / "Shotgun" / "logs"
    else:
        return Path.home() / ".shotgun" / "logs"
