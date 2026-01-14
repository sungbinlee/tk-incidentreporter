import re
import time
import threading
from collections import defaultdict, deque
import queue
from sgtk.util.qt_importer import QtImporter

imp = QtImporter()
QtCore, QtGui, QtNetwork = imp.QtCore, imp.QtGui, imp.QtNetwork

from .tail_worker import TailWorker
from .matcher import Matcher
from .uploader import Uploader
from .utils import get_default_log_folder


class AgentController(QtCore.QObject):
    """
    AgentController with:
    - improved signature extraction (exception class)
    - per-signature burst detection + blacklist
    - global throttling
    - async uploader via bounded queue + worker thread
    """

    def __init__(self, logger, shotgun, settings=None):
        super(AgentController, self).__init__()
        self.logger = logger
        self.shotgun = shotgun
        self.settings = settings or {}

        # Flood protection params
        self.cooldown_sec = int(self.settings.get("cooldown_sec", 60))  # per-signature cooldown (not primary here)
        self.window_sec = 60
        self.max_uploads_per_window = int(self.settings.get("max_uploads_per_minute", 10))

        # Burst detection params
        self.burst_threshold = int(self.settings.get("burst_threshold", 5))      # occurrences
        self.burst_window = int(self.settings.get("burst_window", 10))           # seconds
        self.blackout_period = int(self.settings.get("blackout_period", 300))   # seconds

        # State
        self._last_seen = {}                     # signature -> last_ts (for cooldown)
        self._sig_hits = defaultdict(deque)      # signature -> deque([timestamps])
        self._blacklist = {}                     # signature -> until_ts
        self._upload_timestamps = deque()        # global upload timestamps

        # uploader and async queue
        self.uploader = Uploader(shotgun=self.shotgun, logger=self.logger, settings=self.settings)
        self._upload_queue = queue.Queue(maxsize=int(self.settings.get("upload_queue_maxsize", 32)))
        self._uploader_worker = threading.Thread(target=self._uploader_worker, daemon=True)
        self._uploader_running = True
        self._uploader_worker.start()

        # other
        self.worker = None
        self.matcher = Matcher(self.settings)

    def start(self):
        self.logger.info("AgentController.start()")
        log_dir = self.settings.get("log_dir")
        if not log_dir:
            try:
                lf = get_default_log_folder()
                log_dir = str(lf)
            except Exception:
                log_dir = str(get_default_log_folder())
        patterns = self.settings.get("glob_patterns", ["tk-*.log"])
        self.worker = TailWorker(log_dir, patterns)
        self.worker.line_detected.connect(self._on_line)
        self.worker.start()

    def stop(self):
        self.logger.info("AgentController.stop()")
        # stop tail worker
        if self.worker:
            self.worker.requestInterruption()
            self.worker.wait(2000)
            self.worker = None
        # stop uploader worker
        self._uploader_running = False
        try:
            # unblock queue if waiting
            self._upload_queue.put_nowait(None)
        except Exception:
            pass
        self._uploader_worker.join(timeout=2)

    # ---------------------------
    # signature & burst helpers
    # ---------------------------
    def _extract_exception_name(self, text):
        """
        Try to extract exception class like 'OverflowError' or 'ValueError' etc.
        Return lowercased name if found, else None.
        """
        if not text:
            return None
        m = re.search(r'([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))', text)
        if m:
            return m.group(1).lower()
        return None

    def _make_signature(self, text):
        exc = self._extract_exception_name(text)
        if exc:
            return exc
        # fallback: normalized small hash-like string (simple normalization)
        norm = " ".join((text or "").strip().lower().split())
        import hashlib
        return hashlib.sha1(norm.encode("utf-8")).hexdigest()

    def _is_blacklisted(self, sig, now):
        until = self._blacklist.get(sig)
        if until and now < until:
            return True
        elif until and now >= until:
            del self._blacklist[sig]
        return False

    def _record_sig_hit_and_check_burst(self, sig, now):
        dq = self._sig_hits[sig]
        dq.append(now)
        # evict older than burst_window
        while dq and (now - dq[0] > self.burst_window):
            dq.popleft()
        if len(dq) >= self.burst_threshold:
            # enter blackout
            self._blacklist[sig] = now + self.blackout_period
            # clear hits to avoid repeated immediate blacklisting
            dq.clear()
            self.logger.warning("Signature %s entered blackout until %s due to burst", sig, self._blacklist[sig])
            return True
        return False

    # ---------------------------
    # global throttle helpers
    # ---------------------------
    def _can_upload_global(self, now):
        # evict old
        while self._upload_timestamps and (now - self._upload_timestamps[0] > self.window_sec):
            self._upload_timestamps.popleft()
        return len(self._upload_timestamps) < self.max_uploads_per_window

    def _record_upload(self, now):
        self._upload_timestamps.append(now)

    # ---------------------------
    # uploader worker
    # ---------------------------
    def _uploader_worker(self):
        while self._uploader_running:
            try:
                item = self._upload_queue.get()
                if item is None:
                    break
                log_path, pos, matched = item
                try:
                    ok = self.uploader.upload_log(log_path, pos, matched)
                    if ok:
                        self._record_upload(time.time())
                except Exception:
                    self.logger.exception("Uploader worker failed for %s", log_path)
                finally:
                    self._upload_queue.task_done()
            except Exception:
                # unexpected errors in worker loop
                self.logger.exception("Uploader worker loop error")
                time.sleep(0.5)

    # ---------------------------
    # main slot
    # ---------------------------
    @QtCore.Slot(dict)
    def _on_line(self, payload):
        try:
            matched = self.matcher.match(payload["line"])
            if not matched:
                return

            matched_line = matched.get("matched_line", "")
            now = payload.get("ts", time.time())
            sig = self._make_signature(matched_line)

            # check blacklist
            if self._is_blacklisted(sig, now):
                self.logger.debug("Skipping blacklisted sig=%s", sig)
                return

            # per-signature cooldown (simple)
            last = self._last_seen.get(sig, 0)
            if sig and (now - last) < self.cooldown_sec:
                # still in cooldown for this signature
                # but still record hit to catch burst
                self._record_sig_hit_and_check_burst(sig, now)
                self.logger.debug("Skipping upload due cooldown sig=%s", sig)
                return

            # check global throttle
            if not self._can_upload_global(now):
                self.logger.warning("Global upload throttle reached: skipping upload at %s", now)
                # still record sig hit to detect burst
                self._record_sig_hit_and_check_burst(sig, now)
                return

            # check burst detection: returns True if we just entered blackout
            entered_blackout = self._record_sig_hit_and_check_burst(sig, now)
            if entered_blackout:
                # just blacklisted; skip upload
                return

            # Passed all guards: enqueue upload (non-blocking)
            try:
                self._upload_queue.put_nowait((payload["path"], payload.get("pos", 0), matched))
                # update last_seen immediately to provide per-signature cooldown
                self._last_seen[sig] = now
                self.logger.debug("Enqueued upload for sig=%s path=%s", sig, payload["path"])
            except queue.Full:
                self.logger.warning("Upload queue full: skipping upload for %s", payload["path"])
                # record hit (to detect burst)
                # do not change last_seen so cooldown won't be reset
                self._record_sig_hit_and_check_burst(sig, now)

        except Exception:
            self.logger.exception("Error processing detected line.")
