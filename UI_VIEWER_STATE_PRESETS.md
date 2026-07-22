# UI Viewer – State-Overrides und Presets

Stand: 2026-07-22

## Zweck

State-Presets speichern manuell rekonstruierte UI-Zustände, bevor eine vollständige ActionScript-Laufzeit vorhanden ist. Sie eignen sich beispielsweise für:

- bestimmte Pause- oder Optionsseiten;
- sichtbare und ausgeblendete HUD-Gruppen;
- alternative MovieClip-Unterframes;
- Testwerte in Textfeldern;
- Vergleich mit und ohne Glow, DropShadow oder Blend Mode;
- reproduzierbare Screenshots desselben UI-Zustands.

Alle Presets verändern ausschließlich die Vorschau.

## Preset erstellen

1. Einen GFX-Film im UI Browser öffnen.
2. `State Inspector` oder `F6` öffnen.
3. Eine Instanz im Tiefenbaum auswählen.
4. Sichtbarkeit, MovieClip-Frame, Text oder Effektoptionen setzen.
5. `Override anwenden` anklicken.
6. Weitere Instanzen bearbeiten.
7. `Preset speichern` anklicken.

Der normale Root-Frame-Regler wird zusammen mit den Overrides gespeichert.

## Preset laden

1. Den passenden GFX-Film öffnen.
2. Den State Inspector öffnen.
3. `Preset laden` anklicken.
4. Die JSON-Datei auswählen.

Das Laden ersetzt die aktuell aktiven Overrides dieses Films. Der gespeicherte Root-Frame wird wiederhergestellt.

Bei einem anderen Filmnamen zeigt der Viewer eine Warnung, lädt das Preset aber trotzdem. Dadurch können Presets zwischen Varianten eines strukturell ähnlichen Films getestet werden.

## Unterstützte Overrides

### Sichtbarkeit

```json
{
  "visible": false
}
```

`true` erzwingt sichtbar, `false` erzwingt versteckt. Fehlt das Feld, wird die originale `PlaceObject3`-Sichtbarkeit verwendet.

### MovieClip-Unterframe

```json
{
  "sprite_frame": 12
}
```

Der Wert wird auf den gültigen Bereich des jeweiligen `SpriteDef` begrenzt. Der Inspector rekonstruiert anschließend die Kinder dieses Unterframes.

### Text oder HTML

```json
{
  "text": "TEST 999",
  "html": false
}
```

Für Scaleform-HTML:

```json
{
  "text": "<p align=\"center\"><font size=\"30\" color=\"#ffffff\">TEST</font></p>",
  "html": true
}
```

Die eingebettete Fontklasse, Textfeldgröße, Transformation, Filter, Masken und Blend Modes bleiben erhalten.

### Filter deaktivieren

```json
{
  "disable_filters": true
}
```

Dies entfernt die Filterliste nur für die Vorschau dieses Placements.

### Blend Mode deaktivieren

```json
{
  "disable_blend": true
}
```

Der Blend Mode wird für dieses Placement auf Normal gesetzt.

## Vollständiges Schema

```json
{
  "format": "PAKPY_UI_STATE_PRESET",
  "version": 1,
  "pak": "UIPak.pak",
  "movie": "Options.swf",
  "root_frame": 20,
  "overrides": {
    "root/5:options_control/1:btnHandheld": {
      "visible": true,
      "sprite_frame": 2
    },
    "root/1:align_Title/1:txt_title": {
      "text": "OPTIONS TEST",
      "html": false,
      "disable_filters": true
    },
    "root/8:backgroundGlow": {
      "disable_blend": true
    }
  }
}
```

## Stabile Pfade

Ein Pfad besteht aus der Display-List-Tiefe und dem Instanznamen:

```text
root/5:options_control/1:btnHandheld
```

Existiert kein Instanzname, verwendet der Inspector je nach Objekt SymbolClass, externe Klasse, Textvariable oder `depth N`.

Pfade sind innerhalb desselben GFX-Films und derselben Timeline-Struktur stabil. Sie können ungültig werden, wenn der Film selbst ersetzt oder strukturell verändert wird.

## Verhalten bei Framewechseln

Overrides werden bei jedem Renderdurchlauf anhand des stabilen Pfads neu angewendet. Ein Pfad, der im aktuellen Root- oder Unterframe nicht existiert, bleibt im Preset gespeichert, wird in diesem Frame aber nicht angewendet.

Die Analyse zeigt:

```text
State Overrides:
- Gespeicherte Pfade: 4
- In diesem Frame angewendet: 2
```

So lässt sich erkennen, ob ein Preset nur teilweise zum aktuell gewählten Frame passt.

## Sitzungsverwaltung

Während der UI Browser geöffnet bleibt, werden Override-Sätze pro Film getrennt gehalten. Beim Wechsel zurück zu einem zuvor bearbeiteten Film erscheint dessen Zustand wieder.

Ein Neustart lädt diese Zustände nicht automatisch. Für dauerhafte Speicherung muss ein Preset als JSON gespeichert werden.

## Grenzen

- Keine automatische MovieClip-Wiedergabe.
- Keine ActionScript-Konstruktoren oder Frame Scripts.
- Keine dynamisch erzeugten DisplayObjects.
- Keine automatische MSBT- oder Game-State-Zuordnung.
- Keine Garantie, dass ein manuell rekonstruierter Zustand tatsächlich über den normalen Ingame-Code erreichbar ist.

## Nächster Schritt

Die nächste Phase ergänzt einen laufenden Framezustand pro MovieClip-Instanzpfad, Play/Pause, Looping, Label-Sprünge und eine speicherbare Wiedergabegeschwindigkeit. Danach können vordefinierte Profile und Game-State-Mocks auf denselben Preset-Pfaden aufbauen.
