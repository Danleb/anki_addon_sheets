# Anki addon for importing "Saved Translations" Google sheet

Anki addon for importing cards from "Saved Translations" table on Google Sheets which is export of the Google Translate "Saved" list.

## Installation

## Usage Flow

1. Go to Google Translate, open `Saved` panel, click `Export to Google Sheets` button.
1. Open `Tools`->`Import Google Saved Translations`.
2. Select deck to import to.
3. Finish.

## Development

Create symlink:
```powershell
 New-Item -Path C:\Users\Dan\AppData\Roaming\Anki2\addons21\gtranslate -ItemType SymbolicLink -Value C:\Users\Dan\source\repos\anki_addon_sheets
```

## Deployment

## Useful links

* https://addon-docs.ankiweb.net/intro.html
* https://ankiweb.net/shared/addons
* 

## License

Licensed under the MIT license. Distribution is free, copyright notice is required.
