# UI Viewer – generischer AVM2-Patcher

Stand: 2026-07-23

## Zweck

Der Patcher verbindet die vorhandene AVM2-Analyse mit einem reproduzierbaren Repack-Workflow.
Er ist nicht auf einen bestimmten Button oder Film festgelegt. Gepatcht wird ein ausgewählter
DoABC-Methodenbody über:

- Modulname und Quelle (`root` oder `sprite <ID>`),
- Methodenindex,
- Offset innerhalb des Methodencodes,
- erwartete Originalbytes,
- gleich lange Ersatzbytes.

Die erwarteten Bytes verhindern, dass ein Profil still auf eine andere Spielversion oder eine
falsche Methode angewendet wird. Überlappende Patches und längenverändernde Ersetzungen werden
abgelehnt.

## Bedienung

1. Im UI Browser den gewünschten GFX-Film öffnen.
2. `F9` drücken und im AVM2-Inventar eine Methode auswählen.
3. `Bytepatch hinzufügen…` anklicken.
4. Code-Offset, erwartete Bytes und neue Bytes eintragen.
5. In `Patchliste / Repack…` die Vorschau anwenden.
6. Entweder das gepatchte GFX-Asset speichern oder direkt ein neues PAK bauen.

Patchlisten können als JSON gespeichert und auf andere Filme oder Versionen angewendet werden.
Vor Vorschau und Export wird die gesamte Liste erneut gegen den unveränderten Originalfilm
validiert.

## Sichere Vorlagen

Der Dialog bietet drei häufige, längenneutrale Ersetzungen:

```text
pushtrue                    26
pushfalse                   27
bedingten Sprung entfernen  29 02 02 02   # pop; nop; nop; nop
```

Die Sprungvorlage ist nur für einen vier Byte langen bedingten Sprung gedacht. Der Benutzer muss
die erwarteten Originalbytes aus der Disassembly übernehmen.

## Ausgabe

### Vorschau

Die gepatchten SWF/GFX-Daten werden nur im aktuellen UI-Browser-Fenster neu geparst. Der geladene
PAK-Datensatz bleibt unverändert und kann jederzeit mit `Vorschau zurücksetzen` wiederhergestellt
werden.

### GFX speichern

Der Patcher ersetzt den ausgewählten Film im GFX-Container. Filmtabelle, Filmgrößen, relative
Offsets, GFX-Chunkgröße und RFRM-Größe werden neu geschrieben. Bestehende Zwischenräume und
unbekannte Restdaten bleiben erhalten.

### PAK neu bauen

Das neue GFX-Asset wird als `asset_bytes` an den vorhandenen `pak_core.rebuild_pak`-Pfad übergeben.
Dadurch werden ADIR-/META-/TOCC-Offsets und Größen wie bei anderen Repack-Vorgängen neu aufgebaut
und das Ergebnis erneut geparst und validiert.

## Grenzen

- Der Patcher ist bewusst kein ActionScript-Compiler oder allgemeiner ABC-Assembler.
- Nur gleich lange Bytefolgen werden ersetzt; Constant Pools, Traits und Exceptiontabellen werden
  nicht umgebaut.
- Ein logisch falscher, aber strukturell gültiger Bytepatch kann weiterhin Laufzeitfehler erzeugen.
- Ein Profil ist nur dann anwendbar, wenn Modul, Methode, Offset und Originalbytes passen.

## Beispiel: KONG Select dauerhaft freischalten

Das Beispiel bleibt ein normales Patchprofil und ist nicht im Tool hartcodiert:

```json
{
  "schema": 1,
  "patches": [
    {
      "module_name": "<unbenannt>",
      "source": "root",
      "method_index": 411,
      "code_offset": 325,
      "expected": "D3",
      "replacement": "26",
      "note": "btn3.setEnabled immer true"
    },
    {
      "module_name": "<unbenannt>",
      "source": "root",
      "method_index": 419,
      "code_offset": 357,
      "expected": "12 18 00 00",
      "replacement": "29 02 02 02",
      "note": "PlayerCount/FunkyMode-Sprung entfernen"
    }
  ]
}
```

Die Dezimalwerte `325` und `357` entsprechen `0x145` und `0x165`.
