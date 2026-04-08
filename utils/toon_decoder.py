from typing import Any, Dict, List, Optional


# =======================================================
# Options
# =======================================================
class DecodeOptions:
    """
    Options for the TOON decoder.
    strict = False  → more tolerant parsing.
    """
    def __init__(self, strict: bool = False):
        self.strict = strict


class ToonDecodeError(Exception):
    """Custom exception for TOON parsing errors."""
    pass


# =======================================================
# Public API
# =======================================================
def toon_decode(input_str: str, options: Optional[DecodeOptions] = None) -> Dict[str, Any]:
    if options is None:
        options = DecodeOptions()

    input_str = input_str.strip()

    if (
        (input_str.startswith("'") and input_str.endswith("'")) or
        (input_str.startswith('"') and input_str.endswith('"'))
    ):
        input_str = input_str[1:-1]

    if "\\n" in input_str:
        input_str = input_str.replace("\\n", "\n")

    input_str = input_str.replace('\\"', '"')

    lines = _preprocess_lines(input_str)
    result, _ = _parse_object(lines, 0, 0, options)
    return result



# =======================================================
# Preprocessing
# =======================================================
def _preprocess_lines(text: str) -> List[str]:
    """
    Remove empty lines and ignore comment lines ("# ..."),
    but preserve indentation and meaningful content.
    Additionally, handle malformed lines with special characters and fix common formatting issues.
    """
    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        ln = lines[i]
        # Handle potential carriage return characters
        ln = ln.replace('\r', '')
        stripped = ln.strip()

        if stripped == "":
            i += 1
            continue

        # FIX: Ignore comment lines beginning with '#'
        if stripped.startswith("#"):
            i += 1
            continue

        # Check if this line ends with a comma, which might indicate a multi-line entry
        if ln.rstrip().endswith(","):
            # Look ahead for the next non-empty line to combine with
            j = i + 1
            while j < len(lines):
                next_line = lines[j].replace('\r', '').replace('\n', ' ').strip()
                if next_line != "":
                    # Combine the current line with the next line
                    ln = ln.rstrip() + " " + next_line
                    i = j + 1  # Skip the next line since we've combined it
                    # Check if the new combined line still ends with comma, if so continue combining
                    if ln.rstrip().endswith(","):
                        continue  # Continue to look for more continuation lines
                    else:
                        break
                j += 1
            else:
                # If we reach the end without finding a non-empty line, just continue with current
                result.append(ln.rstrip("\n\r"))
                i += 1
        else:
            result.append(ln.rstrip("\n\r"))
            i += 1
    return result


def _indent_level(line: str) -> int:
    """Return number of leading spaces."""
    return len(line) - len(line.lstrip(" "))


def _parse_value(val: str) -> Any:
    """
    Parse primitive values:
    - quoted strings
    - int / float
    - raw string fallback
    """
    val = val.strip()

    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]

    try:
        if "." in val:
            return float(val)
        return int(val)
    except Exception:
        return val


# =======================================================
# Object Parsing
# =======================================================

def _parse_object(
    lines: List[str],
    idx: int,
    depth: int,
    options: DecodeOptions,
):
    """
    Parse a TOON object section with enhanced error handling for malformed lines.

    depth = expected indentation of this object.
    """
    obj: Dict[str, Any] = {}
    i = idx

    while i < len(lines):
        line = lines[i]
        indent = _indent_level(line)

        # Object ends when indentation drops below current level
        if indent < depth:
            break

        content = line.strip()

        # Handle potential malformed content that starts with numbers or special characters
        # This could be a result of parsing errors, so we try to handle it gracefully
        if not (content.startswith("#") or ":" in content or ("[" in content and content.endswith(":"))):
            # This might be a malformed line that should be part of description or value
            if options.strict:
                raise ToonDecodeError(f"Invalid TOON line at depth {depth}: {line}")
            else:
                # Check if this is part of a multi-line description that was split
                # Try to identify if this looks like a continuation of a description
                if i > 0 and i < len(lines):
                    prev_line = lines[i-1] if i > 0 else ""
                    if prev_line.strip().endswith(","):  # Previous line ended with a comma
                        # This is likely a continuation, we'll skip it for now as it should be handled during preprocessing
                        i += 1
                        continue
                    else:
                        # Log the error and skip the line, or try to incorporate it into previous field
                        print(f"Warning: Invalid TOON line skipped at depth {depth}: {line}")
                        i += 1
                        continue

        # --------------------------------------------------
        # Array header: children[n]: or children[n]{a,b,c}:
        # --------------------------------------------------
        if "[" in content and content.endswith(":"):
            key, expected_len, fields = _parse_array_header(content)

            # FIX: dynamically detect real indent of array items
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            array_base_indent = _indent_level(lines[j]) if j < len(lines) else indent + 2

            arr, next_i = _parse_array(lines, i + 1, array_base_indent, fields, options)

            # Auto-merge multiple children[n] sections
            if key in obj:
                if isinstance(obj[key], list):
                    obj[key].extend(arr)
                else:
                    raise ToonDecodeError(f"Key '{key}' already exists and is not a list")
            else:
                obj[key] = arr

            i = next_i
            continue

        # --------------------------------------------------
        # Regular key: value
        # --------------------------------------------------
        if ":" in content:
            key, val = content.split(":", 1)
            key = key.strip()
            val = val.strip()

            # Nested object starts when value is empty
            if val == "":
                # FIX: use current line indent as parent baseline
                nested, next_i = _parse_object(lines, i + 1, indent + 2, options)
                obj[key] = nested
                i = next_i
            else:
                obj[key] = _parse_value(val)
                i += 1
            continue

        # Not valid at this indentation - but we handle this more gracefully now
        if options.strict:
            raise ToonDecodeError(f"Invalid TOON line at depth {depth}: {line}")
        else:
            print(f"Warning: Invalid TOON line skipped at depth {depth}: {line}")
            i += 1

    return obj, i



def _parse_array(
    lines: List[str],
    idx: int,
    depth: int,
    fields: Optional[List[str]],
    options: DecodeOptions,
):
    """
    Parse arrays including:
      • Mixed object arrays ("- level: xxx", ...)
      • Tabular arrays (e.g., sub_item_work,...,...,unit,qty)

    depth = expected indentation for array items.
    """
    arr: List[Any] = []
    i = idx

    while i < len(lines):
        line = lines[i]
        indent = _indent_level(line)

        # End array when indentation drops below expected level
        if indent < depth:
            break

        # FIX: deeper indentation should not break array, just skip line
        if indent > depth:
            i += 1
            continue

        stripped = line.strip()

        # ------------------------------------------------------
        # Tabular row (if fields are defined and not "- ")
        # ------------------------------------------------------
        if fields and not stripped.startswith("- "):
            item = _parse_tabular_row(stripped, fields, options)
            arr.append(item)
            i += 1
            continue

        # ------------------------------------------------------
        # Mixed object row: "- key: value"
        # ------------------------------------------------------
        if stripped.startswith("- "):
            entry = stripped[2:].strip()

            # Case 1: "- k: v"
            if ":" in entry:
                first_key, first_val = entry.split(":", 1)
                first_key = first_key.strip()
                first_val = first_val.strip()

                obj_item: Dict[str, Any] = {first_key: _parse_value(first_val)}

                i += 1

                # Parse additional fields of this list item
                while i < len(lines):
                    line2 = lines[i]
                    indent2 = _indent_level(line2)

                    # Stop if indentation returns to array level
                    if indent2 <= depth:
                        break

                    content2 = line2.strip()

                    # Sub-array inside list item
                    if "[" in content2 and content2.endswith(":"):
                        sub_key, _, sub_fields = _parse_array_header(content2)
                        sub_arr, next_i = _parse_array(lines, i + 1, indent2 + 2, sub_fields, options)

                        if sub_key in obj_item:
                            obj_item[sub_key].extend(sub_arr)
                        else:
                            obj_item[sub_key] = sub_arr

                        i = next_i
                        continue

                    # Regular key: value
                    if ":" in content2:
                        k2, v2 = content2.split(":", 1)
                        k2 = k2.strip()
                        v2 = v2.strip()

                        if v2 == "":
                            nested2, next_i = _parse_object(lines, i + 1, indent2 + 2, options)
                            obj_item[k2] = nested2
                            i = next_i
                        else:
                            obj_item[k2] = _parse_value(v2)
                            i += 1
                        continue

                    # End of this list-item block
                    break

                arr.append(obj_item)
                continue

            # Case 2: "- primitive"
            arr.append(_parse_value(entry))
            i += 1
            continue

        # No valid array item found - try to handle malformed content gracefully
        if options.strict:
            raise ToonDecodeError(f"Invalid array item at depth {depth}: {line}")
        else:
            # Attempt to handle malformed lines that might contain useful data
            # This could be a continuation of a description or value
            print(f"Warning: Invalid array item skipped at depth {depth}: {line}")
            i += 1

    return arr, i


# =======================================================
# Tabular Row Parsing
# =======================================================
def _parse_tabular_row(line: str, fields: List[str], options: DecodeOptions) -> Dict[str, Any]:
    """
    Parse tabular rows for sub_item_work entries with enhanced error handling for malformed data.
    Format example:
        sub_item_work,Name,"Description with commas, and stuff",m3,123.45

    Steps:
      1) Extract level (leftmost)
      2) Extract name
      3) Extract unit + quantity from rightmost
      4) Remaining = description
    """
    # Clean the line from potential carriage returns and other special characters
    line = line.replace('\r', '').strip()
    
    # Special 5-field format for sub_item_work
    if fields == ["level", "name", "description", "unit", "quantity"]:
        # Handle lines that might contain newlines or special characters in the description part
        # Replace newlines with spaces to keep the line as a single unit
        line = line.replace('\n', ' ').replace('\r', ' ')
        
        # Try to handle quoted values that might contain commas
        # This is a simple state machine to handle quoted values
        parts = []
        current_part = ""
        in_quotes = False
        i = 0
        while i < len(line):
            char = line[i]
            if char == '"':
                in_quotes = not in_quotes
                current_part += char
            elif char == ',' and not in_quotes:
                parts.append(current_part.strip())
                current_part = ""
            else:
                current_part += char
            i += 1
        if current_part:
            parts.append(current_part.strip())
        
        # Clean up quotes from parts
        parts = [_parse_value(part) for part in parts]
        
        # Now try to parse the parts according to the expected format
        if len(parts) >= 5:
            # If we have more than 5 parts, assume the middle parts are part of the description
            level_part = parts[0]
            name_part = parts[1]
            desc_part = " ".join(parts[2:-2]) if len(parts) > 4 else parts[2]
            unit_part = parts[-2] if len(parts) >= 4 else ""
            qty_part = parts[-1] if len(parts) >= 5 else ""
        else:
            # If we don't have enough parts, use fallback
            return _tabular_fallback(line, fields, options)

        # Parse quantity, handling empty or invalid values
        quantity_value = qty_part.strip() if qty_part else ""
        if quantity_value == "" or quantity_value is None:
            parsed_quantity = 0
        else:
            try:
                # Check if it contains a decimal point to decide int or float
                if "." in str(quantity_value):
                    parsed_quantity = float(quantity_value)
                else:
                    parsed_quantity = int(quantity_value)
            except ValueError:
                # If conversion fails, default to 0
                parsed_quantity = 0

        return {
            "level": level_part,
            "name": name_part,
            "description": desc_part,
            "unit": unit_part,
            "quantity": parsed_quantity,
        }

    # Generic fallback for other tabular formats
    parts = [x.strip() for x in line.split(",")]
    if options.strict and len(parts) != len(fields):
        raise ToonDecodeError(f"Tabular row mismatch: {line}")

    parts = (parts + [""] * len(fields))[:len(fields)]
    return {fields[i]: _parse_value(parts[i]) for i in range(len(fields))}


def _tabular_fallback(line: str, fields: List[str], options: DecodeOptions):
    """Fallback behavior when tabular parsing fails."""
    if options.strict:
        raise ToonDecodeError(f"Invalid tabular row: {line}")

    parts = [x.strip() for x in line.split(",")]
    parts = (parts + [""] * len(fields))[:len(fields)]
    result = {}
    for i in range(len(fields)):
        field_name = fields[i]
        field_value = parts[i]
        
        # Handle special case for quantity field - ensure it's a number
        if field_name == "quantity":
            if field_value == "" or field_value is None:
                result[field_name] = 0
            else:
                try:
                    # Check if it contains a decimal point to decide int or float
                    if "." in field_value:
                        result[field_name] = float(field_value)
                    else:
                        result[field_name] = int(field_value)
                except ValueError:
                    # If conversion fails, default to 0
                    result[field_name] = 0
        else:
            result[field_name] = _parse_value(field_value)
    
    return result


# =======================================================
# Array Header Parsing
# =======================================================
def _parse_array_header(content: str):
    """
    Parse headers of the form:
        children[6]{a,b,c}:
        children[1]:

    Returns:
        (key, expected_length, field_list_or_None)
    """
    key = content.split("[", 1)[0].strip()

    inside = content[content.find("[") + 1 : content.find("]")]
    expected_len = int(inside) if inside.isdigit() else 0

    fields = None
    if "{" in content and "}" in content:
        brace = content[content.find("{") + 1 : content.find("}")]
        fields = [x.strip() for x in brace.split(",")]

    return key, expected_len, fields
