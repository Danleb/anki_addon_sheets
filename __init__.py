"""
Anki add-on for one-way syncing with Google Sheets tables representing Anki decks.

Name: Google Sheets Syncer - goosheesy

It performs a way-one sync:
* Google Sheets -> Anki decks

In spreadsheet, each sheet (table) corresponds to one Anki deck with the same name.

"""

import logging
import sys
import os.path
import os
import platform

# handle debugging
WAIT_FOR_DEBUGGER_ATTACHED = False
if WAIT_FOR_DEBUGGER_ATTACHED:
    # disable warning about debugging frozen modules
    os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

    # load package for debugging
    here = os.path.dirname(__file__)
    dev_dir = os.path.join(here, "addon_packages_dev")
    if os.path.exists(dev_dir) and dev_dir not in sys.path:
        sys.path.insert(0, dev_dir)

    # fix debugging
    import threading
    if not hasattr(threading, "__file__"):
        # best-effort fallback: point at the stdlib threading.py location
        threading.__file__ = os.path.join(os.path.dirname(os.__file__), "threading.py")

    import debugpy
    DEBUGGER_PORT = 5678
    debugpy.listen(("localhost", DEBUGGER_PORT))
    debugpy.wait_for_client()

# handle loading of dependencies
def get_addon_dir() -> str:
    addon_dir: str = os.path.dirname(__file__)
    return addon_dir


def get_packages_dir() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize common arch names
    if machine not in ("x86_64", "amd64"):
        raise Exception(f"Not supported CPU architecture: {machine}")

    deps_dir = os.path.join(get_addon_dir(), "vendor")

    if system == "windows":
        return os.path.join(deps_dir, "win_amd64")
    if system == "linux":
        return os.path.join(deps_dir, "linux_amd64")

    raise Exception("Not supported OS: %s", deps_dir)


def loaded_addon_packages(packages_dir: str) -> None:
    # load regular addon packages
    if os.path.exists(packages_dir) and packages_dir not in sys.path:
        sys.path.append(packages_dir)


loaded_addon_packages(get_packages_dir())


# regular entry
import json
from aqt import mw
from aqt.utils import showInfo
from aqt.qt import qconnect
from aqt.addons import AddonManager
from anki.decks import DeckManager, DeckDict
from anki.cards import Card, CardId
from anki.notes import Note
from anki.collection import Collection
from anki.hooks import wrap
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QDockWidget, QLabel, QVBoxLayout, QWidget, QLineEdit, QPushButton, QHBoxLayout, QLayout, QFrame, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt
from types import SimpleNamespace
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from googleapiclient._apis.drive.v3.schemas import FileList
    from googleapiclient._apis.drive.v3.resources import DriveResource
    from googleapiclient._apis.drive.v3.schemas import File
    from googleapiclient._apis.drive.v3.resources import FileListHttpRequest
    from googleapiclient._apis.sheets.v4.resources import SheetsResource
    from googleapiclient._apis.sheets.v4.resources import BatchUpdateSpreadsheetRequest
    from googleapiclient._apis.sheets.v4.resources import SheetProperties
    from googleapiclient._apis.sheets.v4.resources import AddSheetRequest
    from googleapiclient._apis.sheets.v4.resources import AddSheetResponse
else:
    DriveResource = Any
    SheetsResource = Any

type RemoteDeck = Dict[str, str]

APPLICATION_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

USER_DATA_DIR: str = "user_files"
ADDON_NAME: str = "goosheesy"
ADDON_CONFIG: str = ADDON_NAME + ".json"
LOG_FILENAME: str = "goosheesy.log"
VERSION_FILE: str = "version.txt"


def get_icon() -> QIcon:
    icon_path = os.path.join(get_addon_dir(), "icon.png")
    return QIcon(icon_path)


def show_message_box(icon: QMessageBox.Icon, title: str, message: str) -> None:
    message_box = QMessageBox()
    message_box.setIcon(icon)
    message_box.setText(message)
    message_box.setWindowTitle(title)
    message_box.setWindowIcon(get_icon())
    message_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    message_box.exec()


def show_info(title: str, message: str) -> None:
    return show_message_box(QMessageBox.Icon.Information, title, message)


def show_error(title: str, message: str) -> None:
    return show_message_box(QMessageBox.Icon.Critical, title, message)


# ============================================================================================
# TODO extract all Google Sheets logic to a separate Python file
class NoCredentialsException(Exception):
    """Application failed to get credentials for Google API"""

    def __init__(self, *args, msg='No credentials for Google API', **kwargs):
        super().__init__(msg, *args, **kwargs)


def get_credentials(credentials_file: str):
    """Returns user authorization credentials (token) for Google API. Performs user authentication in browser if needed"""

    # do lazy importing to mitigate the issue with .pyd files from cryptography module preventing the add-on from uninstalling
    import google.auth
    import google.oauth2.credentials
    import google.auth.external_account_authorized_user
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    type Credentials = google.auth.external_account_authorized_user.Credentials | google.oauth2.credentials.Credentials
    creds: Optional[Credentials] = None

    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file("token.json", APPLICATION_SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, APPLICATION_SCOPES)
            creds = flow.run_local_server(port=0)

        if not creds:
            raise NoCredentialsException()

        # Save the credentials for the next run
        with open("token.json", "w", encoding="utf8") as token:
            token.write(creds.to_json())

    if not creds:
        raise NoCredentialsException()

    return creds


def find_spreadsheets(drive_service: DriveResource, target_substring: str) -> List[str]:
    """Find in the specified Google Drive account all Google Spreadsheets whose name contains the specified substring"""

    # https://developers.google.com/workspace/drive/api/guides/mime-types
    GOOGLE_SPREADSHEET_MIME_TYPE: str = "application/vnd.google-apps.spreadsheet"

    ids: List[str] = []
    next_page_token: str = ""

    logging.debug("Starting search for spreadsheets with name with substring: %s", target_substring)
    while True:
        files: DriveResource.FilesResource = drive_service.files()
        request: FileListHttpRequest = files.list(
            pageToken=next_page_token,
            pageSize=10, fields="nextPageToken, files(id, name)",
            q=f"mimeType='{GOOGLE_SPREADSHEET_MIME_TYPE}' and 'me' in owners and trashed=false and name contains '{target_substring}'")
        
        results: FileList = request.execute()
        next_page_token = results.get("nextPageToken")  # type: ignore
        items = results.get("files", [])

        # if not items:
        #     print("No files found.")
        #     raise Exception(
        #         f"No spreadsheets found with name {target_substring}")

        logging.debug("Next chunk of files:")
        for item in items:
            spreadsheest_name: str = item['name']  # type: ignore
            spreadsheet_id: str = item['id']  # type: ignore
            logging.debug("Spreadsheet name: %s, spreadsheet ID: %s", spreadsheest_name, spreadsheet_id)
            ids.append(spreadsheet_id)

        if not next_page_token:
            break

        # except HttpError as error:
            # TODO(developer) - Handle errors from drive API.
            # print(f"An error occurred: {error}")
            # break;

    return ids


class AddonConfig:
    def __init__(self, credentials_file: str, sync_config_file: str):
        self.credentials_file = credentials_file
        self.sync_config_file = sync_config_file

    credentials_file: str
    sync_config_file: str


def get_google_sheets_deck(drive_service: DriveResource, sheets_service: SheetsResource, spreadsheet_name: str, sheet_name:str) -> RemoteDeck:
    """Go to Google Sheets spreadsheet sheet and gather all cards from there."""

    spreadsheet_ids: List[str] = find_spreadsheets(drive_service, spreadsheet_name)
    spreadsheet_id: str = spreadsheet_ids[0]

    # final_sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    # sheets = final_sheet_metadata.get('sheets', '')
    sheet: SheetsResource.SpreadsheetsResource = sheets_service.spreadsheets()
    result = (
        sheet.values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A:B")
        .execute()
    )
    values = result.get("values", [])

    deck: RemoteDeck = {}

    for row in values:
        if len(row) < 2:
            logging.debug("Skipping not full line.")
            continue

        CARD_KEY_COLUMN_INDEX = 0
        CARD_VALUE_COLUMN_INDEX = 1

        card_key: str = row[CARD_KEY_COLUMN_INDEX]
        card_value: str = row[CARD_VALUE_COLUMN_INDEX]
        deck[card_key] = card_value

    return deck

# ============================================================================================

def sync_deck(config: AddonConfig, spreadsheet_name: str, sheet_name: str, anki_deck_name: str):
    """Update local Anki deck with cards from remote deck: 
          * Iterate over existing Anki cards and find matching card in the remote deck:
             * If the card description differs, update it
             * If the card is absent in the remote deck, delete it from Anki deck
          * Add new cards from the remote deck which are absent in the Anki deck
    """

    # do lazy importing to mitigate the issue with .pyd files from cryptography module preventing the add-on from uninstalling
    from googleapiclient import discovery
    from googleapiclient.discovery import Resource

    credentials = get_credentials(config.credentials_file)
    sheets_service: SheetsResource = discovery.build("sheets", "v4", credentials=credentials)
    drive_service: DriveResource = discovery.build("drive", "v3", credentials=credentials)
    remote_deck: RemoteDeck = get_google_sheets_deck(drive_service, sheets_service, spreadsheet_name, sheet_name)

    deck_id = mw.col.decks.id_for_name(anki_deck_name)
    if deck_id is None:
        show_error("Error", f"Failed to find Anki deck: {anki_deck_name}")
        return
    
    card_ids = mw.col.decks.cids(deck_id)

    removed_card_count = 0
    added_card_count = 0
    updated_card_count = 0

    for card_id in card_ids:
        card: Card = mw.col.get_card(card_id)
        card_note: Note = card.note()
        card_key: str = card_note['Front']
        remote_card_value = remote_deck.get(card_key)
        if remote_card_value is None:
            logging.info("The card is absent in remote deck, deleting it from the Anki deck, card key: %s", card_key)
            mw.col.remove_notes_by_card([card_id])
            removed_card_count = removed_card_count + 1
        else:
            anki_card_value = card.note()['Back']
            if not remote_card_value == anki_card_value:
                logging.info("Updating description for the card: %s", card_key)
                card_note['Back'] = remote_card_value
                mw.col.update_note(card_note)
                updated_card_count = updated_card_count + 1

    for card_key, card_value in remote_deck.items():
        query = f'deck:"{anki_deck_name}" front:"{card_key}"'
        cids = mw.col.find_cards(query)
        if not cids:
            logging.info("Creating new card: %s", card_key)
            deck_id = mw.col.decks.id_for_name(anki_deck_name)
            model = mw.col.models.by_name("Basic")
            note = mw.col.new_note(model)
            note["Front"] = card_key
            note["Back"] = card_value
            mw.col.add_note(note, deck_id)
            added_card_count = added_card_count + 1
            logging.info("Added new card: %s", card_key)

    logging.info("Finished syncing deck: %s", anki_deck_name)
    show_info(f"Success - {anki_deck_name}", f"Synced dech {anki_deck_name}, new cards added: {added_card_count}, updated cards: {updated_card_count}, deleted cards: {removed_card_count}")


def try_sync_deck(config: AddonConfig, spreadsheet_name: str, sheet_name: str, anki_deck_name: str):
    try:
        sync_deck(config, spreadsheet_name, sheet_name, anki_deck_name)
    except Exception as error:
        show_error("Error", f"Failed to sync sheet: '{spreadsheet_name}'-'{sheet_name}' with deck '{anki_deck_name}', {type(error).__name__} - {error}")


def get_user_data_dir() -> str:
    user_data_dir: str = os.path.join(get_addon_dir(), USER_DATA_DIR)
    return user_data_dir


def get_addon_config_path() -> str:
    addon_config: str = os.path.join(get_user_data_dir(), ADDON_CONFIG)
    return addon_config


def load_addon_config() -> AddonConfig:
    """Load add-on configuration from JSON file"""
    addon_config_file: str = get_addon_config_path()
    logging.info("Loading local addon config from: %s", addon_config_file)

    config: AddonConfig = AddonConfig("", "")
    if not os.path.exists(addon_config_file):
        return config

    with open(addon_config_file, "r", encoding="utf8") as data:
        config_json = json.load(data, object_hook=lambda d: SimpleNamespace(**d))

    config.credentials_file = getattr(config_json, "credentials_file", "")
    config.sync_config_file = getattr(config_json, "sync_config_file", "")

    return config


def select_file() -> str | None:
    dialog = QFileDialog()
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    dialog.setNameFilter("JSON configuration (*.json)")
    dialog.setViewMode(QFileDialog.ViewMode.List)
    if dialog.exec():
        filenames = dialog.selectedFiles()
        if len(filenames) > 0:
            return filenames[0]
    return None


def save_addon_config(config: AddonConfig):
    """Save add-on configuration into JSON file"""

    addon_config_file: str = get_addon_config_path()
    logging.info("Saving add-on configuration to %s", addon_config_file)

    config_json: Any = {}
    config_json["credentials_file"] = config.credentials_file
    config_json["sync_config_file"] = config.sync_config_file

    with open(addon_config_file, "w+", encoding="utf8") as json_file:
        json.dump(config_json, json_file, indent=4)    


def goosheesy_settings():
    """Opens GUI window with add-on settings"""
    mw.settingsWidget = widget = QWidget()
    widget.setWindowTitle("Settings for Google Sheets import")
    widget.setWindowIcon(get_icon())

    config: AddonConfig = load_addon_config()

    layout = QVBoxLayout(widget)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    # credentials file
    credentials_label = QLabel("Credentials file:")
    layout.addWidget(credentials_label)

    credentials_textbox = QLineEdit()
    credentials_textbox.setMinimumWidth(700)

    def on_select_credentials_file():
        credentials_file: str | None = select_file()
        if credentials_file is None:
            pass
        elif os.path.exists(credentials_file):
            credentials_textbox.setText(credentials_file)
        elif not len(credentials_file) == 0:
            show_error("Error", "Failed to select credentials file!")

    credentials_textbox.setText(config.credentials_file)
    select_button = QPushButton("Select")
    qconnect(select_button.clicked, on_select_credentials_file)

    credentials_row = QHBoxLayout()
    credentials_row.addWidget(credentials_textbox)
    credentials_row.addWidget(select_button)
    layout.addLayout(credentials_row)

    # synchronization configuration file
    sync_config_label = QLabel("Synchronization configuration file:")
    layout.addWidget(sync_config_label)

    sync_config_textbox = QLineEdit()
    sync_config_textbox.setMinimumWidth(700)

    def on_select_sync_config_file():
        sync_config_file: str | None = select_file()
        if sync_config_file is None:
            pass
        elif os.path.exists(sync_config_file):
            sync_config_textbox.setText(sync_config_file)
        elif not len(sync_config_file) == 0:
            show_error("Error", "Failed to select synchronization configuration file!")

    sync_config_textbox.setText(config.sync_config_file)
    select_sync_config_button = QPushButton("Select")
    qconnect(select_sync_config_button.clicked, on_select_sync_config_file)

    sync_config_row = QHBoxLayout()
    sync_config_row.addWidget(sync_config_textbox)
    sync_config_row.addWidget(select_sync_config_button)
    layout.addLayout(sync_config_row)

    # apply and close buttons
    def on_apply():
        config.credentials_file = credentials_textbox.text()
        config.sync_config_file = sync_config_textbox.text()
        save_addon_config(config)
        widget.close()

    def on_close():
        widget.close()

    bottom_row = QHBoxLayout()
    apply_button = QPushButton("Apply")
    qconnect(apply_button.clicked, on_apply)
    bottom_row.addWidget(apply_button)

    close_button = QPushButton("Close")
    qconnect(close_button.clicked, on_close)
    bottom_row.addWidget(close_button)

    layout.addLayout(bottom_row)

    widget.resize(widget.sizeHint())
    widget.adjustSize()
    widget.show()


def goosheesy_import():
    """Opens GUI window with configured decks for synchronization, executes process of syncing."""

    if mw is None:
        logging.error("mw is None.")
        return

    col: Collection | None = mw.col
    if col is None:
        logging.error("Collection mw.col is None.")
        return

    decks: DeckManager = col.decks
    if decks is None:
        logging.error("DeckManager mw.col.decks is None.")
        return

    config: AddonConfig = load_addon_config()

    if not os.path.exists(config.credentials_file) or not os.path.exists(config.sync_config_file):
        show_error("Error - Configuration files missing or not exist", "Configure sheets and decks first in the 'Settings for Google Sheets import' menu!")
        return

    # current_directory = os.getcwd()
    # backup_dir = os.path.join(current_directory, "backups")
    # logging.info("Starting creating database backup in %s", backup_dir)
    # if not os.path.exists(backup_dir):
    #     os.makedirs(backup_dir)
    # col.create_backup(backup_folder=backup_dir, force=True, wait_for_completion=True)
    # logging.info("Backup created.")

    logging.info("Path to the Anki collections database file: %s", col.path)
    logging.info("Showing available decks:")
    for d in decks.all_names_and_ids():
        logging.info("Id: %s %s", d.id, d.name)

    mw.importWidget = widget = QWidget()
    widget.setWindowTitle("Import from Google Sheets")
    widget.setWindowIcon(get_icon())
    layout = QVBoxLayout(widget)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    logging.info("Loading sync config: %s.", config.sync_config_file)
    with open(config.sync_config_file, "r", encoding="utf8") as data:
        import_config_json = json.load(data, object_hook=lambda d: SimpleNamespace(**d))

    for spreadsheet_settings in import_config_json.synchronization_map:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        spreadsheet_name = spreadsheet_settings.spreadsheet_name
        spreadsheet_label = QLabel(f"Spreadsheet: {spreadsheet_name}")
        spreadsheet_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(spreadsheet_label)

        for sheet_settings in spreadsheet_settings.sheets:
            sheet_name = sheet_settings.sheet_name
            anki_deck_name = sheet_settings.deck_name

            sheet_label = QLabel(f"Sheet: {sheet_name} -> Deck: {anki_deck_name}")

            anki_deck: DeckDict | None = decks.by_name(anki_deck_name)
            if anki_deck is None:
                sheet_label.setStyleSheet("color: red;") 

            def on_sync_one_deck(
                _checked: bool,
                spreadsheet_name: str = spreadsheet_name,
                sheet_name: str = sheet_name,
                anki_deck_name: str = anki_deck_name,
            ):
                try_sync_deck(config, spreadsheet_name, sheet_name, anki_deck_name)

            sync_button = QPushButton("Sync")
            sync_button.setFixedWidth(100)
            qconnect(sync_button.clicked, on_sync_one_deck)

            row = QHBoxLayout()
            row.addWidget(sheet_label)
            row.addWidget(sync_button)
            layout.addLayout(row)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    layout.addWidget(line)

    def on_sync_all():
        for spreadsheet_settings in import_config_json.spreadsheets:
            for sheet_settings in spreadsheet_settings.sheets:
                try_sync_deck(config, spreadsheet_settings.name, sheet_settings.name, sheet_settings.deck)

    sync_all_button = QPushButton("Sync all")
    qconnect(sync_all_button.clicked, on_sync_all)
    layout.addWidget(sync_all_button)

    widget.resize(widget.sizeHint())
    widget.adjustSize()
    widget.show()


def on_addon_delete(_manager: AddonManager, addon_name: str, *args: Any, **kwargs: Any) -> None:
    if addon_name == ADDON_NAME:
        for h in list(logging.getLogger().handlers):
            h.close()
            logging.getLogger().removeHandler(h)


def main() -> None:
    """Entry point for add-on initialization."""

    log_file: str = os.path.join(get_user_data_dir(), LOG_FILENAME)
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    log_formatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    root_logger = logging.getLogger()

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    AddonManager.deleteAddon = wrap(AddonManager.deleteAddon, on_addon_delete, "before") # type: ignore[method-assign]

    version_file: str = os.path.join(get_addon_dir(), VERSION_FILE)
    with open(version_file, 'r', encoding="utf8") as file:
        version = file.read()

    logging.info("Loaded goosheesy - Anki add-on for Google Sheets importing. Version: %s", version)

    working_directory = os.getcwd()
    logging.info("Working directory: %s", working_directory)

    settings_action = QAction("Settings for Google Sheets import", mw)
    qconnect(settings_action.triggered, goosheesy_settings)
    mw.form.menuTools.addAction(settings_action)

    execute_import_action = QAction("Import from Google Sheets", mw)
    qconnect(execute_import_action.triggered, goosheesy_import)
    mw.form.menuTools.addAction(execute_import_action)


main()
