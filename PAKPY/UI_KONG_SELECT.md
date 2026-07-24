# UI KONG Select: bestätigter Stand

Diese Datei dokumentiert den aktuell **im Spiel funktionierenden Diddy-Stand** des
KONG-Select-Menüs. Sie trennt bewusst zwischen:

- **binär bestätigt**: direkt aus den beiden PAK-Dateien und den enthaltenen SWF/ABC-Daten gelesen
- **im Spiel bestätigt**: vom Nutzer mit der modifizierten PAK getestet
- **noch offen**: für Dixie und Cranky noch nicht gebaut oder getestet

Die Dokumentation ist keine allgemeine Vermutung über Scaleform. Sie beschreibt den
konkreten Stand der analysierten Dateien.

## Analysierte PAK-Dateien

| Rolle | Datei | Größe | SHA-256 |
|---|---:|---:|---|
| Ausgangsstand | `UIPak(7).pak` | 72.653.504 Bytes | `f007a0aeeef648a0a188bec8ba33b88a6d37d5c0316f7c753380136e88540850` |
| funktionierender Diddy-Stand | `diddyicon.pak` | 72.653.976 Bytes | `4096947ac68da29db5eb2e8c66a4cdb3e5ad7a2a30f2744942a2f8587a14e3bb` |

Es wurden genau zwei PAK-Assets inhaltlich verändert:

| Asset | Originalgröße | Modgröße | Änderung |
|---|---:|---:|---:|
| `PauseMenu` (`GFX`) | 350.123 | 350.434 | +311 Bytes |
| `MasterShell` (`GFX`) | 432.011 | 432.172 | +161 Bytes |

Alle nachfolgenden PAK-Offsetänderungen sind eine Folge dieser Größenänderungen.

## Wichtigste Architektur-Erkenntnis

Die funktionierende Lösung besteht aus **zwei getrennten Ebenen**:

1. **`PauseMenu -> Source` und unterstützende PauseMenu-Filme**
   - Auswahlrotation
   - `P1Selection`
   - sichtbarer Charaktername
   - Behandlung beim Öffnen des Menüs

2. **`MasterShell -> MenuCharacter.swf` und `MasterShell -> Source`**
   - tatsächliche Diddy-Porträtinstanz für Spieler 1
   - Rücksetzen der Porträt-Sichtbarkeit

Deshalb dürfen Rotation und Porträt nicht als ein einziger Patch behandelt werden.

---

# 1. Funktionierende P1-Rotation mit Diddy

## Aktueller, bestätigter Zyklus

Nach rechts:

```text
DK -> FUNKY -> DIDDY -> DK
```

Nach links:

```text
DK -> DIDDY -> FUNKY -> DK
```

Dieser Stand ist im Spiel bestätigt.

## Relevanter Film

```text
PauseMenu -> Source
DoABC: erstes unbenanntes Root-Modul
Klasse: shell.MenuCharacter
```

## Relevante Konstanten

Im analysierten `PauseMenu -> Source` gelten:

| Konstante | Multiname-Index |
|---|---:|
| `k_sDK` | 915 |
| `k_sDiddy` | 916 |
| `k_sDixie` | 917 |
| `k_sCranky` | 918 |
| `k_sFunky` | 919 |

Relevante Felder:

| Feld | Multiname-Index |
|---|---:|
| `P1_Character` | 503 |
| `P2_Character` | 504 |
| `portrait_p1` | 505 |
| `portrait_p2` | 506 |
| `P1Selection` | 507 |
| `P2Selection` | 508 |

Relevante Lokalisierungsstrings:

| Text | String-Index |
|---|---:|
| `$_Character_DK` | 2104 |
| `$_Character_FK` | 2106 |
| `$_Character_Diddy` | 2111 |
| `$_Character_Dixie` | 2113 |
| `$_Character_Cranky` | 2115 |

## Methode 490: `initMenu`

Originale Codelänge:

```text
1018 Bytes
```

Modifizierte Codelänge:

```text
1074 Bytes
```

Die Methode wurde so erweitert, dass `P1Selection == k_sDiddy` kein ungültiger Wert
mehr ist.

Der angehängte Diddy-Zweig macht sinngemäß:

```actionscript
if (P1Selection == k_sDiddy)
{
    P1_Character.setToggle(
        this,
        Vial.Proxy.parse("shell", "$_P1_Title"),
        Vial.Proxy.parse("shell", "$_Character_Diddy")
    );
}
else
{
    // ursprünglicher Fehler-/Fallback-Pfad
}
```

Danach springt der Zweig wieder in den gemeinsamen Fortsetzungsbereich der Methode.

Wichtig: Dieser Diddy-Zweig setzt in `PauseMenu -> Source` **nicht ausdrücklich**
`portrait_p1.diddy.visible = true`. Der funktionierende Porträtpfad liegt, wie unten
dokumentiert, in MasterShell.

## Methode 492: `toggleRight`

Originale Codelänge:

```text
668 Bytes
```

Modifizierte Codelänge:

```text
715 Bytes
```

Die vorhandene P1-Auswahl war ursprünglich auf DK und Funky ausgelegt. Der modifizierte
Dispatcher arbeitet effektiv so:

```text
aktuell DK      -> Funky-Zweig
aktuell Funky   -> neuer Diddy-Zweig
aktuell Diddy   -> DK-Zweig
sonst           -> Fehlerpfad
```

Der neue Diddy-Zweig macht sinngemäß:

```actionscript
P1Selection = k_sDiddy;
P1_Character.setToggleText(Vial.Proxy.parse("shell", "$_Character_Diddy"));
P1_Character.toggleNext(controllerIndex);
return;
```

Die relativen Sprünge und der `lookupswitch` wurden manuell passend zur vergrößerten
Methode korrigiert. Der variable AVM2-Patcher baut Containergrößen neu auf, korrigiert
aber keine semantischen Sprungziele automatisch.

## Methode 493: `toggleLeft`

Originale Codelänge:

```text
668 Bytes
```

Modifizierte Codelänge:

```text
715 Bytes
```

Der P1-Dispatcher arbeitet effektiv so:

```text
aktuell DK      -> neuer Diddy-Zweig
aktuell Diddy   -> Funky-Zweig
aktuell Funky   -> DK-Zweig
sonst           -> Fehlerpfad
```

Der eingefügte Diddy-Block setzt ebenfalls `P1Selection = k_sDiddy`, aktualisiert den
Diddy-Text und führt die vorhandene Toggle-Animation aus.

## Binär bestätigte Methodendeltas

| Methode | Original | Modifiziert | Delta |
|---|---:|---:|---:|
| `initMenu` 490 | 1018 | 1074 | +56 |
| `toggleRight` 492 | 668 | 715 | +47 |
| `toggleLeft` 493 | 668 | 715 | +47 |

---

# 2. Weitere PauseMenu-Patches im funktionierenden Stand

## `PauseMenu -> MenuCharacter.swf`

Das eingebettete `MenuCharacter.swf` enthält ein eigenes AVM2-Modul mit
`shell.MenuCharacter.initMenu`, Methode 241.

Die funktionierende PAK verändert dort:

```text
Methode 241, Offset 0x0000:
D0 -> 47
```

Damit beginnt die Methode mit `returnvoid` und beendet sich sofort.

Zusätzlich wurde in derselben Methode bei Offset `0x138` ein bedingter Zweig durch
`pop/nop`-Bytes neutralisiert:

```text
12 21 00 00 -> 29 02 02 02
```

Das ist wichtig, weil der wirksame Auswahlcode des funktionierenden Stands in
`PauseMenu -> Source` liegt. Änderungen dürfen nicht blind gleichzeitig in beiden
Klassenkopien eingebaut werden.

## `PauseMenu -> Options.swf`

Die funktionierende PAK enthält außerdem drei gleichlange AVM2-Patches:

| Klasse / Methode | Methodenindex | Offset | Original | Neu |
|---|---:|---:|---|---|
| `shell.Options.stateManager` | 264 | `0x42A` | `14 09 00 00` | `29 29 02 02` |
| `shell.Options_main.initMenu` | 411 | `0x145` | `D3` | `26` |
| `shell.Options_main.inputSelect` | 419 | `0x165` | `12 18 00 00` | `29 02 02 02` |

Diese Patches sind im funktionierenden PAK vorhanden. Ihre genaue Verantwortung für
den gesamten Menüfluss ist noch nicht vollständig isoliert. Sie dürfen daher nicht
als reine Porträtpatches bezeichnet oder ohne Prüfung entfernt werden.

---

# 3. Funktionierendes P1-Diddy-Porträt

## Originale Sprite-Struktur

In beiden originalen `MenuCharacter.swf`-Filmen ist Sprite 12 die vorhandene
Spieler-2-Porträtgruppe:

| Instanz | Character-ID | Tiefe | Matrix |
|---|---:|---:|---|
| `cranky` | 9 | 1 | `00` |
| `dixie` | 10 | 3 | `00` |
| `diddy` | 11 | 5 | `00` |

Sprite 15 ist die originale Spieler-1-Porträtgruppe:

| Instanz | Character-ID | Tiefe | Matrix |
|---|---:|---:|---|
| `dk` | 13 | 1 | `10 A0 00` |
| `fk` | 14 | 3 | `00` |

Damit ist binär bestätigt:

- Diddy-Grafik: Character-ID `11`
- Dixie-Grafik: Character-ID `10`
- Cranky-Grafik: Character-ID `9`
- Spieler-1-Zielgruppe: Sprite `15`
- vorhandene DK-Position für Spieler 1: Matrix `10 A0 00`

## Tatsächliche Änderung in der funktionierenden PAK

Der neue P1-Diddy-Eintrag befindet sich in:

```text
MasterShell -> MenuCharacter.swf -> Sprite 15
```

Eingefügte Instanz:

| Eigenschaft | Wert |
|---|---|
| Name | `diddy` |
| Character-ID | `11` |
| Tiefe | `5` |
| Matrix | `10 A0 00` |
| Tag | `PlaceObject2` |

Roher Payload:

```text
26 05 00 0B 00 10 A0 00 64 69 64 64 79 00
```

Das ist die Spieler-2-Diddy-Grafik aus Sprite 12, aber an der Spieler-1-DK-Position.

## Entscheidende Korrektur zu früheren Annahmen

Im funktionierenden `diddyicon.pak` wurde **keine Diddy-Instanz in**

```text
PauseMenu -> MenuCharacter.swf -> Sprite 15
```

gefunden.

Dort enthält der erste Frame weiterhin nur:

```text
dk@Tiefe 1
fk@Tiefe 3
```

Der funktionierende Stand beweist daher nicht, dass dieselbe Timeline-Instanz zusätzlich
in PauseMenu eingesetzt werden muss. Die bestätigte P1-Diddy-Instanz liegt in
MasterShell.

## `MasterShell -> Source`: Methode 359 `resetPortraitP1`

Originale Codelänge:

```text
25 Bytes
```

Modifizierte Codelänge:

```text
36 Bytes
```

Die Methode setzt nun alle drei vorhandenen P1-Porträts unsichtbar:

```actionscript
portrait_p1.dk.visible = false;
portrait_p1.fk.visible = false;
portrait_p1.diddy.visible = false;
```

Disassembly des funktionierenden Stands:

```text
0000: getlocal_0
0001: pushscope
0002: getlocal_0
0003: getproperty portrait_p1
0006: getproperty dk
0009: pushfalse
000A: setproperty visible
000D: getlocal_0
000E: getproperty portrait_p1
0011: getproperty fk
0014: pushfalse
0015: setproperty visible
0018: getlocal_0
0019: getproperty portrait_p1
001C: getproperty diddy
001F: pushfalse
0020: setproperty visible
0023: returnvoid
```

## Auffälliger Unterschied zwischen PauseMenu und MasterShell

`PauseMenu -> Source` enthält ebenfalls `resetPortraitP1`, dort Methode 500. Im
funktionierenden PAK blieb sie jedoch unverändert und blendet nur DK und Funky aus:

```actionscript
portrait_p1.dk.visible = false;
portrait_p1.fk.visible = false;
```

Diddy wird in dieser PauseMenu-Methode nicht erwähnt.

Das ist kein theoretischer Vorschlag, sondern der binär bestätigte Zustand der
funktionierenden PAK. Deshalb darf die MasterShell-Logik nicht automatisch auf
PauseMenu übertragen werden, ohne einen eigenen Test zu machen.

---

# 4. Bestätigungsstatus

## Im Spiel bestätigt

- P1 kann zwischen DK, Funky und Diddy rotieren.
- Rechtsrotation: `DK -> Funky -> Diddy -> DK`.
- Linksrotation läuft rückwärts.
- Diddy-Text wird angezeigt.
- Das Diddy-Porträt für Spieler 1 funktioniert im bereitgestellten PAK-Stand.

## Binär bestätigt

- Diddy ist `k_sDiddy`, Multiname 916.
- Diddy-Text ist `$_Character_Diddy`, String 2111.
- Diddy-Porträt ist Character-ID 11.
- P1-Porträtgruppe ist Sprite 15.
- Die neue P1-Diddy-Instanz liegt in MasterShell Sprite 15.
- MasterShell `resetPortraitP1` setzt Diddy auf unsichtbar.
- PauseMenu `Source` enthält die erweiterte Auswahlrotation.
- PauseMenu `MenuCharacter.swf` enthält keine neue P1-Diddy-Instanz im ersten Frame.

## Noch nicht bestätigt

- P1-Dixie-Rotation.
- P1-Cranky-Rotation.
- P1-Dixie-Porträt.
- P1-Cranky-Porträt.
- zweimal derselbe Kong in allen P1/P2-Kombinationen.
- vollständiges Verhalten in allen Frontend-, Map-, Demo- und Funky-Mode-Pfaden.

---

# 5. Nächster Ausbau: Dixie und Cranky

Das gewünschte Endergebnis für Rechtsrotation ist:

```text
DK -> FUNKY -> DIDDY -> DIXIE -> CRANKY -> DK
```

Links muss exakt die Gegenrichtung bilden:

```text
DK -> CRANKY -> DIXIE -> DIDDY -> FUNKY -> DK
```

## Source-Arbeit separat behandeln

Für die Rotation müssen in `PauseMenu -> Source` getrennt geprüft und erweitert werden:

1. `initMenu` Methode 490
   - Dixie als gültigen P1-Wert erkennen
   - Cranky als gültigen P1-Wert erkennen
   - korrekten lokalisierten Text setzen

2. `toggleRight` Methode 492
   - Funky -> Diddy bleibt erhalten
   - Diddy -> Dixie ergänzen
   - Dixie -> Cranky ergänzen
   - Cranky -> DK ergänzen

3. `toggleLeft` Methode 493
   - DK -> Cranky ergänzen
   - Cranky -> Dixie ergänzen
   - Dixie -> Diddy ergänzen
   - Diddy -> Funky bleibt erhalten

Dabei müssen `lookupswitch`, relative Sprünge und alle Rücksprünge anhand des finalen
Methodenlayouts neu berechnet werden. Die aktuellen Diddy-Offets sind nicht automatisch
stabile Offsets für einen erneut vergrößerten Methodenbody.

## Menü-/Icon-Arbeit separat behandeln

Binär bekannte Quellen:

```text
Dixie  = Sprite 12 / Character-ID 10 / Instanzname dixie
Cranky = Sprite 12 / Character-ID 9  / Instanzname cranky
```

Bestätigtes Ziel:

```text
MasterShell -> MenuCharacter.swf -> Sprite 15
```

Für beide neuen Instanzen gilt:

- eigener Name (`dixie`, `cranky`)
- freie, eindeutige Tiefe in Sprite 15
- P1-Position muss anhand eines bestätigten P1-Ankers gesetzt werden
- anschließend MasterShell `resetPortraitP1` um beide Namen erweitern
- sichtbare Aktivierung im Spiel einzeln testen

Die konkreten Zieltiefen für Dixie und Cranky sind noch nicht im Spiel bestätigt und
werden deshalb hier nicht als feststehende Werte behauptet.

---

# 6. Regeln für weitere Patches

1. **Source und Timeline getrennt bearbeiten.**
2. **Immer vom zuletzt funktionierenden PAK-Stand ausgehen.**
3. **Originalbytes vor jedem AVM2-Patch exakt validieren.**
4. **Bei variabler Länge alle relativen Sprünge manuell korrigieren.**
5. **Offsets beziehen sich auf den unveränderten Methodenbody des jeweiligen
   Patchprofils.**
6. **Vorschau-Bestätigung und Spiel-Bestätigung getrennt dokumentieren.**
7. **Nicht annehmen, dass PauseMenu und MasterShell identische Kopien derselben Logik
   verwenden.**
8. **Keine Dixie-/Cranky-Tiefe oder Sichtbarkeitslogik als bestätigt markieren, bevor
   die gebaute PAK im Spiel getestet wurde.**
