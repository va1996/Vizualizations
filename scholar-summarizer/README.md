# Google Scholar Article Summarizer

Taegliches Tool zum automatischen Abrufen und Zusammenfassen relevanter wissenschaftlicher Artikel von Google Scholar, mit optionalem Endnote-Import und KI-Zusammenfassung via Claude.

## Features

- **Google Scholar Suche** mit konfigurierbaren Suchbegriffen
- **Endnote-Import** (.ris und .xml Dateien)
- **Relevanz-Scoring** basierend auf Keyword-Matching
- **KI-Zusammenfassung** via Anthropic Claude API
- **Deduplizierung** und Caching (keine doppelten Artikel)
- **Ausgabe** als Markdown oder HTML
- **E-Mail-Benachrichtigung** (optional)

## Installation

```bash
cd scholar-summarizer
pip install -r requirements.txt
```

## Nutzung

### Einfacher Start

```bash
python scholar_summarizer.py
```

### Mit eigener Suchanfrage

```bash
python scholar_summarizer.py --query "biomimetic remineralization enamel"
```

### Mit Endnote-Bibliothek

```bash
python scholar_summarizer.py --endnote /pfad/zu/bibliothek.ris
```

### Ohne KI-Zusammenfassung

```bash
python scholar_summarizer.py --no-ai
```

### Alle Optionen

```bash
python scholar_summarizer.py \
  --config config.yaml \
  --query "remineralization" \
  --endnote bibliothek.ris \
  --days 14 \
  --output-dir ./meine_zusammenfassungen \
  --no-ai
```

## Konfiguration

Bearbeite `config.yaml` um Suchbegriffe, Relevanz-Keywords und weitere Einstellungen anzupassen.

### KI-Zusammenfassung aktivieren

Setze deinen Anthropic API-Key als Umgebungsvariable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Taegliche Ausfuehrung (Cron)

```bash
# Jeden Morgen um 7:00 Uhr ausfuehren
0 7 * * * cd /pfad/zu/scholar-summarizer && python scholar_summarizer.py >> cron.log 2>&1
```

## Endnote-Export

Um deine Endnote-Bibliothek zu nutzen:

1. Oeffne Endnote
2. Waehle die gewuenschten Referenzen
3. File -> Export -> Format: RIS oder XML
4. Speichere die Datei und trage den Pfad in `config.yaml` ein
