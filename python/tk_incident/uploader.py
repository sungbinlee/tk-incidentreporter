import time
import re
import hashlib
import logging
import getpass
from pathlib import Path

import sgtk
logger = sgtk.platform.get_logger(__name__)


class Uploader(object):
    """
    Minimal uploader that uses Ticket.title as the unique signature key.
    Title format: "<user_login> - <ErrorName or short message>"

    Uses sgtk.get_authenticated_user() to obtain the current user login if available.
    If the login is None, falls back to getpass.getuser().

    Settings expected in settings['upload']:
      - shotgun_project_id (int)
      - ticket_entity_type (str)  # default "Ticket"
      - ticket_attachment_field (str)  # default "attachments"
      - max_retries (int)  # default 3
      - backoff_base_sec (int/float)  # default 2
    """

    def __init__(self, shotgun=None, logger=None, settings=None):
        self._sg = shotgun
        self.logger = logger or logging.getLogger(__name__)
        self.settings = settings or {}

        upload_cfg = self.settings.get("upload", {}) if isinstance(self.settings, dict) else {}
        self.project_id = int(upload_cfg.get("shotgun_project_id", 190))
        self.ticket_entity_type = upload_cfg.get("ticket_entity_type", "Ticket")
        self.attach_field = upload_cfg.get("ticket_attachment_field", "attachments")
        self.max_retries = int(upload_cfg.get("max_retries", 3))
        self.backoff = float(upload_cfg.get("backoff_base_sec", 2))

    # -------------------------
    # user helpers (sgtk)
    # -------------------------
    def _get_user_login(self):
        """
        Try to get authenticated user via sgtk helper.
        Fallback to getpass.getuser().
        """
        try:
            user = sgtk.get_authenticated_user()
            if user:
                # user.login may be None for script users; fall back if needed
                login = getattr(user, "login", None)
                if login:
                    return login
                # if no login, prefer email or name if available
                email = getattr(user, "email", None)
                if email:
                    return email
                name = getattr(user, "name", None)
                if name:
                    return name
        except Exception:
            logger.debug("sgtk.get_authenticated_user() failed", exc_info=True)

        try:
            return getpass.getuser() or "unknown"
        except Exception:
            return "unknown"

    # -------------------------
    # title helpers (no timestamp/engine)
    # -------------------------
    def _strip_leading_timestamp(self, text):
        """
        Remove leading timestamp like:
        2026-01-14 19:49:11,961 ...
        and common bracketed prefixes, to avoid time/engine leaking into title.
        """
        if not text:
            return ""
        # Remove leading ISO-like datetime (YYYY-MM-DD HH:MM:SS,ms)
        txt = re.sub(r'^\s*\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}(?:,\d+)?\s*', '', text, count=1)
        # Also remove leading bracketed PID/INFO blocks like "[2764 ERROR ...]"
        txt = re.sub(r'^\s*\[[^\]]+\]\s*', '', txt, count=1)
        return txt

    def _extract_error_name(self, text):
        """Try to extract Exception/Error name (OverflowError, ValueError, ...)"""
        if not text:
            return None
        m = re.search(r'([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))', text)
        if m:
            return m.group(1)
        return None

    def _short_text(self, text, max_len=80):
        if not text:
            return ""
        s = " ".join(text.strip().split())
        return s[:max_len]

    def _make_title_signature(self, matched_line):
        """
        Title format: "<user_login> - <ErrorName or short message>"
        This removes leading timestamp/engine info from matched_line first.
        """
        user_login = self._get_user_login()
        core_line = self._strip_leading_timestamp(matched_line or "")
        err = self._extract_error_name(core_line)
        if err:
            core = err
        else:
            core = self._short_text(core_line or "Unknown error", max_len=80)
            if not core:
                core = hashlib.sha1((matched_line or "").encode("utf-8")).hexdigest()[:10]
        # sanitize to avoid newlines/tabs
        user_s = re.sub(r'[\r\n\t]+', ' ', str(user_login)).strip()
        core_s = re.sub(r'[\r\n\t]+', ' ', str(core)).strip()
        title = f"{user_s} - {core_s}"
        return title

    # -------------------------
    # ShotGrid helpers
    # -------------------------
    def _find_ticket_by_title(self, title):
        """
        Find ticket with exact title. Return dict or None.
        """
        if not self._sg:
            return None
        try:
            res = self._sg.find(self.ticket_entity_type, [["title", "is", title]], fields=["id"])
            if res:
                return res[0]
        except Exception:
            self.logger.debug("Title-based lookup failed for title=%s", title, exc_info=True)
        return None

    def _attach_log_to_ticket(self, ticket_id, log_path):
        """Upload log file to ticket (with retries)."""
        if not self._sg:
            return False
        p = Path(log_path)
        try:
            for attempt in range(1, self.max_retries + 1):
                try:
                    self._sg.upload(self.ticket_entity_type, ticket_id, str(p), field_name=self.attach_field)
                    return True
                except Exception:
                    self.logger.exception("Upload attempt %d failed for ticket %s file %s", attempt, ticket_id, str(p))
                    if attempt < self.max_retries:
                        time.sleep(self.backoff * attempt)
            return False
        except Exception:
            self.logger.exception("Attachment failed")
            return False

    # -------------------------
    # main method
    # -------------------------
    def upload_log(self, log_path, pos, trigger, snippet=None):
        """
        Create a ticket whose title is the signature. If a ticket with the same title
        already exists, do nothing and return True.
        """
        p = Path(log_path)
        if not p.exists():
            self.logger.error("Log file not found: %s", str(p))
            return False

        matched_line = trigger.get("matched_line", "")
        title = self._make_title_signature(matched_line)

        # 1) check existing ticket by exact title
        try:
            existing = self._find_ticket_by_title(title)
        except Exception:
            existing = None
            self.logger.debug("Error while searching for existing ticket title=%s", title, exc_info=True)

        if existing:
            tid = existing.get("id")
            self.logger.info("Ticket with title exists (%s). Skipping creation.", tid)
            # Do nothing (no comment, no attachment)
            return True

        # 2) create new ticket
        detected_at = trigger.get("detected_ts", time.time())
        description = (
            f"Matched line:\n{matched_line}\n\n"
            f"Detected at: {detected_at}\n"
            f"Log path: {str(p)}\n"
            f"Matched byte offset: {pos}\n"
        )

        # include signature marker for search
        description += f"\n--- INCIDENT_TITLE_SIGNATURE: {title} ---\n"

        payload_base = {"project": {"type": "Project", "id": self.project_id}, "description": description}

        created = None
        try:
            for title_field in ("title", "subject", "name"):
                try:
                    payload = dict(payload_base)
                    payload[title_field] = title
                    created = self._sg.create(self.ticket_entity_type, payload)
                    if created:
                        break
                except Exception:
                    self.logger.exception("Create attempt failed for field %s", title_field)
                    created = None
                    continue
            if not created:
                self.logger.error("Failed to create ticket for log %s", str(p))
                return False
        except Exception:
            self.logger.exception("Unexpected failure while creating ticket")
            return False

        ticket_id = created.get("id")
        if not ticket_id:
            self.logger.error("ShotGrid returned invalid ticket id: %s", str(created))
            return False

        # attach log to new ticket
        attach_ok = self._attach_log_to_ticket(ticket_id, p)
        if attach_ok:
            self.logger.info("Uploaded log %s to new ticket id=%s", p.name, ticket_id)
            return True
        else:
            self.logger.error("Attachment failed for newly created ticket %s", ticket_id)
            return False
