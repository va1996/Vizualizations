#!/usr/bin/env python3
"""
Google Scholar Article Summarizer
=================================
Taegliches Tool zum Abrufen und Zusammenfassen relevanter
wissenschaftlicher Artikel von Google Scholar.

Nutzung:
    python scholar_summarizer.py
    python scholar_summarizer.py --config config.yaml
    python scholar_summarizer.py --query "remineralization enamel"
"""

import argparse
import hashlib
import json
import logging
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml
from scholarly import scholarly, ProxyGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Endnote/RIS Parser ──────────────────────────────────────────────

def parse_ris_file(filepath: str) -> list[dict]:
    """Parse eine RIS-Datei (.ris) und gib eine Liste von Artikeln zurueck."""
    articles = []
    current = {}
    tag_map = {
        "TI": "title",
        "T1": "title",
        "AU": "authors",
        "A1": "authors",
        "AB": "abstract",
        "N2": "abstract",
        "PY": "year",
        "Y1": "year",
        "JO": "journal",
        "JF": "journal",
        "DO": "doi",
        "UR": "url",
        "KW": "keywords",
    }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            match = re.match(r"^([A-Z][A-Z0-9])\s{2}-\s(.*)$", line)
            if match:
                tag, value = match.group(1), match.group(2).strip()
                if tag == "ER":
                    if current:
                        articles.append(current)
                    current = {}
                elif tag == "TY":
                    current["type"] = value
                elif tag in tag_map:
                    field = tag_map[tag]
                    if field == "authors":
                        current.setdefault("authors", []).append(value)
                    elif field == "keywords":
                        current.setdefault("keywords", []).append(value)
                    else:
                        current[field] = value

    if current:
        articles.append(current)

    return articles


def parse_endnote_xml(filepath: str) -> list[dict]:
    """Parse eine Endnote XML-Datei und gib eine Liste von Artikeln zurueck."""
    import xml.etree.ElementTree as ET

    articles = []
    tree = ET.parse(filepath)
    root = tree.getroot()

    for record in root.iter("record"):
        article = {}

        title_el = record.find(".//title")
        if title_el is not None and title_el.text:
            article["title"] = title_el.text.strip()

        authors_el = record.findall(".//author")
        if authors_el:
            article["authors"] = [a.text.strip() for a in authors_el if a.text]

        abstract_el = record.find(".//abstract")
        if abstract_el is not None and abstract_el.text:
            article["abstract"] = abstract_el.text.strip()

        year_el = record.find(".//year")
        if year_el is not None and year_el.text:
            article["year"] = year_el.text.strip()

        journal_el = record.find(".//secondary-title")
        if journal_el is not None and journal_el.text:
            article["journal"] = journal_el.text.strip()

        doi_el = record.find(".//electronic-resource-num")
        if doi_el is not None and doi_el.text:
            article["doi"] = doi_el.text.strip()

        keywords_el = record.findall(".//keyword")
        if keywords_el:
            article["keywords"] = [k.text.strip() for k in keywords_el if k.text]

        if article.get("title"):
            articles.append(article)

    return articles


# ── Google Scholar Suche ─────────────────────────────────────────────

def search_scholar(query: str, max_results: int = 10, year_from: int | None = None) -> list[dict]:
    """Suche Google Scholar nach Artikeln."""
    results = []
    try:
        search_query = scholarly.search_pubs(query, year_low=year_from)
        for i, result in enumerate(search_query):
            if i >= max_results:
                break
            bib = result.get("bib", {})
            article = {
                "title": bib.get("title", "Unbekannt"),
                "authors": bib.get("author", []),
                "abstract": bib.get("abstract", ""),
                "year": bib.get("pub_year", ""),
                "journal": bib.get("venue", ""),
                "url": result.get("pub_url", ""),
                "citations": result.get("num_citations", 0),
                "source": "google_scholar",
                "query": query,
            }
            results.append(article)
            logger.info(f"  Gefunden: {article['title'][:80]}...")
    except Exception as e:
        logger.warning(f"Fehler bei Scholar-Suche '{query}': {e}")

    return results


# ── Deduplizierung ───────────────────────────────────────────────────

def deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Entferne doppelte Artikel basierend auf Titel-Aehnlichkeit."""
    seen = {}
    unique = []

    for article in articles:
        title = article.get("title", "").lower().strip()
        title_normalized = re.sub(r"[^a-z0-9]", "", title)
        title_hash = hashlib.md5(title_normalized.encode()).hexdigest()

        if title_hash not in seen:
            seen[title_hash] = True
            unique.append(article)

    logger.info(f"Deduplizierung: {len(articles)} -> {len(unique)} Artikel")
    return unique


# ── Relevanz-Scoring ─────────────────────────────────────────────────

def score_relevance(article: dict, keywords: list[str]) -> float:
    """Berechne einen Relevanz-Score basierend auf Keyword-Matches."""
    text = " ".join([
        article.get("title", ""),
        article.get("abstract", ""),
        " ".join(article.get("keywords", [])),
    ]).lower()

    score = 0.0
    matched = []
    for kw in keywords:
        kw_lower = kw.lower()
        count = text.count(kw_lower)
        if count > 0:
            score += count
            matched.append(kw)

    # Bonus fuer Titel-Treffer
    title_lower = article.get("title", "").lower()
    for kw in keywords:
        if kw.lower() in title_lower:
            score += 3.0

    article["relevance_score"] = score
    article["matched_keywords"] = matched
    return score


# ── KI-Zusammenfassung ───────────────────────────────────────────────

def summarize_with_claude(articles: list[dict], api_key: str, model: str) -> str:
    """Erstelle eine Zusammenfassung der Artikel mit Claude."""
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic-Paket nicht installiert. Installiere mit: pip install anthropic")
        return _fallback_summary(articles)

    client = anthropic.Anthropic(api_key=api_key)

    articles_text = ""
    for i, a in enumerate(articles, 1):
        authors = a.get("authors", [])
        if isinstance(authors, list):
            authors_str = ", ".join(authors[:3])
            if len(authors) > 3:
                authors_str += " et al."
        else:
            authors_str = str(authors)

        articles_text += f"""
---
### Artikel {i}
**Titel:** {a.get('title', 'N/A')}
**Autoren:** {authors_str}
**Jahr:** {a.get('year', 'N/A')}
**Journal:** {a.get('journal', 'N/A')}
**Zitierungen:** {a.get('citations', 'N/A')}
**Relevanz-Score:** {a.get('relevance_score', 0):.1f}
**Passende Keywords:** {', '.join(a.get('matched_keywords', []))}
**Abstract:** {a.get('abstract', 'Kein Abstract verfuegbar.')[:1000]}
"""

    prompt = f"""Du bist ein wissenschaftlicher Assistent fuer Forschung im Bereich
Remineralisation (Zahnmedizin, Materialwissenschaften, Biomineralisation).

Hier sind die neuesten relevanten Artikel von Google Scholar.
Erstelle eine strukturierte, deutschsprachige Zusammenfassung mit:

1. **Ueberblick**: Kurze Zusammenfassung der wichtigsten Trends und Themen
2. **Top-Artikel**: Die 5 relevantesten Artikel mit jeweils:
   - Titel und Autoren
   - Kernaussage (2-3 Saetze)
   - Relevanz fuer Remineralisationsforschung
   - Methodischer Ansatz
3. **Neue Entwicklungen**: Besonders innovative oder ueberraschende Ergebnisse
4. **Empfehlungen**: Welche Artikel sollten unbedingt gelesen werden und warum
5. **Verbindungen**: Moegliche Verbindungen zu Bisphenol-Forschung (BPA/BPT/BPF)

Artikel:
{articles_text}
"""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Claude API Fehler: {e}")
        return _fallback_summary(articles)


def _fallback_summary(articles: list[dict]) -> str:
    """Einfache Zusammenfassung ohne KI als Fallback."""
    lines = ["# Artikel-Zusammenfassung (ohne KI)\n"]
    lines.append(f"**Datum:** {datetime.now().strftime('%d.%m.%Y')}\n")
    lines.append(f"**Anzahl Artikel:** {len(articles)}\n")

    sorted_articles = sorted(articles, key=lambda x: x.get("relevance_score", 0), reverse=True)

    for i, a in enumerate(sorted_articles, 1):
        authors = a.get("authors", [])
        if isinstance(authors, list):
            authors_str = ", ".join(authors[:3])
        else:
            authors_str = str(authors)

        lines.append(f"\n## {i}. {a.get('title', 'N/A')}")
        lines.append(f"- **Autoren:** {authors_str}")
        lines.append(f"- **Jahr:** {a.get('year', 'N/A')}")
        lines.append(f"- **Journal:** {a.get('journal', 'N/A')}")
        lines.append(f"- **Relevanz-Score:** {a.get('relevance_score', 0):.1f}")
        lines.append(f"- **Keywords:** {', '.join(a.get('matched_keywords', []))}")

        abstract = a.get("abstract", "")
        if abstract:
            lines.append(f"- **Abstract:** {abstract[:300]}...")

        url = a.get("url", "")
        if url:
            lines.append(f"- **Link:** {url}")
        lines.append("")

    return "\n".join(lines)


# ── Ausgabe ──────────────────────────────────────────────────────────

def save_output(content: str, output_dir: str, fmt: str = "markdown") -> str:
    """Speichere die Zusammenfassung als Datei."""
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")

    if fmt == "html":
        try:
            import markdown
            html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
            html_doc = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Scholar Summary - {date_str}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px;
               margin: 2em auto; padding: 0 1em; line-height: 1.6; color: #333; }}
        h1 {{ color: #1a5276; border-bottom: 2px solid #2980b9; padding-bottom: 0.3em; }}
        h2 {{ color: #2471a3; }}
        h3 {{ color: #2e86c1; }}
        .article {{ background: #f8f9fa; padding: 1em; margin: 1em 0;
                    border-left: 4px solid #2980b9; border-radius: 4px; }}
        a {{ color: #2980b9; }}
        strong {{ color: #1a5276; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
            filepath = os.path.join(output_dir, f"scholar_summary_{date_str}.html")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_doc)
        except ImportError:
            logger.warning("markdown-Paket nicht installiert, speichere als Markdown.")
            fmt = "markdown"

    if fmt == "markdown":
        filepath = os.path.join(output_dir, f"scholar_summary_{date_str}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    logger.info(f"Zusammenfassung gespeichert: {filepath}")
    return filepath


# ── E-Mail ───────────────────────────────────────────────────────────

def send_email(subject: str, body: str, config: dict):
    """Sende die Zusammenfassung per E-Mail."""
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled"):
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_cfg["sender"]
    msg["To"] = email_cfg["recipient"]
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
            server.starttls()
            server.login(email_cfg["sender"], email_cfg["password"])
            server.sendmail(email_cfg["sender"], email_cfg["recipient"], msg.as_string())
        logger.info("E-Mail erfolgreich gesendet.")
    except Exception as e:
        logger.error(f"E-Mail-Versand fehlgeschlagen: {e}")


# ── Cache ────────────────────────────────────────────────────────────

def load_cache(cache_path: str) -> dict:
    """Lade den Artikel-Cache."""
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen_titles": [], "last_run": None}


def save_cache(cache: dict, cache_path: str):
    """Speichere den Artikel-Cache."""
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def filter_new_articles(articles: list[dict], cache: dict) -> list[dict]:
    """Filtere bereits gesehene Artikel heraus."""
    seen = set(cache.get("seen_titles", []))
    new_articles = []
    for a in articles:
        title_norm = re.sub(r"[^a-z0-9]", "", a.get("title", "").lower())
        if title_norm not in seen:
            new_articles.append(a)
            seen.add(title_norm)

    cache["seen_titles"] = list(seen)[-500:]  # Behalte die letzten 500
    cache["last_run"] = datetime.now().isoformat()

    logger.info(f"Neue Artikel: {len(new_articles)} von {len(articles)}")
    return new_articles


# ── Hauptprogramm ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Google Scholar Article Summarizer - Taegliche Zusammenfassung relevanter Artikel"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Pfad zur Konfigurationsdatei (Standard: config.yaml)",
    )
    parser.add_argument(
        "--query", "-q",
        help="Einzelne Suchanfrage (ueberschreibt config)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Keine KI-Zusammenfassung erstellen",
    )
    parser.add_argument(
        "--endnote", "-e",
        help="Pfad zur Endnote-Datei (.ris oder .xml)",
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        help="Artikel der letzten N Tage (ueberschreibt config)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Ausgabeverzeichnis (ueberschreibt config)",
    )
    args = parser.parse_args()

    # Konfiguration laden
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info(f"Konfiguration geladen: {config_path}")
    else:
        logger.warning(f"Keine Konfiguration gefunden unter {config_path}, nutze Standardwerte.")
        config = {}

    # Parameter
    queries = [args.query] if args.query else config.get("search_queries", ['"remineralization"'])
    days_back = args.days or config.get("days_back", 7)
    max_results = config.get("max_results_per_query", 10)
    keywords = config.get("relevance_keywords", ["remineralization"])
    output_dir = args.output_dir or config.get("output_dir", "./output")
    output_format = config.get("output_format", "markdown")
    endnote_file = args.endnote or config.get("endnote_file")

    api_key = (
        config.get("anthropic_api_key")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    model = config.get("anthropic_model", "claude-sonnet-4-20250514")

    cache_path = os.path.join(output_dir, ".article_cache.json")
    cache = load_cache(cache_path)

    year_from = (datetime.now() - timedelta(days=days_back)).year

    # ── Scholar-Suche ──
    all_articles = []
    logger.info(f"Starte Suche mit {len(queries)} Anfragen (ab {year_from})...")

    for i, query in enumerate(queries, 1):
        logger.info(f"[{i}/{len(queries)}] Suche: {query}")
        results = search_scholar(query, max_results=max_results, year_from=year_from)
        all_articles.extend(results)

    # ── Endnote-Import ──
    if endnote_file and os.path.exists(endnote_file):
        logger.info(f"Importiere Endnote-Bibliothek: {endnote_file}")
        ext = os.path.splitext(endnote_file)[1].lower()
        if ext == ".ris":
            endnote_articles = parse_ris_file(endnote_file)
        elif ext == ".xml":
            endnote_articles = parse_endnote_xml(endnote_file)
        else:
            logger.warning(f"Unbekanntes Endnote-Format: {ext}. Unterstuetzt: .ris, .xml")
            endnote_articles = []

        for a in endnote_articles:
            a["source"] = "endnote"
        all_articles.extend(endnote_articles)
        logger.info(f"  {len(endnote_articles)} Artikel aus Endnote importiert.")
    elif endnote_file:
        logger.warning(f"Endnote-Datei nicht gefunden: {endnote_file}")

    if not all_articles:
        logger.warning("Keine Artikel gefunden. Beende.")
        sys.exit(0)

    # ── Verarbeitung ──
    all_articles = deduplicate_articles(all_articles)
    new_articles = filter_new_articles(all_articles, cache)

    if not new_articles:
        logger.info("Keine neuen Artikel seit dem letzten Durchlauf.")
        save_cache(cache, cache_path)
        sys.exit(0)

    # Relevanz berechnen
    for article in new_articles:
        score_relevance(article, keywords)

    # Nach Relevanz sortieren
    new_articles.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    # ── Zusammenfassung ──
    logger.info(f"Erstelle Zusammenfassung fuer {len(new_articles)} Artikel...")

    header = f"# Scholar-Zusammenfassung: {datetime.now().strftime('%d.%m.%Y')}\n\n"
    header += f"**Suchanfragen:** {len(queries)} | **Neue Artikel:** {len(new_articles)}\n\n"

    if not args.no_ai and api_key:
        summary = header + summarize_with_claude(new_articles, api_key, model)
    else:
        if not api_key and not args.no_ai:
            logger.info("Kein ANTHROPIC_API_KEY gesetzt. Erstelle Zusammenfassung ohne KI.")
        summary = header + _fallback_summary(new_articles)

    # ── Speichern ──
    filepath = save_output(summary, output_dir, output_format)

    # ── Cache aktualisieren ──
    save_cache(cache, cache_path)

    # ── E-Mail senden ──
    if config.get("email", {}).get("enabled"):
        date_str = datetime.now().strftime("%d.%m.%Y")
        send_email(
            subject=f"Scholar-Zusammenfassung {date_str}",
            body=summary,
            config=config,
        )

    logger.info("Fertig!")
    print(f"\nZusammenfassung gespeichert unter: {filepath}")


if __name__ == "__main__":
    main()
