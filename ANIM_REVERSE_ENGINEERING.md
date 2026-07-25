# DKCTF-ANIM: belastbare Reverse-Engineering-Ergebnisse

Stand: 2026-07-18

## Ergebnisstatus

**Die vollständige Skelettanimation ist mit dem vorhandenen Repository noch nicht dekodiert.**

Das ist keine vorsichtige Formulierung, sondern das Ergebnis einer Gegenprüfung an allen
beigefügten Dateien:

- 942 `.anim`-Dateien
- 312 unterschiedliche Binärdateien nach SHA-256
- 28 `.skel`-Dateien
- mehrere Rigs mit 2 bis 78 Skin-Bones
- Bindpose-, Mirror-, Additive-, Kamera- und Mehrquellen-Clips

Der bisherige Blender-Importer ist kein Formatdecoder. Er liest ausgewählte Bytebereiche
als `s16`, skaliert sie testweise oder speichert sie als Custom Properties und ordnet
Spuren über Reihenfolge beziehungsweise Namenspräfixe zu. Diese Ausgabe ist nicht
geeignet, um die Originalanimation zu rekonstruieren.

Die neuen Dateien in diesem Verzeichnis ersetzen diese Annahmen nicht durch neue
Annahmen. Der Parser akzeptiert ausschließlich Felder, die über den gesamten Corpus
konsistent belegt sind. Der komprimierte Skelett-Payload wird bewusst noch nicht als
Animation ausgegeben.

## Vollständig verifizierter äußerer Aufbau

Alle 312 unterschiedlichen Dateien erfüllen dieselben Invarianten:

| Offset | Typ | Bedeutung |
|---:|---|---|
| `0x00` | FourCC | `RFRM` |
| `0x04` | BE `u64` | Dateigröße minus `0x20` |
| `0x0C` | BE `u64` | `0` |
| `0x14` | FourCC | `ANIM` |
| `0x18` | BE `u32` | Form-Version `20` |
| `0x1C` | BE `u32` | Daten-Version `20` |
| `0x20` | BE `u32` | `0x49170014` |
| `0x24` | BE `u32` | Dateigröße minus `0x28` |
| `0x28` | BE `u32` | Control-Wert |
| `0x2C` | BE `u32` | Gruppen-/Rig-Wert |
| `0x30` | variabel | Familienabhängiger ANIM-Header |

Beobachtete Control-Familien:

| Familie | unterschiedliche Dateien |
|---:|---:|
| `0x81` | 145 |
| `0x82` | 129 |
| `0xC1` | 1 |
| `0xC2` | 37 |

Bei `0xC1` und `0xC2` liegt bei `0x30` ein zusätzliches Byte. Dadurch verschieben sich
Descriptor, Root-Transform und komprimierter Payload exakt um ein Byte:

| Familie | Descriptor | Root-Transform | Payload |
|---|---:|---:|---:|
| `0x81`, `0x82` | `0x30` | `0x37` | `0x54` |
| `0xC1`, `0xC2` | `0x31` | `0x38` | `0x55` |

## Vollständig verifizierter Descriptor

Es kommen genau drei Descriptor-Formen vor:

| Bytes | Anzahl |
|---|---:|
| `07 01 FF 01 00 00 00` | 273 |
| `15 03 FF 01 02 03 00` | 24 |
| `1C 04 FF 01 02 03 04` | 15 |

Damit ist bytegenau belegt:

- Byte 0 ist immer `7 × Byte 1`.
- Byte 2 ist immer `FF`.
- Danach stehen die IDs `1..N`.
- Restbytes sind null.

**Nicht belegt** ist bislang, was die IDs 1 bis 4 semantisch bezeichnen. Eine Benennung
als Bone-, Actor- oder Transformanzahl wäre derzeit eine Hypothese.

## Vollständig verifizierter Root-Transform

Direkt nach dem sieben Byte langen Descriptor stehen:

1. vier Big-Endian-`float32`: Quaternion in Reihenfolge `W, X, Y, Z`
2. drei Big-Endian-`float32`: Translation in Reihenfolge `X, Y, Z`
3. ein Flag-Byte
4. der komprimierte Payload

Die Quaternion ist in allen 312 unterschiedlichen Dateien normalisiert:

- kleinstes gemessenes `norm²`: `0.999999940761294`
- größtes gemessenes `norm²`: `1.000000060329313`

Die Flag-Bytes verteilen sich wie folgt:

| Flag | Anzahl |
|---:|---:|
| `0x01` | 255 |
| `0x20` | 18 |
| `0x3F` | 39 |

Die genaue Bedeutung dieses Flags ist nicht belegt.

## Belegte Payload-Eigenschaften

Der Payload ist kein Array aus festen 12-Byte-Bone-Records.

Belege:

- Dateien desselben Rigs besitzen lange identische Metadatenpräfixe, bevor sich
  Bewegungsdaten unterscheiden.
- Die ersten Payload-Bytes variieren über mindestens 27 Werte.
- Kleine statische Clips enthalten wiederkehrende, 32-Bit-ausgerichtete Records.
- Mehrere `0x60`-Payloads enthalten LSB-orientierte Bitmasks, die exakt zu
  Skeleton-Node-Bereichen passen.
- Beim Ring-Clip mit gespeichertem Wert 30 folgt nach dem Initialzustand 29-mal
  ein ausgerichteter Null-/Delta-Record `1C 00 00 00`, anschließend `1C`.
  Das belegt einen Initialzustand plus Folgezustände, aber noch nicht die
  Semantik jedes Bits des Records.

Diese Befunde passen strukturell zu Retros älteren ANIM-Codecs: kumulative,
bitgepackte Quaternion-/Translationsdeltas, LSB-first in 32-Bit-Wörtern,
Quaternion-Interpolation und ein separat rekonstruierter Quaternion-Anteil.
Sie beweisen jedoch **nicht**, dass Tropical Freeze dieselbe Descriptor- und
Quantisierungsstruktur verwendet. Tropical Freeze hat die Engine-Formate
grundlegend überarbeitet.

## Widerlegte Ansätze im bisherigen Repository

Folgende Ansätze sind nicht formatgetreu und dürfen nicht als Decoder verwendet werden:

- Startoffset über zufällig gesuchte Byte-Signaturen bestimmen
- Payload pauschal als Big-Endian-`s16 / 32767` interpretieren
- drei Rohwerte als Euler-Winkel verwenden
- Quaternionen ausschließlich anhand `comp_count == 4` annehmen
- Tracks über Bone-Reihenfolge oder Namenspräfix zuweisen
- aus erfolgreichem Byte-Roundtrip auf korrekte Semantik schließen
- den 21-Byte-Sonderfall als zwei allgemeine 8-Byte-Keyframes deklarieren

Ein Roundtrip ist nur dann semantischer Beweis, wenn ein Decoder die Daten in
Transformwerte zerlegt und ein unabhängiger Encoder exakt dieselben Bytes erzeugt.
Das bloße Herausschneiden und Wiedereinfügen derselben Bytes beweist nichts über
deren Bedeutung.

## Was für eine vollständige Blender-Wiedergabe noch fehlt

Für jeden Payload-Untertyp müssen folgende Punkte bytegenau bestimmt werden:

1. aktive Joint-/Track-Masks
2. Reihenfolge und Typ jedes Tracks
3. Initialwerte
4. Key-/Presence-Mask
5. Bitbreite jedes Delta-Kanals
6. Vorzeichenkodierung
7. Quaternion-Rekonstruktion und Quantisierung
8. Translation- und Scale-Multiplikatoren
9. Interpolation ausgelassener Frames
10. Zuordnung von Track-ID zu SKEL-Node
11. additive und Mehrquellen-Clips
12. Achsen-/Handedness-Konvertierung nach Blender
13. Root-Motion-Semantik

Ohne diese Punkte kann Blender zwar Keyframes anzeigen, aber nicht die
Originalanimation.

## Erforderlicher unabhängiger Nachweis

Der Corpus liefert viele Korrelationen, aber keine unabhängige Sollausgabe der
komprimierten Joint-Transforms. Für einen beweisbaren Abschluss wird mindestens
eine der folgenden Quellen benötigt:

- der Wii-U-Ladercode beziehungsweise ein dekompilierbarer Game-Code-Ausschnitt,
- ein instrumentierter Lauf des Spiels/Cemu, der pro Frame lokale Joint-Matrizen
  zusammen mit der verwendeten ANIM-ID ausgibt,
- ein verifizierter Referenzdecoder,
- oder mehrere ANIM-Dateien mit exakt bekannten, exportierten lokalen Joint-
  Transformen pro Frame.

Die vorhandenen DAE/GLB/Blend-Dateien enthalten Rigs beziehungsweise Bindposes,
aber keine unabhängigen Original-Actions, gegen die der Payload geprüft werden kann.

## Enthaltene Werkzeuge

### `PAKPY/dkctf_anim_format.py`

Strikter Parser für ausschließlich verifizierte Headerfelder. Er bricht bei
abweichenden Größen, Versionen, Descriptoren oder nicht normalisierten
Quaternionen ab.

### `PAKPY/dkctf_anim_audit.py`

Prüft einen kompletten Sample-Baum, dedupliziert nach SHA-256 und erzeugt:

- `summary.json`
- `files.json`
- `files.csv`

Der beigefügte Corpus läuft mit **312/312 strikt gültigen unterschiedlichen Dateien**.

### `PAKPY/blender_import_decoded_dkctf.py`

Blender-Importer für eine bereits vollständig dekodierte,
matrixbasierte Zwischenrepräsentation. Er verwendet:

- exakte Bone-Namen
- lokale 4×4-Matrizen
- Quaternion-Keyframes
- keine Präfixsuche
- keine Euler-Näherung
- keine stillen Fallbacks

Er ist die korrekte Blender-Seite der Pipeline. Der noch fehlende Teil ist der
beweisbare Raw-Payload-Decoder.
