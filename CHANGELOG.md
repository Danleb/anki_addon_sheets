# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Fixed

### Changed

### Removed

## [0.1.2] - 2026-02-14

### Fixed

* Fix fields in manifest.json (added necessary fields as per Anki documentation, removed unused fields);
* Add handling of absence of the add-on config file - show error with explanation instead of generic Anki error message;
* Add closing of log file handle to not block the add-on uninstallation (used monkey patching and hook on add-on uninstalling event);
* Add lazy loading of Google Sheets API Python modules which mitigates the issue with .pyd libraries files blocking add-on uninstallation (because files of loaded libraries are locked and cannot be deleted);
* Replace tkinter message boxes and file dialogs with PyQt6 interfaces;
* Package Linux-specific Python modules (cryptography module for google-auth);
