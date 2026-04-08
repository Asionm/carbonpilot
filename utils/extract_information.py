# utils\extract_information.py
import re
from pathlib import Path
from typing import NotRequired, Optional, TypedDict, Union, List, Any, Tuple, Dict
import shutil
import subprocess

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import TextLoader
from langgraph.graph import StateGraph, END, START
import yaml

from configs.llm_wrapper import LLMWrapper
from schemes.project_info import WBSRoot
from prompts import SELECT_CHUNK_PROMPT, READ_CHUNK_PROMPT, FINAL_EXTRACTION_PROMPT
import logging
import json
from datetime import datetime

from dataclasses import is_dataclass, asdict
import pandas as pd
import os

from markitdown import MarkItDown
from utils.toon_decoder import toon_decode


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("extract.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("InformationExtractor")

# ---- Logging helpers: Safe truncation and unread statistics ----
def _snip(s: str, n: int = 400) -> str:
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= n else s[:n] + "...truncated"

def _unread_stats(chunks: List[Dict]) -> Tuple[int, int, List[int]]:
    total = len(chunks)
    unread_indices = [c["index"] for c in chunks if c.get("status", False)]
    return len(unread_indices), total, unread_indices

# --- helpers & regex/globals --------------------------------------------------

_JSON_START_RE = re.compile(r"[{\[]")
_JSON_END_MAP = {"{": "}", "[": "]"}


def _strip_code_fences(text: str) -> str:
    # Remove ```json ... ``` or ``` ... ```
    return re.sub(
        r"```(?:json|javascript|js|py)?\s*([\s\S]*?)\s*```",
        r"\1",
        text.strip(),
        flags=re.IGNORECASE,
    )


def _slice_to_balanced_json(s: str) -> str:
    """
    Extract the first balanced JSON fragment from arbitrary text (supporting mixed {} and [] and skipping strings),
    effectively removing noise or additional text before or after.
    """
    m = _JSON_START_RE.search(s)
    if not m:
        return s  # Try original

    start = m.start()
    stack = [s[start]]
    in_str = False
    escape = False

    for i in range(start + 1, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                escape = False
                continue
            if ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if not stack:
                    break
                opener = stack.pop()
                if _JSON_END_MAP[opener] != ch:
                    # Fault tolerance: if type mismatch, ignore this closing character
                    stack.append(opener)
                    continue
                if not stack:
                    return s[start : i + 1]

    # Not balanced, try to slice to the end
    return s[start:]


def _escape_newlines_inside_strings(text: str) -> str:
    """
    Replace bare newlines in string literals with \\n to avoid "Unterminated string".
    """
    out = []
    in_str = False
    escape = False
    for ch in text:
        if in_str:
            if escape:
                out.append(ch)
                escape = False
            else:
                if ch == "\\":
                    out.append(ch)
                    escape = True
                elif ch == '"':
                    out.append(ch)
                    in_str = False
                elif ch in ("\r", "\n"):
                    out.append("\\n")
                else:
                    out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_str = True
                escape = False
    # If string is not closed, add a quote to try to pair it
    if in_str:
        out.append('"')
    return "".join(out)


def _lightweight_repairs(s: str) -> str:
    """
    Perform lightweight repairs on common "non-strict JSON":
    - Remove BOM
    - Unify smart quotes to regular quotes
    - Fix keys broken by line breaks (e.g. "scale\n": or "scale\n" next key)
    - Replace bare newlines in string literals with \\n
    - Remove trailing commas in objects/arrays
    - Replace NaN/Infinity/-Infinity with null
    - Try to complete missing right brackets
    """
    s = s.lstrip("\ufeff")

    # Smart quotes -> regular quotes
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    # Fix "key" and colon separated by line break:  "key"\n   :  -> "key":
    s = re.sub(r'("([^"\\]|\\.)*")\s*[\r\n]+\s*:', r"\1:", s)

    # More aggressive: fix "dangling key" directly followed by next key: "key"\n  "next"  -> "key": null, "next"
    s = re.sub(r'("([^"\\]|\\.)*")\s*[\r\n]+\s*(")', r'\1: null, \3', s)

    # Bare newlines in strings -> \n
    s = _escape_newlines_inside_strings(s)

    # Trailing commas (before }, ]})
    s = re.sub(r",\s*([}\]])", r"\1", s)

    # NaN/Infinity -> null
    s = re.sub(r"\b-?Infinity\b", "null", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNaN\b", "null", s, flags=re.IGNORECASE)
    s = re.sub(r"\b-?Inf\b", "null", s, flags=re.IGNORECASE)

    # Simple completion of missing right brackets (add by counting difference; may be in strings but improves success rate)
    need_curly = s.count("{") - s.count("}")
    need_square = s.count("[") - s.count("]")
    if need_square > 0:
        s += "]" * need_square
    if need_curly > 0:
        s += "}" * need_curly

    return s


def _json_error_context(s: str, err: json.JSONDecodeError, radius: int = 60) -> str:
    start = max(0, err.pos - radius)
    end = min(len(s), err.pos + radius)
    frag = s[start:end]
    caret = " " * (err.pos - start) + "^"
    return f"{frag}\n{caret}\n@pos {err.pos}: {err.msg}"


def _filter_known_fields(model_cls, data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known fields in target Pydantic model to avoid strict mode errors."""
    try:
        # pydantic v2
        fields = getattr(model_cls, "model_fields", None)
        if fields:
            allow = set(fields.keys())
            return {k: v for k, v in data.items() if k in allow}
        # pydantic v1
        fields_v1 = getattr(model_cls, "__fields__", None)
        if fields_v1:
            allow = set(fields_v1.keys())
            return {k: v for k, v in data.items() if k in allow}
    except Exception:
        pass
    return data


def _safe_build_model(model_cls, data: Dict[str, Any], *, partial: bool) -> Any:
    """
    Construct Pydantic instance with strongest fallback:
    1) Try strict validation
    2) If failed, keep only model fields and use construct/model_construct to skip validation
    3) Try empty construction if that fails
    4) Still failing, return dict (guarantee **always return**)
    """
    # 1) Strict validation (complete)
    if not partial:
        try:
            return model_cls(**data)
        except Exception:
            pass

    # 2) Loose construction (keep only known fields)
    filtered = _filter_known_fields(model_cls, data)
    try:
        # pydantic v2
        ctor = getattr(model_cls, "model_construct", None)
        if callable(ctor):
            return ctor(**filtered)
    except Exception:
        pass
    try:
        # pydantic v1
        ctor_v1 = getattr(model_cls, "construct", None)
        if callable(ctor_v1):
            return ctor_v1(**filtered)
    except Exception:
        pass

    # 3) Empty construction
    try:
        return model_cls()
    except Exception:
        pass

    # 4) Final fallback: return dict
    return filtered or {"_fallback": True}


# --- Main class: Even if error occurs, still return -----------------------------------------------------

class SmartPydanticOutputParser(PydanticOutputParser):
    """
    - Remove code blocks & noise
    - Automatically extract the first "balanced bracket" JSON fragment
    - Lightweight repair of common non-strict JSON (including string breaks caused by line feeds, trailing commas, etc.)
    - Better error context
    - Support partial (missing fields still work)
    - **Key**: Will always return (model instance or dictionary), never throw to upper level
    """

    def parse_result(self, result, *, partial: bool = False):
        # ---------------------------
        # 0) Extract raw text safely
        # ---------------------------
        try:
            raw = result[0].text if isinstance(result, (list, tuple)) else str(result)
        except Exception as e:
            logger.error(f"[parse_result/raw-extract] {e}", exc_info=True)
            raw = str(result)

        # Trim whitespace
        raw = raw.strip()

        # ---------------------------
        # 1) Try TOON first
        # ---------------------------
        if raw:
            try:
                toon_data = toon_decode(raw)
                if not isinstance(toon_data, dict):
                    logger.error("[parse_result] TOON decoded non-dict root; rejecting")
                    raise ValueError("TOON root must be a dict")
                logger.info("[parse_result] Parsed as TOON successfully")
                return _safe_build_model(self.pydantic_object, toon_data, partial=partial)
            except Exception as e:
                logger.warning(f"[parse_result] TOON parsing failed: {e}")

        # -------------------------------------------------
        # 2) Continue with EXISTING JSON/YAML repair chain
        # -------------------------------------------------

        # A) Strip code fences
        try:
            cleaned = _strip_code_fences(raw) or raw
        except Exception:
            cleaned = raw

        # B) Try to isolate first balanced JSON object
        try:
            sliced = _slice_to_balanced_json(cleaned) or cleaned
        except Exception:
            sliced = cleaned

        # C) Lightweight textual repairs
        try:
            candidate = _lightweight_repairs(sliced) or sliced
        except Exception:
            candidate = sliced

        # -----------------------
        # 3) JSON strict attempt
        # -----------------------
        try:
            data = json.loads(candidate)
            if not isinstance(data, dict):
                data = {"data": data}
            return _safe_build_model(self.pydantic_object, data, partial=partial)

        except json.JSONDecodeError as e1:
            logger.error(f"[parse_result/json-loads#1] {e1}")

            # D) More repairs
            try:
                advanced = _lightweight_repairs(candidate)
            except Exception:
                advanced = candidate

            # Retry JSON
            try:
                data = json.loads(advanced)
                if not isinstance(data, dict):
                    data = {"data": data}
                return _safe_build_model(self.pydantic_object, data, partial=partial)

            except json.JSONDecodeError as e2:
                logger.error(f"[parse_result/json-loads#2] {e2}")

                # -----------------------
                # 4) YAML fallback
                # -----------------------
                try:
                    yaml_data = yaml.safe_load(advanced)
                    if not isinstance(yaml_data, dict):
                        yaml_data = {"data": yaml_data}
                    return _safe_build_model(self.pydantic_object, yaml_data, partial=partial)
                except Exception as e3:
                    logger.error(f"[parse_result/yaml-loads] {e3}")

                    # -----------------------
                    # 5) Final fallback dict
                    # -----------------------
                    fallback = {
                        "_fallback": True,
                        "_error": "Failed to decode as TOON/JSON/YAML",
                        "_raw_head": candidate[:2000],
                    }
                    return _safe_build_model(
                        self.pydantic_object, fallback, partial=True
                    )


    def get_toon_instructions(self):
        """
        Strict TOON-format instructions designed for WBS output.
        Structure:
        - Upper levels use YAML-style object lists.
        - Final leaf level (sub_item_work) uses TOON tabular arrays.
        All output MUST be valid TOON, decodable by toon_format.decode().
        """
        instructions = [
            "You MUST output the final result using STRICT TOON format.",
            "NEVER output JSON. NEVER output markdown. NEVER output explanations.",
            "Your output MUST be a single TOON document representing one WBSRoot object.",
            "",

            "======================== TOON FORMAT RULES ========================",
            "",
            "TOON supports three array forms:",
            "1) Primitive array:      key[n]: v1,v2,v3",
            "2) Mixed object array:   key[n]:",
            "                           - key: value",
            "                           - another: value",
            "3) Tabular array:        key[n]{f1,f2,f3}:",
            "                           v1,v2,f3",
            "                           v1,v2,f3",
            "",
            "In THIS TASK:",
            "- Upper levels MUST use mixed-object form (#2).",
            "- The final sub_item_work level MUST use tabular form (#3).",
            "",
            "IMPORTANT:",
            "- children[n] MUST match the actual number of child nodes.",
            "- Indentation MUST be exactly two spaces per level.",
            "- Strings containing commas or newlines MUST be quoted.",
            '- Example: description: \"text, with comma\"',
            "",
            "====================================================================",
            "WBS HIERARCHY DEFINITIONS (MANDATORY)",
            "====================================================================",
            "",
            "construction_project (建设项目):",
            "  The entire construction work scope. Example: 城市更新一期 / 科技园区建设工程.",
            "",
            "individual_project (单项工程):",
            "  A relatively independent functional part of the project.",
            "  Examples: 住宅楼 A 栋 / 商业楼 B 区 / 地下车库.",
            "",
            "unit_project (单位工程):",
            "  A professional engineering unit, usually matching disciplines.",
            "  Examples: 土建工程 / 装饰工程 / 电气工程 / 给排水工程.",
            "",
            "sub_divisional_work (分部工程):",
            "  A division of work based on system/structure/space.",
            "  Examples: 地基基础工程 / 主体结构工程 / 屋面工程 / 装饰装修工程.",
            "",
            "specialty_subdivision (子分部工程):",
            "  A subdivision based on material/craft category.",
            "  Examples: 桩基工程 / 混凝土结构工程 / 幕墙工程 / 抹灰工程.",
            "",
            "sub_item_work (分项工程):",
            "  Final measurable work items.",
            "  Examples: 钢筋绑扎、C30 混凝土浇筑、腻子找平、石材铺贴.",
            "Only sub_item_work has (unit, quantity).",
            "",

            "====================================================================",
            "MINIMAL REQUIRED TOON STRUCTURE EXAMPLE (MANDATORY)",
            "====================================================================",
            "",
            "# DO NOT copy values; only follow the structure.",
            "level: construction_project",
            "name: 项目名称",
            "description: \"\"",
            "children[1]:",
            "  - level: individual_project",
            "    name: 单项工程名称",
            "    description: \"\"",
            "    children[1]:",
            "      - level: unit_project",
            "        name: 单位工程名称",
            "        description: \"\"",
            "        children[1]:",
            "          - level: sub_divisional_work",
            "            name: 分部工程名称",
            "            description: \"\"",
            "            children[1]:",
            "              - level: specialty_subdivision",
            "                name: 子分部名称",
            "                description: \"\"",
            "                children[2]{level,name,description,unit,quantity}:",
            "                  sub_item_work,工作内容1,\"描述\",m2,10",
            "                  sub_item_work,工作内容2,\"描述\",m3,5",
            "",
            "This example EXISTS ONLY to ensure the model ALWAYS outputs `level`, tabular arrays, and correct indentation.",
            "",

            "====================================================================",
            "MISSING LEVEL COMPLETION RULES",
            "====================================================================",
            "",
            "If a required level is missing, YOU MUST auto-create it:",
            "",
            "1) If sub_item_work appears under unit_project OR sub_divisional_work:",
            "   → Insert a default specialty_subdivision.",
            "   Naming rule:",
            "       - If all child items belong to a craft, use that craft as name.",
            "       - Otherwise: \"unnamed specialty subdivision\".",
            "",
            "2) If sub_divisional_work is missing:",
            "   → Insert `unnamed sub-divisional work`.",
            "",
            "3) If individual_project contains sub_item_work directly:",
            "   → Insert unit_project + sub_divisional_work + specialty_subdivision.",
            "",
            "4) ALL leaves MUST be sub_item_work.",
            "5) NEVER fabricate quantities; only restructure hierarchy.",
            "",

            "====================================================================",
            "STRICT STRUCTURAL RULES",
            "====================================================================",
            "",
            "construction_project → ONLY individual_project",
            "individual_project → ONLY unit_project",
            "unit_project → ONLY sub_divisional_work",
            "sub_divisional_work → ONLY specialty_subdivision",
            "specialty_subdivision → ONLY sub_item_work (tabular array)",
            "sub_item_work → leaf; MUST NOT have children.",
            "",
            "Only sub_item_work has (unit, quantity).",
            "",

            "====================================================================",
            "VALIDATION RULES:",
            "====================================================================",
            "",
            "1. children[n] MUST equal number of child nodes.",
            "2. children[n] MUST NOT be 0 unless genuinely empty.",
            "3. DO NOT mix YAML-style arrays and tabular arrays.",
            "4. Only sub_item_work uses tabular format.",
            "5. Names must be concise Chinese engineering names.",
            "6. Descriptions must include technical information or be empty \"\".",
            "7. Quote descriptions if they contain commas or line breaks.",
            "",
            "====================================================================",
            "END OF INSTRUCTIONS — OUTPUT ONLY THE TOON DOCUMENT.",
            "====================================================================",
        ]

        return "\n".join(instructions)


def _safe_parse_int(s: str) -> int:
    s = (s or "").strip()
    m = re.match(r"^-?\d+", s)
    if not m:
        raise ValueError(f"Cannot parse as integer: {s!r}")
    return int(m.group(0))

def _parse_read_json(s: str) -> Dict[str, str]:
    # Step 1: Remove surrounding Markdown code blocks (```json ... ```)
    cleaned = re.sub(r'^\s*```(?:json)?\s*\n?', '', s, flags=re.IGNORECASE)
    cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # Step 2: Remove invisible or invalid control characters (optional but safe)
    # JSON spec disallows certain Unicode control characters
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', cleaned)  # Remove ASCII control chars except \n \t \r

    # Optional: Replace common problematic escapes
    # If model used single quotes, consider replacing, but be careful (non-standard)
    # Not recommended to automatically replace quotes unless explicitly needed

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Reading segment stage returned non-JSON format. Position={e.pos}, Error={e.msg}, Content={repr(cleaned)}") from e
    except Exception as e:
        raise ValueError(f"Unknown error occurred while parsing JSON at reading segment stage: {cleaned}") from e

    # Step 3: Validate fields
    abstract = data.get("abstract", "")
    comment = data.get("comment", "")

    if not isinstance(abstract, str) or not isinstance(comment, str):
        raise ValueError(f"Read segment JSON field type error: abstract={type(abstract)}, comment={type(comment)}, data={data}")

    return {"abstract": abstract, "comment": comment}



# ----------------------------------------
# Safe & fallback saving tools
# ----------------------------------------

def _ensure_json_suffix(name: str) -> str:
    return name if name.lower().endswith(".json") else f"{name}.json"

def _sanitize_filename(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    # Remove illegal characters (Windows compatible)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    return _ensure_json_suffix(name or "result.json")

def _coerce_to_mapping(obj: Any) -> Dict[str, Any]:
    """Try to convert result to JSON-serializable dict; return fallback dict with original info if failed."""
    # pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()  # type: ignore[attr-defined]
        except Exception:
            pass
    # pydantic v1
    if hasattr(obj, "dict"):
        try:
            return obj.dict()  # type: ignore[call-arg]
        except Exception:
            pass
    # dataclass
    if is_dataclass(obj):
        try:
            return asdict(obj)
        except Exception:
            pass
    # Already a mapping
    if isinstance(obj, dict):
        return obj
    # Other types: fallback
    try:
        return {"value": str(obj)}
    except Exception:
        return {"_fallback": True}

def _json_dumps_safely(data: Any) -> str:
    """Try to convert data to JSON string; use default=str for non-serializable objects."""
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except Exception:
        # Double fallback: wrap data in another string
        return json.dumps({"_fallback": True, "payload": str(data)}, ensure_ascii=False, indent=2)

def _write_atomic(path: Path, payload: str) -> None:
    """
    Atomic write: write to temporary file in same directory first, then replace target file.
    On Windows, if target exists, need to unlink first, otherwise replace may fail.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Use binary write to avoid encoding BOM issues; unified UTF-8
    with open(tmp, "wb") as f:
        f.write(payload.encode("utf-8"))
    try:
        if path.exists():
            try:
                os.replace(tmp, path)  # Prefer atomic replacement
            except Exception:
                path.unlink(missing_ok=True)
                os.replace(tmp, path)
        else:
            os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


class ExtractState(TypedDict):
    # Input/context
    last_index: int
    last_comment: str
    loop: int
    max_loops: int
    # Text chunks
    chunks: List[Dict]               # Your chunk structure
    # Runtime selection
    choice: NotRequired[int]
    selected: NotRequired[Dict]
    # Final extraction input
    abstracts: NotRequired[List[Dict]]
    # Result
    project: NotRequired[WBSRoot]
    # Termination signal
    stop: NotRequired[bool]


class InformationExtractor:
    def __init__(self, normalize_markdown: bool = True):
        self.llm = LLMWrapper().llm
        self.parser = SmartPydanticOutputParser(pydantic_object=WBSRoot)
        self.content = ""
        self.chunks = None

        # Three prompt chains
        self.select_chunk_chain = (SELECT_CHUNK_PROMPT | self.llm | StrOutputParser())
        self.read_chunk_chain = (READ_CHUNK_PROMPT | self.llm | StrOutputParser())
        self.final_extraction_chain = (FINAL_EXTRACTION_PROMPT | self.llm | self.parser)

        # Pre-build graph (node functions depend on self)
        self.graph = self._build_graph()

        self.normalize_markdown = normalize_markdown
        self._md = MarkItDown()

    # ---------- Text format conversion tools ----------
    def _normalize_md(self, text: str) -> str:
        """Light cleaning: strip leading/trailing spaces from lines, compress blank lines, without destroying structure."""
        if not text:
            return text
        lines = [ln.strip() for ln in text.splitlines()]
        compact, last_blank = [], False
        for ln in lines:
            blank = (ln == "")
            if blank and last_blank:
                continue
            compact.append(ln)
            last_blank = blank
        return "\n".join(compact).strip() + "\n"

    def _ensure_tmp_subdir(self, file_path: Path) -> Path:
        """Ensure using tmp/<stem>/ as output directory; do not clean up historical temp files."""
        subdir = Path("tmp") / file_path.stem
        subdir.mkdir(parents=True, exist_ok=True)
        return subdir

    def _convert_with_markitdown(self, file_path: Path) -> str:
        """Use MarkItDown to convert file to Markdown, and save to tmp/<stem>/<stem>.md."""
        result = self._md.convert(str(file_path))
        text = result.text_content or ""
        if self.normalize_markdown:
            text = self._normalize_md(text)

        out_dir = self._ensure_tmp_subdir(file_path)
        out_file = out_dir / f"{file_path.stem}.md"
        out_file.write_text(text, encoding="utf-8")

        # Synchronously save attachments (such as extracted images, audio, etc.)
        if getattr(result, "attachments", None):
            for name, blob in result.attachments.items():
                safe_name = name
                i = 1
                while (out_dir / safe_name).exists():
                    stem, ext = os.path.splitext(name)
                    safe_name = f"{stem}_{i}{ext}"
                    i += 1
                (out_dir / safe_name).write_bytes(blob)
        return text

    # ---------------- Main entry ----------------
    def _load_document(self, file_path: Union[str, Path]) -> str:
        """Support PDF / Excel / TXT / MD (and other formats supported by MarkItDown)"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(str(file_path))

        suffix = file_path.suffix.lower()

        # Handle IFC files
        if suffix == ".ifc":
            try:
                from utils.ifc_extractor import generateBill
                return generateBill(str(file_path))
            except ImportError:
                logger.warning("IFC extractor not available, treating as text")
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()

        # 纯文本与 Markdown 直接读取
        if suffix in {".txt", ".md", ".json", ".xml"}:
            docs = TextLoader(str(file_path), encoding="utf-8").load()
            return "\n\n".join(doc.page_content for doc in docs)

        # PDF 原计划走 MinerU，但暂时不用，保留 MinerU 函数
        if suffix == ".pdf":
            # return self._load_pdf_with_mineru(file_path)  # 暂时注释掉
            return self._convert_with_markitdown(file_path)

        # Excel 以及其他受支持格式统一走 MarkItDown
        if suffix in {".xlsx", ".xls"}:
            return self._convert_with_markitdown(file_path)

        return self._convert_with_markitdown(file_path)

    def _load_pdf_with_mineru(self, pdf_path: Path) -> str:
        """Call MinerU to convert PDF to Markdown, result placed in ./tmp/filename/ (preserved but currently not enabled)."""
        tmp_dir = Path("tmp") / pdf_path.stem
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "mineru",
            "-p", str(pdf_path),
            "-o", str(tmp_dir),
            "-m", "auto"
        ]
        subprocess.run(cmd, check=True)

        md_files = list(tmp_dir.rglob("*.md"))
        if not md_files:
            raise RuntimeError("MinerU did not generate Markdown files")
        text = md_files[0].read_text(encoding="utf-8")
        return text

    # ---------- Get table of contents and fragment tools ----------
    def read_toc(self) -> List[Dict]:
        """
        Return index, title, comment and status from chunks
        """
        if self.chunks is None:
            return []
        
        toc = []
        for chunk in self.chunks:
            toc.append({
                "index": chunk["index"],
                "title": chunk["title"],
                "comment": chunk["comment"],
                "status": chunk["status"]
            })
        return toc

    def get_chunk(self, index: int) -> Union[Dict, str]:
        """
        Return the chunk with specified index, but if the selected index is not in chunks or status is not True,
        need to return a prompt saying the searched index does not exist or has been read, please reselect.
        """
        if self.chunks is None:
            return "Searched index does not exist, please process document first."
        
        # Find chunk with specified index
        target_chunk = None
        for chunk in self.chunks:
            if chunk["index"] == index:
                target_chunk = chunk
                break
        
        # If chunk not found or status is False
        if target_chunk is None:
            return "Searched index does not exist, please reselect."
        elif not target_chunk["status"]:
            return "Searched index has been read, please reselect."
        else:
            return target_chunk

    def get_abstract(self) -> List[Dict]:
        """
        Return all content of self.chunks except body.
        """
        if self.chunks is None:
            return []
        
        abstracts = []
        for chunk in self.chunks:
            # Copy chunk but exclude body field
            abstract = {
                "index": chunk["index"],
                "title": chunk["title"],
                "status": chunk["status"],
                "abstract": chunk["abstract"],
                "comment": chunk["comment"]
            }
            abstracts.append(abstract)
        
        return abstracts
    
    def _split_chunks(self, text: str, fmt: str = "md") -> List[Dict]:
        """
        For Markdown: slice according to "non-subdivisible" principle.
        Rules:
        1. Start from any level heading (# ## ###)
        2. Keep taking until:
        - Next same-level heading or
        - Upper-level heading or
        - End of document
        3. Return list object form: [{index: int, title: str, body: str, status: bool(default: true), abstract: str(default: ""),  comment: str(default: "")},...]
        """
        logger.info("Starting _split_chunks, input length %d characters", len(text))

        if fmt != "md":
            logger.warning("Non-md format, returning whole block")
            return [{"index": 0, "title": "Full Document", "body": text, "status": True, "abstract": "", "comment": ""}]

        # Regex: capture (heading symbol, heading text, body)
        pattern = re.compile(
            r'(^#{1,6})\s+(.+?)\s*\n([\s\S]*?)(?=^\1\s|\Z|^#{1,6}\s)',
            re.MULTILINE
        )
        chunks = []
        for idx, (lev_sym, title, body) in enumerate(pattern.findall(text)):
            chunk_dict = {
                "index": idx,
                "title": title.strip(),
                "body": body.strip(),
                "status": True,
                "abstract": "",
                "comment": ""
            }
            chunks.append(chunk_dict)
            logger.debug("Slice successful -> %s (%d characters)", title.strip(), len(body.strip()))

        if not chunks:
            logger.warning("No headings matched, returning whole")
            return [{"index": 0, "title": "Full Document", "body": text, "status": True, "abstract": "", "comment": ""}]

        logger.info("_split_chunks completed, total %d slices", len(chunks))
        return chunks

    # ---------- LangGraph: Node implementation ----------
    def _node_select_chunk(self, state: ExtractState) -> ExtractState:
        # TOC simplified assembly
        toc = [{"index": c["index"], "title": c["title"], "comment": c["comment"], "status": c["status"]}
            for c in state["chunks"]]

        unread_count, total, unread_indices = _unread_stats(state["chunks"])
        logger.info("【select_chunk】loop=%s last_index=%s unread=%d/%d unread_indices=%s",
                    state["loop"], state["last_index"], unread_count, total,
                    unread_indices[:12] + (["…"] if len(unread_indices) > 12 else []))

        # For convenient observation, print a few TOC title samples
        sample_titles = [(c["index"], _snip(c["title"], 80)) for c in state["chunks"][:8]]
        logger.debug("【select_chunk】TOC sample=%s", sample_titles)

        raw_choice = self.select_chunk_chain.invoke(
            {"read_toc": toc, "last_index": state["last_index"], "last_comment": state["last_comment"]},
            config={"tags": ["select_chunk"], "metadata": {"loop": state["loop"]}},
        )
        logger.info("【select_chunk】llm_raw_choice=%r", _snip(raw_choice, 120))

        try:
            choice = _safe_parse_int(raw_choice)
            logger.info("【select_chunk】parsed_choice=%d", choice)
        except Exception as e:
            logger.warning("【select_chunk】Parse failed: %s -> Sequential fallback", e)
            unread = [c for c in state["chunks"] if c["status"]]
            choice = unread[0]["index"] if unread else -1
            logger.info("【select_chunk】fallback_choice=%d", choice)

        return {"choice": choice}

    def _node_check_stop(self, state: ExtractState) -> ExtractState:
            # Stop conditions
            if state.get("choice", -1) == -1:
                logger.info("【check_stop】Stop: Agent returned -1")
                return {"stop": True}

            unread_count, total, unread_indices = _unread_stats(state["chunks"])
            if unread_count == 0:
                logger.info("【check_stop】Stop: All fragments read (%d/%d)", total, total)
                return {"stop": True}

            if state["loop"] >= state["max_loops"]:
                logger.info("【check_stop】Stop: Reached loop limit loop=%d max_loops=%d",
                            state["loop"], state["max_loops"])
                return {"stop": True}

            # Select fragment
            selected = self.get_chunk(state["choice"])
            if isinstance(selected, str):
                logger.info("【check_stop】Slice unreadable: %s -> Sequential fallback", selected)
                unread = [c for c in state["chunks"] if c["status"]]
                if not unread:
                    logger.info("【check_stop】Stop: No readable fragments to fallback")
                    return {"stop": True}
                selected = self.get_chunk(unread[0]["index"])
                if isinstance(selected, str):
                    logger.info("【check_stop】Stop: Still unreadable after fallback")
                    return {"stop": True}

            logger.info("【check_stop】Continue: selected index=%d title=%s body_len=%d",
                        selected["index"], _snip(selected["title"], 120), len(selected.get("body", "")))
            logger.debug("【check_stop】body_snippet=%s", _snip(selected.get("body", ""), 300))
            return {"selected": selected, "stop": False}

    def _node_read_chunk(self, state: ExtractState) -> ExtractState:
        sel = state["selected"]
        logger.info("【read_chunk】Start reading index=%d title=%s body_len=%d",
                    sel["index"], _snip(sel["title"], 120), len(sel.get("body", "")))

        raw_read = self.read_chunk_chain.invoke(
            {"current_index": sel["index"], "current_title": sel["title"], "read_text": sel["body"]},
            config={"tags": ["read_chunk"], "metadata": {"index": sel["index"], "title": sel["title"]}},
        )
        logger.debug("【read_chunk】llm_raw_output=%s", _snip(raw_read, 600))

        read_dict = _parse_read_json(raw_read)
        abstract_len = len(read_dict.get("abstract", "") or "")
        comment_len  = len(read_dict.get("comment", "") or "")
        logger.info("【read_chunk】parsed: abstract_len=%d comment_len=%d", abstract_len, comment_len)
        logger.info("【comment】comment: %s", read_dict.get("comment", "") or "")
        if abstract_len == 0:
            logger.info("【read_chunk】Notice: No effective abstract extracted from this fragment (empty string)")

        # Write back and mark as read
        before_unread, total, _ = _unread_stats(state["chunks"])
        for c in state["chunks"]:
            if c["index"] == sel["index"]:
                c["abstract"] = read_dict["abstract"]
                c["comment"]  = read_dict["comment"]
                c["status"]   = False
                break
        after_unread, _, _ = _unread_stats(state["chunks"])
        logger.info("【read_chunk】Writeback completed: unread %d -> %d (this fragment marked as read)",
                    before_unread, after_unread)

        return {
            "chunks": state["chunks"],
            "last_index": sel["index"],
            "last_comment": read_dict["comment"],
            "loop": state["loop"] + 1,
        }

    def _node_final_extract(self, state: ExtractState) -> ExtractState:
        # Assemble abstracts
        abstracts = [{
            "index": c["index"],
            "title": c["title"],
            "status": c["status"],
            "abstract": c["abstract"],
            "comment": c["comment"],
        } for c in state["chunks"]]

        non_empty = [a for a in abstracts if (a.get("abstract") or "").strip()]
        logger.info("【final_extraction】Total abstracts=%d, Non-empty abstracts=%d, Sample indices=%s",
                    len(abstracts), len(non_empty),
                    [a["index"] for a in non_empty[:10]])

        project_schema = self.parser.get_toon_instructions()
        abstracts = [item["abstract"] for item in non_empty]
        project: WBSRoot = self.final_extraction_chain.invoke(
            {"abstracts": non_empty, "project_schema": project_schema},
            config={"tags": ["final_extraction"],
                    "metadata": {"total_chunks": len(state["chunks"]), "loops": state["loop"]}},
        )

        # Print result size and fragments (avoid full output)
        try:
            proj_json = project.model_dump_json()
            logger.info("【final_extraction】Result size=%d characters", len(proj_json))
        except Exception as e:
            logger.warning("【final_extraction】Result printing failed: %s", e)

        return {"project": project}
    
    # ---------- LangGraph: Build graph ----------
    def _build_graph(self):
        graph = StateGraph(ExtractState)

        graph.add_node("select_chunk", self._node_select_chunk)
        graph.add_node("check_stop", self._node_check_stop)
        graph.add_node("read_chunk", self._node_read_chunk)
        graph.add_node("final_extract", self._node_final_extract)

        graph.add_edge(START, "select_chunk")
        graph.add_edge("select_chunk", "check_stop")

        # Conditional edge: Jump based on stop True/False
        def route_after_check(state: ExtractState):
            return "final_extract" if state.get("stop") else "read_chunk"

        graph.add_conditional_edges("check_stop", route_after_check, {"final_extract": "final_extract", "read_chunk": "read_chunk"})
        graph.add_edge("read_chunk", "select_chunk")
        graph.add_edge("final_extract", END)

        return graph.compile()

    # ---------- LangGraph: Run graph ----------
    def _run_graph(self, chunks: List[Dict]) -> WBSRoot:
        init_state: ExtractState = {
            "last_index": -1,
            "last_comment": "",
            "loop": 0,
            "max_loops": max(1, len(chunks)),
            "chunks": chunks,
        }

        # Estimate steps: 3 steps per round + 1 final step, plus redundancy
        expect_steps = 3 * init_state["max_loops"] + 5
        recursion_limit = max(50, int(expect_steps * 1.2))

        final_state = self.graph.invoke(
            init_state,
            config={
                "tags": ["extract_graph"],
                "recursion_limit": recursion_limit,
            },
        )
        project: WBSRoot = final_state.get("project")
        if not isinstance(project, WBSRoot):
            raise ValueError("Final extraction did not return WBSRoot object")
        return project

    # ----------------------------------------
    # Safe save function (always try to return path)
    # ----------------------------------------

    def _save_result(
        self,
        result,                              # Pydantic BaseModel or any object
        output_dir: Union[str, Path] = "outputs",
        filename: Optional[str] = None
    ) -> Path:
        """
        Safely save result as UTF-8 JSON (Chinese not escaped, indented 2).
        - Atomic write to avoid partial writes causing corruption
        - Even if serialization fails, generate .error.json with error info
        - Always try to return a usable Path
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Auto naming: wbs_YYYYmmdd_HHMMSS.json
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"wbs_{ts}.json"
        filename = _sanitize_filename(filename)
        out_path = out_dir / (filename or f"wbs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        # 1) Prioritize using pydantic's own JSON export
        try:
            if hasattr(result, "model_dump_json"):  # pydantic v2
                try:
                    payload = result.model_dump_json(indent=2, ensure_ascii=False)  # type: ignore[attr-defined]
                except TypeError:
                    # Some versions lack ensure_ascii parameter
                    payload = result.model_dump_json(indent=2)  # type: ignore[attr-defined]
                _write_atomic(out_path, payload)
                logger.info("Result saved: %s (%d bytes)", str(out_path), len(payload.encode("utf-8")))
                return out_path
            elif hasattr(result, "json"):  # pydantic v1
                payload = result.json(ensure_ascii=False, indent=2)
                _write_atomic(out_path, payload)
                logger.info("Result saved: %s (%d bytes)", str(out_path), len(payload.encode("utf-8")))
                return out_path
        except Exception as e:
            logger.warning("Direct JSON export failed, will try loose serialization: %s", e)

        # 2) Loose serialization: Try to convert dict -> dumps
        try:
            data = _coerce_to_mapping(result)
            payload = _json_dumps_safely(data)
            _write_atomic(out_path, payload)
            logger.info("Result saved (loose serialization): %s (%d bytes)", str(out_path), len(payload.encode("utf-8")))
            return out_path
        except Exception as e2:
            logger.exception("Loose serialization save failed: %s", e2)

        # 3) Final fallback: Save error description file .error.json
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            err_name = _ensure_json_suffix((Path(filename).stem if filename else "wbs") + f".{ts}.error")
            err_path = out_dir / err_name
            fallback = {
                "_fallback": True,
                "_error": "Save failed (original result could not be serialized)",
                "_type": type(result).__name__,
                "_str": str(result)[:4000] if result is not None else "None",
            }
            payload = _json_dumps_safely(fallback)
            _write_atomic(err_path, payload)
            logger.error("Result save failed, error file output: %s", str(err_path))
            return err_path
        except Exception:
            # 4) Fallback of fallback: Try to return target out_path (may not be written), avoid upper crash
            logger.error("Error file also could not be written, returning expected path: %s", str(out_path))
            return out_path
    
    # ----------------------------------------
    # Recommended call in extract (maintain "must return")
    # ----------------------------------------
    def extract(self,
                source: Union[str, Path, None] = None,
                text: str = "",
                output_dir: str="static/extraction_cache") -> "WBSRoot":
        logger.info("===== Starting extract =====")
        if source and text:
            raise ValueError("Please choose only one input method")

        # 1. Get full text
        if source:
            src_path = Path(source).resolve()
            logger.info("Reading file: %s", src_path)
            self.content = self._load_document(source)
        else:
            logger.info("Using passed text, length %d characters", len(text))
            self.content = text

        default_name = None
        if source:
            try:
                default_name = f"{Path(source).stem}_wbs_raw.json"
            except Exception:
                default_name = None

        try:
            # 2. Short text: Direct final extraction
            if len(self.content) < 50000:
                logger.info("Short text mode: Direct final extraction")
                abstracts = [{
                    "index": 0,
                    "title": "Full Document",
                    "status": False,
                    "abstract": self.content,
                    "comment": "Short text direct extraction, no slicing performed."
                }]
                project_schema = self.parser.get_toon_instructions()

                result: WBSRoot = self.final_extraction_chain.invoke(
                    {"abstracts": abstracts, "project_schema": project_schema},
                    config={"tags": ["final_extraction", "short_document"]},
                )
                self._save_result(result, output_dir=output_dir, filename=default_name)
                return result

            # 3. Long text: Slice + LangGraph cycle extraction
            self.chunks = self._split_chunks(self.content, fmt="md")
            result: WBSRoot = self._run_graph(self.chunks)
            self._save_result(result, output_dir=output_dir, filename=default_name)
            return result

        except Exception as e:
            logger.exception("Extract execution failed, will return fallback result: %s", e)
            # Construct a minimal usable fallback structure to avoid upper crash
            fallback: Dict[str, Any] = {
                "level": "construction_project",
                "name": "Unnamed Project",
                "description": f"Extraction failed: {str(e)}",
                "children": []
            }
            # Save fallback result to .error.json
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            err_name = (Path(default_name).stem if default_name else "wbs") + f".{ts}.error.json"
            self._save_result(fallback, output_dir=output_dir, filename=err_name)
            # Also return fallback object (if WBSRoot is pydantic, can do construction here)
            try:
                return _safe_build_model(WBSRoot, fallback, partial=True)
            except Exception:
                # Cannot hang even if failed
                return fallback