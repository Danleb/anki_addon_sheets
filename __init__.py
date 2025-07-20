"""Entry point for the Add-in"""

from aqt import mw
from aqt.utils import showInfo, qconnect
from aqt.qt import *


def import_from_google_sheets() -> None:
    # get the number of cards in the current collection, which is stored in
    # the main window
    card_count = mw.col.card_count()

    decks1 = mw.col.decks.all_names()
    mw.col.decks.decks["En"]
    s = ""
    for deck in decks1:
        s += deck + "\n"

    showInfo(s)

    col.decks.save(deck)
    # show a message box
    # showInfo("Card count: %d" % card_count)


action = QAction("Import from Google Sheets", mw)
qconnect(action.triggered, import_from_google_sheets)

mw.form.menuTools.addAction(action)
