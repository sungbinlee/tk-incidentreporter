# python/tk_incident/singleton.py
# Qt import via QtImporter
import getpass, hashlib, os
from sgtk.util.qt_importer import QtImporter

imp = QtImporter()
QtCore, QtGui, QtNetwork = imp.QtCore, imp.QtGui, imp.QtNetwork


class SingletonLock(object):
    def __init__(self, name):
        self.name = name
        self._server = None

    def acquire(self):
        try:
            server = QtNetwork.QLocalServer()
            try:
                server.removeServer(self.name)
            except Exception:
                pass
            ok = server.listen(self.name)
            if ok:
                self._server = server
                return True
            return False
        except Exception:
            return False

    def release(self):
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
