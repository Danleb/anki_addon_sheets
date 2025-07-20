# Anki add-on for importing cards from Google Sheets

Google Sheets Syncer - goosheesy

Anki addon for importing cards from spreadsheet tables on Google Sheets.

It's best suited and tested on importing the translation pairs in form "word-translation".

## Installation

TODO

## Usage Flow

Before using the add-on, you have to configure the `credentials.json` file so that the add-on can access sheets in your Google Sheets account, and `import_config.json` file which defines mapping between Google Sheets and Anki decks.

Create `credentials.json` in [console.cloud.google.com](console.cloud.google.com).

Create `import_config.json` file which maps your Google Sheets to Anki decks:

```json
{
   "spreadsheets":[
      {
         "name":"My Japanese Vocabulary spreadsheet",
         "sheets":[
            {
               "name":"Japanese Google Sheet",
               "deck":"Japanese Anki deck"
            },
            {
               "name":"Additional sheet",
               "deck":"Additional deck"
            }
         ]
      }
   ]
}
```

Use add-on in Anki:

* Launch Anki.
* Press `Tools`->`Google Sheets import settings`.
* Select the `credentials.json` file.
* Press `Tools`->`Import from Google Sheets`.

## Development

Anki add-on development has some nuances.

To prepare the project for development:

* Clone the repo.
* In order for Anki to download the add-on from the source code of repository, create a symlink:
    * On Windows:
        ```powershell
        New-Item -Path C:\Users\MyUserName\AppData\Roaming\Anki2\addons21\gtranslate -ItemType SymbolicLink -Value C:\Users\MyUserName\source\repos\anki_addon_sheets
        ```
    * On Linux:
        ```bash
        TODO
        ```
* Install regular packages:
```shell
pip install -r requirements.txt -t ./vendor
```
* Install development packages:
```shell
pip install -r requirements_dev.txt -t ./addon_packages_dev
```

### Debugging

In `__init__.py`, set `WAIT_FOR_DEBUGGER_ATTACHED` variable to `True`.

To debug, launch Anki first. It will freeze and won't launch until you presss F5 in VSCode and attach the debugger to your add-on.

## Deployment

TODO

## Useful links

* https://addon-docs.ankiweb.net/intro.html
* https://ankiweb.net/shared/addons
* https://github.com/ankidroid/Anki-Android/wiki/Database-Structure
* Anki Python API: https://addon-docs.ankiweb.net/the-anki-module.html
* Python modules: https://addon-docs.ankiweb.net/python-modules.html

## Notes

* If your code throws an uncaught exception, it will be caught by Anki’s standard exception handler, and an error will be presented to the user (https://addon-docs.ankiweb.net/debugging.html).

## License

Licensed under the MIT license. Distribution is free, copyright notice is required.
