from sgtk.platform import Application


class ObservabilityStarterApp(Application):
    def init_app(self):
        # Collect configuration (Toolkit merges defaults + site/config)
        project_id = self.get_setting("shotgun_project_id")

        try:
            proj = self.shotgun.find_one("Project", [["id", "is", project_id]], ["id"])
        except Exception as e:
            self.logger.error(f"cannot access project_id={project_id}. skip start. ({e})")
            return

        if not proj:
            self.logger.error(f"project_id={project_id} not found or no access. skip start.")
            return

        settings = {}
        keys = ["shotgun_project_id", "ticket_entity_type"]
        for key in keys:
            value = self.get_setting(key)
            if value:
                if key in ("shotgun_project_id", "ticket_entity_type"):
                    settings.setdefault("upload", {})[key] = value
                else:
                    settings[key] = value

        # Start bootstrap, passing logger and shotgun handle
        self._tk_incident = self.import_module("tk_incident")
        self._tk_incident.bootstrap.start(logger=self.logger, shotgun=self.shotgun, settings=settings)

    def destroy_app(self):
        try:
            if hasattr(self, "_tk_incident"):
                self._tk_incident.bootstrap.stop()
        except Exception:
            self.logger.debug("Error while stopping observability bootstrap", exc_info=True)
