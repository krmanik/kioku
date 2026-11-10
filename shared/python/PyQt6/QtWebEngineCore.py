# Every Qt WebEngine Core class kioku.webengine stands in for, so that code
# doing `from PyQt6.QtWebEngineCore import *` (aqt.qt) sees new ones without
# a list to keep up to date. QWebEngineView belongs to QtWebEngineWidgets.
from kioku import webengine as _webengine

globals().update(
    {
        name: getattr(_webengine, name)
        for name in dir(_webengine)
        if name.startswith(("QWebEngine", "qWebEngine")) and name != "QWebEngineView"
    }
)
