#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import bibtexparser
import yaml
from pylatexenc.latex2text import LatexNodes2Text


def latex_to_text(s: str) -> str:
    """Convert LaTeX/BibTeX accents and markup to plain Unicode text safely."""
    if not s:
        return ""

    # 1) Primero: convertir LaTeX -> Unicode (NO borrar llaves antes)
    s = LatexNodes2Text().latex_to_text(s)

    # 2) Luego: limpiar llaves residuales típicas de BibTeX (capitalización)
    s = s.replace("{", "").replace("}", "")

    # 3) Normalizar espacios
    s = re.sub(r"\s+", " ", s).strip()
    return s



def pick(entry: Dict[str, str], *keys: str) -> str:
    for k in keys:
        if k in entry and entry[k].strip():
            return entry[k].strip()
    return ""


def normalize_pages(pages: str) -> str:
    if not pages:
        return ""
    return pages.replace("--", "–").strip()


def normalize_authors(authors: str) -> str:
    if not authors:
        return ""
    # Keep as provided but make "and others" nicer.
    authors = authors.replace(" and others", "; et al.")
    authors = authors.replace(" and ", "; ")
    return latex_to_text(authors)


def build_item(entry: Dict[str, str]) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    item["id"] = entry.get("ID", "").strip()

    etype = entry.get("ENTRYTYPE", "").strip().lower()
    item["type"] = etype

    year = pick(entry, "year")
    item["year"] = int(year) if year.isdigit() else year

    item["authors"] = normalize_authors(pick(entry, "author"))
    item["title"] = latex_to_text(pick(entry, "title"))

    # Venues depending on type
    if etype == "article":
        item["venue"] = latex_to_text(pick(entry, "journal"))
        item["volume"] = latex_to_text(pick(entry, "volume"))
        item["issue"] = latex_to_text(pick(entry, "number", "issue"))
        item["pages"] = normalize_pages(latex_to_text(pick(entry, "pages")))
    elif etype in ("incollection", "inproceedings"):
        item["venue"] = latex_to_text(pick(entry, "booktitle"))
        item["editor"] = latex_to_text(pick(entry, "editor", "editors"))
        item["pages"] = normalize_pages(latex_to_text(pick(entry, "pages")))
        item["publisher"] = latex_to_text(pick(entry, "publisher"))
    elif etype in ("mastersthesis", "phdthesis", "thesis"):
        item["degree"] = latex_to_text(pick(entry, "type"))
        item["institution"] = latex_to_text(pick(entry, "school", "institution"))
    else:
        # misc, dataset, software, etc.
        item["venue"] = latex_to_text(pick(entry, "journal", "howpublished"))

    doi = latex_to_text(pick(entry, "doi"))
    url = latex_to_text(pick(entry, "url"))

    if doi:
        item["doi"] = doi
        # If no url, synthesize DOI URL
        if not url:
            url = f"https://doi.org/{doi}"

    if url:
        item["url"] = url

    # Optional tags (you can add later manually)
    item["tags"] = []

    # Drop empty keys (clean YAML)
    item = {k: v for k, v in item.items() if v not in ("", [], None)}
    return item


def group_sections(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sections = {
        "journal_articles": {"id": "journal_articles", "title": "Journal articles", "items": []},
        "book_chapters": {"id": "book_chapters", "title": "Book chapters", "items": []},
        "theses": {"id": "theses", "title": "Theses", "items": []},
        "datasets_tools": {"id": "datasets_tools", "title": "Datasets & tools", "items": []},
        "other": {"id": "other", "title": "Other", "items": []},
    }

    for it in items:
        t = it.get("type", "")
        if t == "article":
            sections["journal_articles"]["items"].append(it)
        elif t in ("incollection", "inproceedings"):
            sections["book_chapters"]["items"].append(it)
        elif t in ("mastersthesis", "phdthesis", "thesis"):
            sections["theses"]["items"].append(it)
        elif t == "misc":
            # Heuristic: if URL contains huggingface/zenodo/doi or title looks like a tool/dataset
            title = (it.get("title") or "").lower()
            url = (it.get("url") or "").lower()
            if any(x in url for x in ["huggingface.co", "zenodo", "doi.org"]) or any(
                x in title for x in ["corpus", "dataset", "builder", "tool"]
            ):
                sections["datasets_tools"]["items"].append(it)
            else:
                sections["other"]["items"].append(it)
        else:
            sections["other"]["items"].append(it)

    # Sort items by year desc (safe even if year is string)
    def year_key(x: Dict[str, Any]) -> int:
        y = x.get("year", 0)
        return int(y) if isinstance(y, int) or (isinstance(y, str) and y.isdigit()) else 0

    for sec in sections.values():
        sec["items"] = sorted(sec["items"], key=year_key, reverse=True)

    # Return only non-empty sections in a stable order
    order = ["journal_articles", "book_chapters", "theses", "datasets_tools", "other"]
    return [sections[k] for k in order if sections[k]["items"]]


def main() -> None:
    bib_path = Path("static/files/publications.bib")
    out_path = Path("data/research.yaml")

    if not bib_path.exists():
        raise SystemExit(f"BibTeX not found: {bib_path}")

    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    db = bibtexparser.load(bib_path.open(encoding="utf-8"), parser=parser)

    items = [build_item(e) for e in db.entries]
    sections = group_sections(items)

    out = {"sections": sections}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=120)

    print(f"✅ Wrote {out_path} ({sum(len(s['items']) for s in sections)} entries)")


if __name__ == "__main__":
    main()
