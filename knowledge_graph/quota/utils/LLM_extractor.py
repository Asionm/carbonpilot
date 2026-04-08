# -*- coding: utf-8 -*-
"""
Send each entry in static/structured_data.json to Dify / Ollama to generate augmented results.
Improvement: Prefer reusing old augmented results (static/structured_llm_augmented.json)
within the same "Engineering Category / Subcategory / Sub-item".
If no reusable result is found at that level, then call the LLM.
Used to “complete” newly processed content when original input has missing pages/sections.
"""

import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from tqdm import tqdm
import requests
from dotenv import load_dotenv

dotenv_path = ".env"
load_dotenv(dotenv_path)
# =============== Choose backend engine ===============
ENGINE = "dify"   # "dify" or "ollama"

# =============== Dify basic config ===============
DIFY_BASE_URL = "http://127.0.0.1/"
DIFY_API_KEY  = "xxx"
DIFY_USER_ID  = "xxx"
RESPONSE_MODE = "blocking"  # or "streaming"

# =============== Ollama basic config ===============
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL    = os.getenv("LLM_MODEL_NAME")
OLLAMA_STREAM   = False

# =============== Input/Output files ===============
INPUT_FILE     = "static/structured_data.json"
OUTPUT_FILE    = "static/structured_llm_augmented.json"   # New output (incrementally written)
OLD_OUTPUT_FILE = "static/structured_llm_augmented.json"  # Old augmented results as reuse source (can be same file)

SLEEP_BETWEEN_CALLS = 0.05

# =============== Debug (only run a small subset) ===============
DEBUG = False
DEBUG_MAX_CHAPTERS    = 1
DEBUG_MAX_SECTIONS    = 1
DEBUG_MAX_SUBSECTIONS = 1
DEBUG_MAX_WORKS       = 1
DEBUG_MAX_ITEM_BLOCKS = 1

# ================= Utility functions =================
def to_halfwidth(s: str) -> str:
    res = []
    for ch in s or "":
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            res.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            res.append(" ")
        else:
            res.append(ch)
    return "".join(res)

def normalize_unit_text(u: str) -> str:
    u = to_halfwidth((u or "")).strip()
    u = re.sub(r"m\s*\^?\s*3", "m3", u, flags=re.I)
    u = re.sub(r"m\s*\^?\s*2", "m2", u, flags=re.I)
    u = re.sub(r"\s+", "", u)
    return u

def normalize_id_text(s: str) -> Optional[str]:
    s = to_halfwidth(s or "").strip()
    nums = re.findall(r"\d+", s)
    if len(nums) >= 2:
        a, b = int(nums[0]), int(nums[1])
        return f"{a}-{b}"
    return None

def normalize_key(s: str) -> str:
    """Used for aligning hierarchy keys: convert to halfwidth + collapse whitespace"""
    s = to_halfwidth(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def normalize_content_text(s: str) -> str:
    """Used for matching work content: convert to halfwidth + remove whitespace"""
    s = to_halfwidth(s or "")
    s = re.sub(r"\s+", "", s)
    return s

def extract_content_and_unit(raw_work: str) -> Tuple[str, Optional[str]]:
    text = raw_work or ""
    if text.startswith("工作内容："):
        text = text[len("工作内容："):]
    m = re.search(r"计量单位：([^\n\r]*)", text)
    unit = normalize_unit_text(m.group(1)) if m else None
    text = re.sub(r"计量单位：[^\n\r]*", "", text).strip()
    return text, unit

# ================= LLM interaction =================
def build_ollama_prompt(unit_hint: str, item_text: str) -> str:
    unit_hint = to_halfwidth(unit_hint or "").strip()
    item_text = to_halfwidth(item_text or "").strip()
    schema = (
        '{"items":[{"name":"","id":"","unit":"","activities":{'
        '"labor":[{"name":"","unit":"workday","value":0}],'
        '"material":[{"name":"","unit":"","value":0}],'
        '"machinery":[{"name":"","unit":"shift","value":0}]}}]}'
    )
    rules = (
        "Task:\n"
        "1) Convert fullwidth to halfwidth; IDs unified as number-number (e.g., 1-55).\n"
        "2) Output only a JSON object with root key 'items'; fields strictly follow the example.\n"
        "3) Remove summary items such as 'total workdays'.\n"
        "4) All values must be numeric.\n"
        "5) Do NOT output extra text or code blocks.\n"
    )
    structure = "Output structure example (fill real data in the return):\n" + schema + "\n"
    io = f"Input:\n- unit_hint: {unit_hint}\n- item_text: {item_text}\n"
    return "You are an engineering quota item parser.\n\n" + rules + structure + io

def dify_workflow_run(inputs: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{DIFY_BASE_URL}/v1/workflows/run"
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
    payload = {"inputs": inputs or {}, "response_mode": RESPONSE_MODE, "user": DIFY_USER_ID}
    r = requests.post(url, headers=headers, json=payload, timeout=90)
    r.raise_for_status()
    return r.json()

def ollama_generate(unit_hint: str, item_text: str) -> Dict[str, Any]:
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {"model": OLLAMA_MODEL, "prompt": build_ollama_prompt(unit_hint, item_text), "stream": OLLAMA_STREAM}
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    text = (data or {}).get("response") or ""
    return {"data": {"outputs": {"answer": text}}}

def call_llm(inputs: Dict[str, Any]) -> Dict[str, Any]:
    return dify_workflow_run(inputs) if ENGINE == "dify" else ollama_generate(inputs.get("unit_hint",""), inputs.get("item_text",""))

def extract_items_from_response(resp_json: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(resp_json, dict):
        return None
    outputs = (resp_json.get("data") or {}).get("outputs") or {}
    answer = outputs.get("answer")
    if answer is None:
        return None
    if isinstance(answer, dict):
        return answer.get("items") if isinstance(answer.get("items"), list) else None
    if isinstance(answer, list):
        return answer
    if isinstance(answer, str):
        txt = answer.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```(?:json)?", "", txt, flags=re.I).strip()
            txt = re.sub(r"```$", "", txt).strip()
        try:
            data = json.loads(txt)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
            if isinstance(data, list):
                return data
        except Exception:
            return None
    return None

# ================= Cleaning =================
def _coerce_numeric(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    s = to_halfwidth(str(v)).strip().replace(",", "")
    if not re.match(r"^[+-]?\d+(?:\.\d+)?$", s or ""):
        return None
    try:
        return float(s)
    except Exception:
        return None

def normalize_entry(x, default_unit=None):
    if not isinstance(x, dict):
        return None
    name = str(x.get("name", "")).strip()
    unit = normalize_unit_text(x.get("unit") or (default_unit or ""))
    val  = _coerce_numeric(x.get("value"))
    if not name or val is None:
        return None
    return {"name": name, "unit": unit, "value": val}

def clean_llm_items(llm_items: List[Dict[str, Any]], unit_hint: Optional[str]) -> List[Dict[str, Any]]:
    out = []
    for rec in llm_items or []:
        if not isinstance(rec, dict):
            continue
        if unit_hint and not rec.get("unit"):
            rec["unit"] = unit_hint
        if rec.get("unit"):
            rec["unit"] = normalize_unit_text(rec["unit"])
        rid = rec.get("id")
        fixed_id = normalize_id_text(str(rid)) if rid is not None else None
        if fixed_id:
            rec["id"] = fixed_id
        acts = rec.get("activities") or {}
        labor = acts.get("labor") or []
        material = acts.get("material") or []
        machinery = acts.get("machinery") or []
        # Remove summary rows
        labor = [a for a in labor if str(a.get("name","")).strip() not in ("合计工日","合计","合计人工")]
        labor     = list(filter(None, (normalize_entry(a, "工日") for a in labor)))
        material  = list(filter(None, (normalize_entry(a, None)  for a in material)))
        machinery = list(filter(None, (normalize_entry(a, "台班") for a in machinery)))
        rec["activities"] = {"labor": labor, "material": material, "machinery": machinery}
        if labor or material or machinery:
            out.append(rec)
    return out

# ================= Old-result hierarchy index (for reuse) =================
def build_old_hierarchy_index(old_out: Dict[str, Any]):
    """
    Returns:
    - idx_sub: {chap_key: {sec_key: {sub_key: [ {content_norm: str, items: [...]}, ... ]}}}
    Used to prefer exact content matching; if the level has only one work, fallback reuse is allowed.
    """
    idx_sub: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
    for chap_name, chap_obj in (old_out or {}).items():
        if not isinstance(chap_obj, dict): continue
        cK = normalize_key(chap_name)
        for sec_name, sec_obj in chap_obj.items():
            if not isinstance(sec_obj, dict): continue
            sK = normalize_key(sec_name)
            for sub_name, sub_list in sec_obj.items():
                if not isinstance(sub_list, list): continue
                ssK = normalize_key(sub_name)
                bucket = idx_sub.setdefault(cK, {}).setdefault(sK, {}).setdefault(ssK, [])
                for work in sub_list:
                    content = (work or {}).get("content","")
                    items   = deepcopy((work or {}).get("items") or [])
                    bucket.append({"content_norm": normalize_content_text(content), "items": items})
    return idx_sub

def try_reuse_items(idx_sub, chap_name, sec_name, sub_name, content_now, item_blocks_count: int) -> Optional[List[Dict[str, Any]]]:
    cK, sK, ssK = normalize_key(chap_name), normalize_key(sec_name), normalize_key(sub_name)
    content_norm = normalize_content_text(content_now or "")
    sub_bucket = (((idx_sub.get(cK) or {}).get(sK) or {}).get(ssK) or [])
    if not sub_bucket:
        return None
    # 1) Same hierarchy + exact content match
    for rec in sub_bucket:
        if rec.get("content_norm") == content_norm and rec.get("items"):
            return deepcopy(rec["items"])
    # 2) If only one work in this hierarchy, fallback reuse
    if len(sub_bucket) == 1 and (sub_bucket[0].get("items") or []):
        return deepcopy(sub_bucket[0]["items"])
    # 3) Optional: if multiple works but items are identical — conservative: disabled
    return None

# ================= Main process =================
def quota_extractor():
    # Current output (incremental writing)
    out_root: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
    if Path(OUTPUT_FILE).exists():
        try:
            out_root = json.loads(Path(OUTPUT_FILE).read_text(encoding="utf-8"))
            print(f"▶ Loaded existing output (incremental continuation): {OUTPUT_FILE}")
        except Exception as e:
            print(f"⚠ Unable to parse existing output file, starting from scratch: {e}")
            out_root = {}

    # Old augmented results (reuse source)
    old_aug_source: Dict[str, Any] = {}
    if Path(OLD_OUTPUT_FILE).exists():
        try:
            old_aug_source = json.loads(Path(OLD_OUTPUT_FILE).read_text(encoding="utf-8"))
            print(f"▶ Loaded old augmented results (reuse source): {OLD_OUTPUT_FILE}")
        except Exception as e:
            print(f"⚠ Unable to parse old augmented file: {e}")
            old_aug_source = {}

    old_idx_sub = build_old_hierarchy_index(old_aug_source)

    root = json.loads(Path(INPUT_FILE).read_text(encoding="utf-8"))

    # Count total tasks (for progress bar)
    total_tasks = 0
    for chapter_name, chapter_obj in root.items():
        for section_name, section_obj in chapter_obj.items():
            for subsection_name, subsection_obj in section_obj.items():
                for work_raw, payload in subsection_obj.items():
                    item_blocks = (payload.get("items") or []) if isinstance(payload, dict) else []
                    total_tasks += len(item_blocks)

    pbar = tqdm(total=total_tasks, desc="Progress", unit="items") if not DEBUG else None

    for chapter_name, chapter_obj in root.items():
        if DEBUG and len(out_root) >= DEBUG_MAX_CHAPTERS: break
        out_root.setdefault(chapter_name, {})

        for section_name, section_obj in chapter_obj.items():
            if DEBUG and len(out_root[chapter_name]) >= DEBUG_MAX_SECTIONS: break
            out_root[chapter_name].setdefault(section_name, {})

            for subsection_name, subsection_obj in section_obj.items():
                if DEBUG and len(out_root[chapter_name][section_name]) >= DEBUG_MAX_SUBSECTIONS: break

                # Skip if already generated
                if subsection_name in out_root[chapter_name][section_name]:
                    if pbar:
                        done_count = sum(len((w or {}).get("items") or [])
                                         for w in out_root[chapter_name][section_name][subsection_name])
                        pbar.update(done_count)
                    continue

                work_list: List[Dict[str, Any]] = []

                for work_raw, payload in subsection_obj.items():
                    if DEBUG and len(work_list) >= DEBUG_MAX_WORKS: break
                    if not isinstance(payload, dict): continue

                    item_blocks: List[str] = payload.get("items", []) or []
                    content, unit_hint = extract_content_and_unit(work_raw)

                    # ===== Try reuse from same hierarchy =====
                    reused_items = try_reuse_items(
                        old_idx_sub, chapter_name, section_name, subsection_name, content, len(item_blocks)
                    )
                    if reused_items is not None:
                        work_list.append({"content": content, "items": reused_items})
                        if pbar: pbar.update(len(item_blocks))
                        continue

                    # ===== If no reusable result, call LLM =====
                    aggregated: List[Dict[str, Any]] = []
                    for item_text in item_blocks:
                        if DEBUG and len(aggregated) >= DEBUG_MAX_ITEM_BLOCKS: break
                        try:
                            inputs = {"unit_hint": unit_hint or "", "item_text": item_text}
                            resp = call_llm(inputs)
                            items = extract_items_from_response(resp) or []
                            cleaned = clean_llm_items(items, unit_hint)
                            aggregated.extend(cleaned)
                        except Exception as e:
                            print(f"❌ LLM call error, skipping this item: {e}")
                        finally:
                            if pbar: pbar.update(1)
                            if SLEEP_BETWEEN_CALLS > 0: time.sleep(SLEEP_BETWEEN_CALLS)

                    work_list.append({"content": content, "items": aggregated})

                out_root[chapter_name][section_name][subsection_name] = work_list

                # Incremental save
                Path(OUTPUT_FILE).write_text(
                    json.dumps(out_root, ensure_ascii=False, indent=2), encoding="utf-8"
                )

    if pbar: pbar.close()
    print(f"\nOutput written to: {OUTPUT_FILE}")
