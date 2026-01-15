from sgtk.util.qt_importer import QtImporter
imp = QtImporter()
QtCore, QtGui, QtNetwork = imp.QtCore, imp.QtGui, imp.QtNetwork


class SingletonLock(object):
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent
        self._server = None

    def acquire(self, timeout_ms=150):
        sock = QtNetwork.QLocalSocket(self.parent)
        sock.connectToServer(self.name)
        if sock.waitForConnected(timeout_ms):
            return False

        server = QtNetwork.QLocalServer(self.parent)

        if not server.listen(self.name):
            try:
                QtNetwork.QLocalServer.removeServer(self.name)
            except Exception:
                pass
            if not server.listen(self.name):
                return False

        self._server = server
        return True

    def release(self):
        if self._server:
            try:
                name = self._server.serverName()
                self._server.close()
                QtNetwork.QLocalServer.removeServer(name)
            except Exception:
                pass
            self._server = None
