import os
from sgtk.platform import Application


class ObservabilityStarterApp(Application):
    def init_app(self):
        # Collect configuration (Toolkit merges defaults + site/config)
        settings = {}
        keys = ["snippet_before", "snippet_after", "shotgun_project_id", "ticket_entity_type"]
        for k in keys:
            try:
                v = self.get_setting(k)
            except Exception as e:
                v = None
                self.logger.debug(f"error : {e}")
            if v is not None and v != "":
                if k in ("shotgun_project_id", "ticket_entity_type"):
                    settings.setdefault("upload", {})[k] = v
                else:
                    settings[k] = v

        # Environment override for project id
        env_proj = os.environ.get("TK_INCIDENT_PROJECT_ID")
        if env_proj:
            try:
                settings.setdefault("upload", {})["shotgun_project_id"] = int(env_proj)
                self.logger.debug("Overriding project id from env: %s", env_proj)
            except Exception:
                self.logger.warning("Invalid TK_INCIDENT_PROJECT_ID: %s", env_proj)

        # Start bootstrap, passing logger and shotgun handle
        self._tk_incident = self.import_module("tk_incident")
        self._tk_incident.bootstrap.start(logger=self.logger, shotgun=self.shotgun, settings=settings)

    def destroy_app(self):
        try:
            if hasattr(self, "_tk_incident"):
                self._tk_incident.bootstraop.stop()
        except Exception:
            self.logger.debug("Error while stopping observability bootstrap", exc_info=True)
