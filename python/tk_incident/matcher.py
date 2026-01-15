import re


class Matcher(object):
    """
    detect ERROR/CRITICAL only.
    """
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.severity_re = re.compile(r"\b(ERROR|CRITICAL)\b")

    def match(self, line):
        m = self.severity_re.search(line)
        if m:
            return {"reason": "severity", "level": m.group(1), "matched_line": line}
        return None
