from .singleton import SingletonLock
from .agent import AgentController

_runner = None


def start(logger, shotgun, settings=None):
    """
    Start the agent (singleton).
    """
    global _runner
    if _runner:
        logger.warning("tk-incidentreporter: already started. Not starting again.")
        return

    _runner = AgentRunner(logger=logger, shotgun=shotgun, settings=settings)
    _runner.start()


def stop():
    global _runner
    if _runner:
        _runner.stop()
        _runner = None


class AgentRunner(object):
    def __init__(self, logger, shotgun, settings=None):
        self.logger = logger
        self.shotgun = shotgun
        self.settings = settings or {}
        self.lock = SingletonLock("tk_incident_site_lock")
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