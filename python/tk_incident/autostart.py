from .singleton import SingletonLock
from .agent import AgentController


class AgentRunner(object):
    def __init__(self, logger, shotgun, settings=None):
        """
        logger: logger instance from app
        shotgun: Shotgun API handle (sgtk app.shotgun or engine.shotgun)
        settings: dict (from app), may contain upload.* keys and log_dir/glob_patterns
        """

        self.LoggerClass = logger.__class__
        self.logger = logger
        self.shotgun = shotgun
        self.lock = SingletonLock("tk_incident_site_lock")
        self.settings = settings or {}
        self.controller = None

    def start(self):
        if not self.lock.acquire():
            self.logger.warning("tk-incidentreporter: another instance running. Not starting.")
            return
        self.logger.info("tk-incidentreporter starting.")
        self.controller = AgentController(logger=self.logger, shotgun=self.shotgun, settings=self.settings)
        self.controller.start()

    def stop(self):
        if self.controller:
            self.controller.stop()
            self.controller = None
        try:
            self.lock.release()
        except Exception:
            pass
        self.logger.info("tk-incidentreporter stopped.")
