from sgtk.util.qt_importer import QtImporter
imp = QtImporter()
QtCore, QtGui, QtNetwork = imp.QtCore, imp.QtGui, imp.QtNetwork

from pathlib import Path
import time


class TailWorker(QtCore.QThread):
    """
    Simple tail/follow worker.
    Emits payload dict: {path, line, pos, ts}
    """
    line_detected = QtCore.Signal(object)

    def __init__(self, log_folder, glob_patterns=None, poll_interval=0.5, parent=None):
        super(TailWorker, self).__init__(parent)
        self.log_folder = Path(log_folder)
        self.glob_patterns = glob_patterns or ["tk-*.log"]
        self.poll_interval = float(poll_interval)
        self._files = {}  # path -> {"pos": int, "inode": int}

    def _register_file(self, p):
        pstr = str(p)
        if pstr in self._files:
            return
        try:
            st = p.stat()
            self._files[pstr] = {"pos": st.st_size, "inode": getattr(st, "st_ino", None)}
        except Exception:
            self._files[pstr] = {"pos": 0, "inode": None}

    def _scan_and_read(self):
        # register files
        for pattern in self.glob_patterns:
            for f in self.log_folder.glob(pattern):
                self._register_file(f)

        # read each file
        for pstr, info in list(self._files.items()):
            try:
                p = Path(pstr)
                st = p.stat()
                inode = getattr(st, "st_ino", None)

                # rotation detection
                if info.get("inode") and inode != info.get("inode"):
                    info["pos"] = 0
                    info["inode"] = inode

                # truncate detection
                if st.st_size < info.get("pos", 0):
                    info["pos"] = 0

                with open(pstr, "r", encoding="utf-8", errors="ignore") as fh:
                    fh.seek(info.get("pos", 0))
                    while True:
                        line = fh.readline()
                        if not line:
                            break
                        pos = fh.tell()
                        info["pos"] = pos
                        payload = {
                            "path": pstr,
                            "line": line.rstrip("\n"),
                            "pos": pos,
                            "ts": time.time()
                        }
                        self.line_detected.emit(payload)
            except FileNotFoundError:
                try:
                    del self._files[pstr]
                except KeyError:
                    pass
            except Exception:
                pass

    def run(self):
        while not self.isInterruptionRequested():
            try:
                self._scan_and_read()
            except Exception:
                pass
            time.sleep(self.poll_interval)
