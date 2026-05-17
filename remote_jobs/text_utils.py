from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup


def html_to_plain_text(raw_html: str) -> str:
    if not raw_html:
        return ""

    soup = BeautifulSoup(html.unescape(raw_html), "html.parser")

    for br in soup.find_all("br"):
        br.replace_with("\n")

    for li in soup.find_all("li"):
        line = li.get_text(" ", strip=True)
        li.replace_with(f"\n• {line}" if line else "\n")

    for tag in soup.find_all(["p", "strong", "b"]):
        text_inside = tag.get_text(" ", strip=True)
        if text_inside and text_inside.endswith(":") and len(text_inside) < 72:
            tag.replace_with(f"\n\n{text_inside}\n")
        elif tag.name in ("strong", "b") and text_inside and len(text_inside) < 56:
            tag.replace_with(f"\n\n{text_inside}:\n")

    for paragraph in soup.find_all("p"):
        paragraph.insert_after("\n")

    text = soup.get_text("\n")
    return normalize_description_text(text)


def normalize_description_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n•\s*\n+", "\n• ", text)
    text = re.sub(r"(?m)^\s*•\s*$", "", text)

    lines = [line.strip() for line in text.split("\n")]
    lines = _merge_broken_lines(lines)

    text = "\n".join(lines)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"•[ \t]{2,}", "• ", text)
    text = re.sub(r"(?m)^\s*[-–—]\s+", "• ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _merge_broken_lines(lines: list[str]) -> list[str]:
    """Склеивает обрывки вроде «В» + «ам:» или «Приветствуется» + «:»."""
    merged: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue

        if line == ":" and merged:
            merged[-1] += ":"
            i += 1
            continue

        if (
            i + 1 < len(lines)
            and lines[i + 1]
            and not line.startswith("•")
            and not lines[i + 1].startswith("•")
            and (
                lines[i + 1] == ":"
                or (
                    len(line) <= 3
                    and len(lines[i + 1]) < 48
                    and not re.match(r"^[A-ZА-ЯЁ]", lines[i + 1])
                )
            )
        ):
            merged.append(line + lines[i + 1].lstrip())
            i += 2
            continue

        merged.append(line)
        i += 1

    return merged


def normalize_whitespace(text: str) -> str:
    return normalize_description_text(text)
