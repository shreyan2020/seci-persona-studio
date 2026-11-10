from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

import httpx


class ScientificPdfParsingError(RuntimeError):
    pass


def _clean_text(value: str, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[: limit - 3].rstrip() + "..." if len(text) > limit else text


def _node_text(node: ET.Element | None, limit: int = 4000) -> str:
    if node is None:
        return ""
    return _clean_text(" ".join(node.itertext()), limit=limit)


def _parse_grobid_tei(tei_xml: str) -> Dict[str, Any]:
    root = ET.fromstring(tei_xml)
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}
    title = _node_text(root.find(".//tei:titleStmt/tei:title", ns), limit=800)
    abstract = _node_text(root.find(".//tei:profileDesc/tei:abstract", ns), limit=5000)
    authors = []
    for author in root.findall(".//tei:sourceDesc//tei:author", ns)[:12]:
        name = _node_text(author, limit=180)
        if name:
            authors.append(name)
    sections = []
    for div in root.findall(".//tei:text/tei:body//tei:div", ns)[:40]:
        heading = _node_text(div.find("tei:head", ns), limit=240)
        paragraphs = [_node_text(paragraph, limit=1200) for paragraph in div.findall("tei:p", ns)[:4]]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]
        if heading or paragraphs:
            sections.append({"heading": heading, "text": "\n".join(paragraphs)[:3000]})
    references = []
    for ref in root.findall(".//tei:listBibl/tei:biblStruct", ns)[:80]:
        ref_title = _node_text(ref.find(".//tei:title", ns), limit=400)
        ref_authors = [_node_text(author, limit=120) for author in ref.findall(".//tei:author", ns)[:6]]
        ref_authors = [author for author in ref_authors if author]
        date = ref.find(".//tei:date", ns)
        year = (date.attrib.get("when") or "")[:4] if date is not None else ""
        if ref_title or ref_authors:
            references.append({"title": ref_title, "authors": ref_authors, "year": year})
    text_excerpt = "\n\n".join(
        item
        for item in [
            f"Title: {title}" if title else "",
            f"Abstract: {abstract}" if abstract else "",
            *[f"{section.get('heading')}: {section.get('text')}" for section in sections[:8]],
        ]
        if item
    )
    return {
        "parser": "grobid",
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "sections": sections,
        "references": references,
        "text_excerpt": _clean_text(text_excerpt, limit=16000),
    }


async def parse_with_grobid(pdf_path: str | Path, grobid_url: str) -> Dict[str, Any]:
    endpoint = grobid_url.rstrip("/") + "/api/processFulltextDocument"
    timeout = httpx.Timeout(180.0, connect=20.0)
    path = Path(pdf_path)
    async with httpx.AsyncClient(timeout=timeout) as client:
        with path.open("rb") as handle:
            response = await client.post(
                endpoint,
                files={"input": (path.name, handle, "application/pdf")},
                data={"consolidateHeader": "1", "consolidateCitations": "1"},
            )
    response.raise_for_status()
    return _parse_grobid_tei(response.text)


def parse_with_docling_local(pdf_path: str | Path) -> Dict[str, Any]:
    try:
        from docling.document_converter import DocumentConverter
    except Exception as exc:
        raise ScientificPdfParsingError("Docling local parser is enabled but the docling package is not installed.") from exc

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    document = getattr(result, "document", None)
    if document is None:
        raise ScientificPdfParsingError("Docling conversion did not return a document object.")
    markdown = document.export_to_markdown() if hasattr(document, "export_to_markdown") else str(document)
    return {
        "parser": "docling_local",
        "title": "",
        "abstract": "",
        "authors": [],
        "sections": [],
        "references": [],
        "text_excerpt": _clean_text(markdown, limit=16000),
    }


async def parse_with_docling_url(pdf_path: str | Path, docling_url: str) -> Dict[str, Any]:
    timeout = httpx.Timeout(180.0, connect=20.0)
    path = Path(pdf_path)
    async with httpx.AsyncClient(timeout=timeout) as client:
        with path.open("rb") as handle:
            response = await client.post(
                docling_url.rstrip("/"),
                files={"file": (path.name, handle, "application/pdf")},
            )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type:
        payload = response.json() or {}
        text = payload.get("markdown") or payload.get("text") or payload.get("content") or ""
        return {
            "parser": "docling_url",
            "title": str(payload.get("title") or ""),
            "abstract": str(payload.get("abstract") or ""),
            "authors": payload.get("authors") if isinstance(payload.get("authors"), list) else [],
            "sections": payload.get("sections") if isinstance(payload.get("sections"), list) else [],
            "references": payload.get("references") if isinstance(payload.get("references"), list) else [],
            "text_excerpt": _clean_text(str(text), limit=16000),
        }
    return {
        "parser": "docling_url",
        "title": "",
        "abstract": "",
        "authors": [],
        "sections": [],
        "references": [],
        "text_excerpt": _clean_text(response.text, limit=16000),
    }


async def parse_scientific_pdf(pdf_path: str | Path) -> Dict[str, Any]:
    configured = []
    results = []
    errors = []

    if os.getenv("DOCLING_ENABLED", "0") == "1":
        configured.append("docling_local")
        try:
            results.append(parse_with_docling_local(pdf_path))
        except Exception as exc:
            errors.append(f"docling_local: {exc}")

    grobid_url = os.getenv("GROBID_URL", "").strip()
    if grobid_url:
        configured.append("grobid")
        try:
            results.append(await parse_with_grobid(pdf_path, grobid_url))
        except Exception as exc:
            errors.append(f"grobid: {exc}")

    docling_url = os.getenv("DOCLING_URL", "").strip()
    if docling_url:
        configured.append("docling_url")
        try:
            results.append(await parse_with_docling_url(pdf_path, docling_url))
        except Exception as exc:
            errors.append(f"docling_url: {exc}")

    if not configured:
        from document_pipeline import parse_document
        document = await parse_document(pdf_path)
        configured.append("liteparse")
        sections = {}
        for passage in document['passages']:
            sections.setdefault(passage['section'], []).append(passage['text'])
        results.append({
            'parser': 'liteparse', 'title': '', 'abstract': '', 'authors': [], 'references': [],
            'sections': [{'heading': heading, 'text': '\n'.join(texts)} for heading, texts in sections.items()],
            'text_excerpt': '\n'.join(p['text'] for p in document['passages']),
        })
    if not results:
        raise ScientificPdfParsingError("Configured scientific PDF parsers all failed: " + "; ".join(errors))

    title = next((item.get("title") for item in results if item.get("title")), "")
    abstract = next((item.get("abstract") for item in results if item.get("abstract")), "")
    text_excerpt = "\n\n".join(str(item.get("text_excerpt") or "") for item in results if item.get("text_excerpt"))
    return {
        "parsers": [item["parser"] for item in results],
        "configured_parsers": configured,
        "title": title,
        "abstract": abstract,
        "authors": next((item.get("authors") for item in results if item.get("authors")), []),
        "sections": [section for item in results for section in (item.get("sections") or [])][:60],
        "references": [ref for item in results for ref in (item.get("references") or [])][:120],
        "text_excerpt": _clean_text(text_excerpt, limit=24000),
        "errors": errors,
    }
