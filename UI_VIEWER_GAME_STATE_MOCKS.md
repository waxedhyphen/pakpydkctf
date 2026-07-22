# UI Viewer – State-Profile und Game-State-Mocks

Stand: 2026-07-22

## Zweck

Die Profile und Mocks dienen dazu, typische UI-Zustände ohne laufende Spielengine zu untersuchen. Sie verändern ausschließlich die Vorschau. GFX-, GFXL-, TXTR-, MSBT- und Repacking-Daten bleiben unverändert.

Die mitgelieferten Profile sind reproduzierbare Analysevorlagen. Sie sind kein Beweis, dass exakt diese Kombination von Werten und Frames über den originalen Ingame-Code erreichbar ist.

## Bedienung

Unterhalb der Timeline- und Qualitätsleisten befindet sich `State-Profil`.

1. Einen passenden GFX-Film auswählen.
2. Ein Profil auswählen.
3. `Anwenden` drücken.
4. Mit `Mocks…` die Werte und Zuordnungen prüfen oder verändern.
5. `Mocks aus` stellt die originalen beziehungsweise manuell überschriebenen Texte wieder her.

`F8` öffnet den Mock-Editor.

## Mitgelieferte Profile

- `HUD – 1 Spieler`
- `HUD – 2 Spieler`
- `HUD – Time Attack`
- `Pause – eingefrorener Zustand`
- `Optionen – Hauptseite`
- `Frontend – Hauptmenü`
- `Shop – 99 Banana Coins`
- `Charakterwahl – 2 Spieler`

Profile setzen nur die für sie vorgesehenen Mock-Rollen. Das Options-Profil springt bei `Options.swf` zusätzlich auf den bekannten Root-Frame 20. Andere Profile verwenden passende Frame-Labels, sofern der Film solche Labels enthält. Profile pausieren standardmäßig die strukturelle Timeline, damit der Zustand untersuchbar bleibt.

## Verfügbare Mock-Werte

- Spielerzahl
- Leben
- Banana Coins
- Puzzle Pieces und optionaler Gesamtwert
- Timer in Sekunden oder als `MM:SS.xx`
- Punkte
- Levelname
- Bananen
- KONG-Buchstaben
- Fortschritt in Prozent

Der Timer wird beispielsweise aus `83.42` als `01:23.42` dargestellt.

## Automatische Textfeldzuordnung

EditText-Felder werden anhand mehrerer Quellen bewertet:

1. `variable_name` des `DefineEditText`-Feldes;
2. Instanzname;
3. eigener stabiler Inspector-Pfad;
4. semantische Namen übergeordneter MovieClips.

Dadurch können auch mehrteilige Textdarstellungen wie `text_base`, `text_stroke` und `text_dropshadow` denselben Spielwert erhalten, wenn ihr Elternpfad beispielsweise `scoreText`, `levelTitle` oder `bananaCoins` enthält.

Breite generische Felder wie `text_base` ohne semantischen Elternnamen werden nicht automatisch ersetzt. Der Mock-Editor zeigt alle im aktuellen Zustand erkannten Felder mit Rolle, Wert, Variable und vollständigem Pfad.

## Vorrangregeln

Text wird in dieser Reihenfolge gewählt:

1. manueller Text- oder HTML-Override im State Inspector;
2. aktivierter Game-State-Mock;
3. originaler `DefineEditText`-Inhalt oder Variablenplatzhalter.

Sichtbarkeits-, Filter-, Blend- und MovieClip-Frame-Overrides bleiben unabhängig von den Game-Mocks erhalten.

## Sitzungs- und Preset-Verhalten

Mock-Zustände bleiben während der Browser-Sitzung pro Film getrennt gespeichert. JSON-Presets enthalten zusätzlich:

```json
{
  "game_state": {
    "enabled": true,
    "profile": "hud_1p",
    "roles": ["players", "lives", "score"],
    "values": {
      "players": 1,
      "lives": 5,
      "score": 12500,
      "timer_seconds": 95.42
    }
  }
}
```

Ältere Presets ohne `game_state` bleiben kompatibel und laden mit deaktivierten Mocks.

## Inspector und Analyse

Der State Inspector zeigt bei einem automatisch ersetzten Textfeld zusätzlich:

```text
Game-State-Mock:
- Rolle: Punkte
- Wert: 12500
```

Im Analysefeld stehen Profil, Aktivstatus, Anzahl aktivierter Rollen und die Zahl der im letzten Renderzustand tatsächlich ersetzten Textfelder.

## Grenzen

- Keine automatische Zuordnung zu nativen Spielcallbacks.
- Keine MSBT-Sprachauswahl.
- Keine Ausführung von ActionScript-Konstruktoren oder Frame Scripts.
- Dynamisch erst durch AVM2 erzeugte Textfelder existieren noch nicht.
- Ungewöhnlich benannte Felder können im Mock-Editor als nicht zugeordnet erscheinen und müssen bis zur AVM2-Stufe manuell überschrieben werden.
