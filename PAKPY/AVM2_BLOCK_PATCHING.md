# AVM2-Byteblöcke einfügen, ersetzen und entfernen

Der AVM2-Patcher unterstützt weiterhin sichere, gleich lange Byte-Ersetzungen. Zusätzlich
kann ein neuer Byteblock länger oder kürzer als der geprüfte Originalblock sein.

## Oberfläche

1. Im AVM2-Inventar eine Methode auswählen.
2. **Bytepatch hinzufügen…** öffnen.
3. Den Offset innerhalb des Methodencodes eintragen.
4. Links die **erwarteten Originalbytes** eintragen.
5. Rechts den vollständigen **neuen Byteblock** eintragen.
6. Die angezeigte Byteanzahl und Größenänderung prüfen.
7. Den Patch validieren und bestätigen.

Beide Bytefelder sind mehrzeilig. Leerzeichen, Zeilenumbrüche, Kommas und kompakte
Hexfolgen werden akzeptiert.

## Sicherheitsanker

Eine erwartete Originalfolge ist immer erforderlich. Dadurch wird nicht blind an einen
Offset geschrieben. Der Patch wird nur angewendet, wenn die Originalbytes exakt passen.

### Gleich lang ersetzen

```text
Erwartet:  12 18 00 00
Neu:       29 02 02 02
Änderung:  0 Bytes
```

Hier ist keine zusätzliche Größenbestätigung nötig.

### Bytes vor einem vorhandenen Anker einfügen

```text
Erwartet:  D0
Neu:       02 02 D0
Änderung:  +2 Bytes
```

`D0` bleibt erhalten; davor werden zwei Bytes eingefügt.

### Bytes nach einem vorhandenen Anker einfügen

```text
Erwartet:  D0
Neu:       D0 02 02
Änderung:  +2 Bytes
```

### Bytes entfernen

```text
Erwartet:  02 02 D0
Neu:       D0
Änderung:  -2 Bytes
```

## Bestätigung bei Größenänderungen

Bei jeder Abweichung zwischen alter und neuer Byteanzahl erscheint eine Warnung mit:

- Anzahl der erwarteten Bytes
- Anzahl der neuen Bytes
- exakter Größenänderung
- Hinweis, dass es keine gleich lange Ersetzung ist

Bei mehr als einem eingefügten oder entfernten Byte muss zusätzlich exakt eingegeben
werden:

```text
EINFÜGEN 3
```

oder:

```text
LÖSCHEN 3
```

Damit fällt ein versehentlich unterschiedlich langer Block vor dem Schreiben auf.

## Was automatisch neu aufgebaut wird

Der Patcher aktualisiert:

- das U30-Codegrößenfeld des AVM2-Methodenbodys
- den Inhalt und die Größe des DoABC-Tags
- Größen übergeordneter `DefineSprite`-Tags
- die SWF/GFX-Dateilänge
- CWS-Komprimierung
- die Größe des Films im GFX-Container
- die Größe des GFX-Assets beim PAK-Neubau

Mehrere Patches innerhalb derselben Methode verwenden weiterhin die Offsets des
unveränderten Originalcodes. Dadurch verschiebt ein früher Patch nicht die Position
eines später definierten Patches.

## Was nicht automatisch korrigiert wird

Bei einer Größenänderung werden semantische AVM2-Ziele nicht neu berechnet:

- relative Sprungweiten
- `lookupswitch`-Ziele
- Exception-Bereiche und Exception-Ziele
- selbst berechnete Offsets in eingebetteten Daten

Diese Werte müssen im neuen Byteblock bereits korrekt sein oder mit weiteren Patches
angepasst werden. Die Oberfläche weist vor jeder Größenänderung ausdrücklich darauf hin.

## Patchprofile

Das vorhandene JSON-Format bleibt kompatibel:

```json
{
  "schema": 1,
  "patches": [
    {
      "module_name": "<unbenannt>",
      "source": "root",
      "method_index": 492,
      "code_offset": 104,
      "expected": "D0",
      "replacement": "02 02 D0",
      "note": "Zwei NOPs vor dem Anker einfügen"
    }
  ]
}
```

`expected` und `replacement` dürfen nun unterschiedlich lang sein. Beim Anwenden wird
weiterhin jede erwartete Originalfolge geprüft. Der Ergebnisbericht enthält zusätzlich:

- `byte_delta`
- `old_method_code_size`
- `new_method_code_size`
- einen Hinweis zu nicht automatisch angepassten Sprung- und Exception-Offsets

## Tests

Die Tests decken ab:

- unveränderte gleich lange Patches
- mehrbyteige Einfügungen
- Löschungen
- mehrere Original-Offsets in einer Methode
- U30-Größenwechsel über 127 Bytes
- DoABC innerhalb eines `DefineSprite`
- CWS-Komprimierung
- überlappende Patchbereiche
