from .autostart import AgentRunner

_runner = None

def start(logger, shotgun, settings=None):
    """
    Start the AgentRunner. We accept logger and shotgun handles (from app).
    settings is an optional dict already merged from info/config/env.
    """
    global _runner
    _runner = AgentRunner(logger=logger, shotgun=shotgun, settings=settings)
    _runner.start()

def stop():
    global _runner
    if _runner:
        _runner.stop()
        _runner = None
