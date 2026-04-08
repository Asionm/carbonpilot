# -*- coding: utf-8 -*- 
"""
Page-by-page state machine parsing (enhanced version, following the logic of "sub-items should be retained but not included in (1) for further sub-item naming"):
- Only keep pages 13..760
- Remove page headers "Instructions/Engineering Quantity Calculation Rules"
- Remove pages without "Work Content/Measurement Unit" and with more than 50 characters
- Parse hierarchy: Engineering Category -> Engineering Subcategory -> Sub-item -> (Further Subdivision under Sub-item) -> Work Content -> Quota Item
- When there is no sub-item, use the engineering subcategory name as fallback for sub-item
- "(1)/(（1）)" are only used as anchor points for identification; they are not combined into "Sub-item (Further Subdivision)" names, work content belongs to sub-item
- "Work Content: Same as previous..." is merged into the previous work content (page numbers and quota content are merged)
- When collecting items, any "title-like" lines (Chapter/Subcategory/Sub-item/Further Subdivision/Work Content anchor points) will not be mistakenly absorbed
- Items accumulate across pages until encountering the next boundary (next work content/sub-item/subcategory/chapter)
- Pages records cover pages

Output: static/structured_data.json
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

INPUT_FILE  = "static/data.json"
OUTPUT_FILE = "static/structured_data.json"

# ========== Preprocessing and Cleaning ==========
FOOTER_RE = re.compile(r"\n?·\s*\d+\s*·\s*")
ZW_RE     = re.compile(r"[\u200B\u200C\u200D\uFEFF\u2060]")  # Zero-width characters/BOM

def clean_tail(s: str) -> str:
    return FOOTER_RE.sub("", s or "").strip()

def normalize_page_text(s: str) -> str:
    """Unify line breaks, remove invisible characters, strip each line to maximize regex hit rate"""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = ZW_RE.sub("", s)
    lines = [ln.strip() for ln in s.split("\n")]
    return "\n".join(lines)

# ========== Regular Expressions ==========
DIG    = r"0-9０-９"
CN_NUM = r"一二三四五六七八九十百〇零"
WS     = r"[ \t\u3000]"
DOT    = r"[．\.]"

# Chapter: e.g. "Chapter One Earthwork\n(0101)"
chapter_re = re.compile(rf"^第[{CN_NUM}{DIG}]+章{WS}+([^\n]+?)\n（[{DIG}]{{4,6}}）", re.M)

# ---- Code suffix (safe writing to avoid '-' character class range conflicts) ----
CODE_NUM    = rf"[{DIG}]+"
CODE_SEP    = r"(?:\s*(?:-|–|—|－|~|～)\s*)"      # Support multiple hyphens/tildes
CODE_TAIL   = rf"(?:{CODE_NUM}(?:{CODE_SEP}{CODE_NUM})?)"
CODE_SUFFIX = rf"(?:（\s*编码[:：]?\s*{CODE_TAIL}\s*）|（\s*{CODE_TAIL}\s*）|\(\s*{CODE_TAIL}\s*\))"

# Subcategory (with/without code both acceptable; "、" after **when there is a code, space is optional**, **when there is no code, space is mandatory**)
section_re = re.compile(
    rf"""
    ^
    [{CN_NUM}{DIG}]+、                             
    (?:
        {WS}*                                      # Branch 1: With code → space is optional
        (?P<title1>[^\n（(]+?)\s*
        {CODE_SUFFIX}
      |
        {WS}+                                      # Branch 2: Without code → space is mandatory
        (?P<title2>[^\n（(]+?)\s*
    )
    $
    """,
    re.M | re.X
)

# Sub-item: e.g. "1. Diaphragm Wall / 1. Cast-in-place Component Round Reinforcement"
# Rule: 1.xxx or 1. xxx, and **the next non-empty line** is "Work Content:" or "(1)…/(1)…"
subsection_re = re.compile(
    rf"^\s*[{DIG}]+{DOT}{WS}*([^\n\r]+?)\s*(?=\n\s*(?:工作内容：|[（(][{DIG}]+[）)]))",
    re.M
)

# Further subdivision under sub-item: e.g. "(1) Point Tamping / (1) Point Tamping"
# Only used as boundary/anchor point (not combined into name)
subsubsection_re = re.compile(
    rf"^\s*[（(][{DIG}]+[）)]{WS}*([^\n\r]+?)\s*$",
    re.M
)

# Work content anchor + measurement unit line
work_anchor_re = re.compile(r"^\s*工作内容：", re.M)
unit_line_re   = re.compile(r"计量单位：[ \t\u3000]*([^\n\r]*)")

# "Same as previous" recognition (allowing whitespace and punctuation at the beginning)
SAME_AS_PREV_RE = re.compile(r"^\s*同前[。,.、；;]?\s*", re.I)

# Any "title-like" beginning (to prevent mistakenly absorbing items)
heading_start_re = re.compile(
    rf"^\s*(?:第[{CN_NUM}{DIG}]+章|[{CN_NUM}{DIG}]+、|[{DIG}]+{DOT}{WS}*|[（(][{DIG}]+[）)]|工作内容：)"
)

# ========== Token Extraction ==========
def find_tokens(page_text: str):
    """
    Return sorted token list by starting position: [(kind, match), ...]
    kind in {"chapter","section","subsection","subsubsection","work"}
    """
    tokens = []
    for m in chapter_re.finditer(page_text):
        tokens.append(("chapter", m))
    for m in section_re.finditer(page_text):
        tokens.append(("section", m))
    for m in subsection_re.finditer(page_text):
        tokens.append(("subsection", m))
    for m in subsubsection_re.finditer(page_text):
        tokens.append(("subsubsection", m))
    for m in work_anchor_re.finditer(page_text):
        tokens.append(("work", m))
    tokens.sort(key=lambda x: x[1].start())
    return tokens

def extract_work_key(anchored_text: str) -> Optional[str]:
    """
    anchored_text starts with "工作内容：" (remaining part of this page)
    Find the first "计量单位：" in this text and return:
      "工作内容：... 计量单位：Xxx" (keep both keywords as dictionary key)
    If "计量单位：" is not found, return None
    """
    m = unit_line_re.search(anchored_text)
    if not m:
        return None
    head = anchored_text[: m.end()]
    head = clean_tail(head).strip()
    # Fault tolerance: ensure it starts with "工作内容："
    if not head.startswith("工作内容："):
        idx = head.find("工作内容：")
        if idx > -1:
            head = head[idx:].strip()
        else:
            return None
    return head

def is_same_as_previous(work_key: str) -> bool:
    """Check if work content is 'same as previous' (ignoring unit segment)"""
    inside = work_key.replace("工作内容：", "", 1)
    inside = inside.split("计量单位：", 1)[0]
    inside = inside.strip()
    return bool(SAME_AS_PREV_RE.match(inside))

# ========== Main Process ==========
def process_quota_data(json_file_path=INPUT_FILE, out_file=OUTPUT_FILE):
    pages = json.loads(Path(json_file_path).read_text(encoding="utf-8"))

    # ---- Filtering Phase ----
    filtered = []
    for row in pages:
        pno = int(row.get("page_number", 0))
        if pno < 13 or pno > 760:
            continue
        content = row.get("content", "") or ""
        text = content.strip()

        # Page header "Instructions/Engineering Quantity Calculation Rules"
        if text[:2] == "说明":
            continue
        if text.startswith("工程量计算规则"):
            continue
        # Text without keywords and long text
        if ("工作内容" not in text and "计量单位" not in text and len(text) > 50):
            continue

        filtered.append({"page_number": pno, "content": content})

    # ---- Page-by-page State Machine ----
    result: Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]] = {}

    current_chapter: Optional[str] = None
    current_section: Optional[str] = None
    current_subsection: Optional[str] = None
    current_subsubsection: Optional[str] = None
    last_work_key: Optional[str] = None  # Track for "same as previous" merging

    current_work_key: Optional[str] = None
    collecting_items = False
    current_items: List[str] = []
    current_pages: List[int] = []

    def effective_subsection_name() -> Optional[str]:
        """
        Return "effective sub-item name":
        - No longer combine Sub-item(Further Subdivision), only return Sub-item;
        - If there is currently no sub-item, use the engineering subcategory as fallback.
        """
        sub = current_subsection or current_section
        return sub

    def finalize_current():
        """Write the currently accumulated work into results and clear the building blocks"""
        nonlocal current_work_key, current_items, current_pages, last_work_key, collecting_items

        eff_sub = effective_subsection_name()
        if current_chapter and current_section and eff_sub and current_work_key:
            chap = result.setdefault(current_chapter, {})
            sec  = chap.setdefault(current_section, {})
            sub  = sec.setdefault(eff_sub, {})
            entry = sub.setdefault(current_work_key, {"items": [], "pages": []})

            # Items cleaning and appending
            cleaned_items = []
            for it in current_items:
                it2 = clean_tail(it)
                if not it2:
                    continue
                # Do not put any "title-like" lines into items
                if heading_start_re.match(it2):
                    continue
                cleaned_items.append(it2)
            for it in cleaned_items:
                if it not in entry["items"]:
                    entry["items"].append(it)

            # Pages merging and deduplication
            for p in current_pages:
                if p not in entry["pages"]:
                    entry["pages"].append(p)
            entry["pages"].sort()

            # Update last_work_key (for "same as previous" merging)
            last_work_key = current_work_key

        # Clear
        current_work_key = None
        collecting_items = False
        current_items = []
        current_pages = []

    # Process page by page
    for row in filtered:
        page_no = int(row["page_number"])
        text = normalize_page_text(row["content"] or "")

        cursor = 0
        tokens = find_tokens(text)

        # If collecting items and the first token on this page has text before it, absorb it first
        if collecting_items and (not tokens or tokens[0][1].start() > 0):
            pre = text[0 : tokens[0][1].start()] if tokens else text
            pre = clean_tail(pre)
            if pre and not heading_start_re.match(pre):
                current_items.append(pre)
                if page_no not in current_pages:
                    current_pages.append(page_no)
            cursor = tokens[0][1].start() if tokens else len(text)

        # Iterate through tokens
        for kind, m in tokens:
            start, end = m.start(), m.end()

            # Fragment before token, if collecting then absorb
            if collecting_items and cursor < start:
                chunk = text[cursor:start]
                chunk = clean_tail(chunk)
                if chunk and not heading_start_re.match(chunk):
                    current_items.append(chunk)
                    if page_no not in current_pages:
                        current_pages.append(page_no)

            if kind == "chapter":
                finalize_current()
                current_chapter = m.group(1).strip()
                current_section = None
                current_subsection = None
                current_subsubsection = None

            elif kind == "section":
                finalize_current()
                # Group 1 or 2 may match the title
                title = m.group("title1") or m.group("title2") or ""
                current_section = title.strip()
                current_subsection = None
                current_subsubsection = None


            elif kind == "subsection":
                finalize_current()
                current_subsection = m.group(1).strip()
                current_subsubsection = None

            elif kind == "subsubsection":
                # Only used as boundary, no longer combine name into "Sub-item (Further Subdivision)"
                # If there was no sub-item before, still use engineering subcategory as fallback (convenient for subsequent work content attribution)
                if not current_subsection:
                    current_subsection = current_section
                current_subsubsection = m.group(1).strip()

            elif kind == "work":
                # If there is no sub-item yet, first use engineering subcategory name as fallback
                if current_chapter and current_section and not current_subsection:
                    current_subsection = current_section
                    current_subsubsection = None

                anchor_tail = text[m.start():]
                key = extract_work_key(anchor_tail)

                if key is None or not (current_chapter and current_section and effective_subsection_name()):
                    # Invalid work, clear collection status
                    finalize_current()
                    cursor = end
                    continue

                # "Same as previous"? → Merge into previous work content
                if is_same_as_previous(key) and last_work_key:
                    current_work_key = last_work_key
                    collecting_items = True
                    if page_no not in current_pages:
                        current_pages.append(page_no)
                else:
                    # Normal new start
                    finalize_current()
                    current_work_key = key
                    collecting_items = True
                    current_items = []
                    current_pages = [page_no]

            cursor = end

        # End of page: if collecting, swallow the tail
        if collecting_items and cursor < len(text):
            tail = text[cursor:]
            tail = clean_tail(tail)
            if tail and not heading_start_re.match(tail):
                current_items.append(tail)
                if page_no not in current_pages:
                    current_pages.append(page_no)

    # Finalize
    finalize_current()

    # Write file
    Path(OUTPUT_FILE).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Structured data saved to: {OUTPUT_FILE}")
    return result, OUTPUT_FILE


if __name__ == "__main__":
    process_quota_data()