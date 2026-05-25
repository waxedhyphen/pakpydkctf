# Windows-Start

Dieses Paket ist jetzt fuer Windows vorbereitet.

## Starten

- Haupttool: `start_pakpy_windows.bat`
- Model-Konverter: `start_cmdl_converter_windows.bat`
- Ryujinx-Mods von macOS-Metadaten reinigen: `clean_ryujinx_mod_metadata_windows.bat`

Ryujinx unter Windows kann `.DS_Store` und `._*` Dateien aus macOS im `romfs` als echte Mod-Dateien einlesen. Wenn im Log mehr Dateien ersetzt werden als erwartet, diesen Cleaner ausfuehren.

## Abhaengigkeiten

Einmal ausfuehren:

```bat
install_windows_deps.bat
```

`Pillow` ist fuer PNG-Vorschau und PNG-Export noetig. `texture2ddecoder`, `py-tegra-swizzle` und `astc-encoder-py` sind fuer Switch-Texturen und ASTC-Rueckbau relevant.

Falls ASTC per Python-Paket nicht klappt, lege `astcenc.exe` in einen dieser Ordner:

- `PAKPY\tools`
- `PAKPY\tools\windows`
- `PAKPY\tools\win64`
- `tools`
- `tools\windows`
- `tools\win64`

Alternativ kann `ASTCENC` auf die EXE oder auf den Ordner zeigen.
