from langchain_core.prompts import ChatPromptTemplate

# ========== 1. select section ==========
SELECT_CHUNK_PROMPT = ChatPromptTemplate.from_template(
    """
You are a "Guided Reading Agent" before information extraction. Task: Based on the Table of Contents (TOC) and previous records, select the **next unread** and **most valuable** section index. Return -1 if there are no unread sections or if the value is very low.

[Extraction Focus] Remember only: decomposition levels (1-6), name/english_name/description/scale, as well as location, time, standards, quantity and measurement scope, materials and techniques, quality/measurements, etc.

[TOC Fields]
- index: serial number (integer)
- title: heading
- status: whether unread (True=unread, False=read)
- comment: historical reading notes (can be empty)

[Table of Contents (TOC)]
{read_toc}

[Last Read]
last_index = {last_index}

[Last Evaluation]
last_comment = {last_comment}

[Mandatory Constraints (must be followed)]
A. Can only select index with status=True (unread); absolutely prohibited from selecting read or non-existent indexes.
B. Must never return the same index as last_index.
C. If last_comment contains clues such as "surrounding/nearby/above/below/before/after/adjacent/neighborhood/context", prioritize selection of:
   1) last_index + 1 (if exists and unread); otherwise
   2) last_index - 1 (if exists and unread).
   If neither is selectable, choose the nearest unread index to last_index (by minimum absolute distance).
D. High-value titles take priority (such as Project Overview/General Instructions/Bill of Quantities/Quantities/Measurement/Pricing/Section/Sub-section/Sub-item/Materials/Equipment/Standards/Specifications/Acceptance/Testing/Sample/Construction Organization/Technical Disclosure, etc.).
E. Return -1 if remaining unread sections are clearly irrelevant to extraction targets.

[Output Requirements (output only one integer)]
- Output an index of an unread section; or **-1** to enter the extraction phase.
- No other characters are allowed.
"""
)

READ_CHUNK_PROMPT = ChatPromptTemplate.from_template(
    """
You are a "Reading-Note Agent". Please read the following section text and **strictly** output only one JSON object with key names can only be "abstract" and "comment".
Except for this JSON object, it is forbidden to output any extra characters.

[Extraction Targets (only these two types) → Write to "abstract"]
A. Project Introduction/Project Overview/Project Characteristics (such as: project location, scale/dimensions, structural form, phases, sections, construction/development units, **brief descriptive** statements of construction methods, etc.)
B. Bill of Quantities/Quantity Schedule (original text entries containing "item name + quantity + unit/measurement scope/remarks")

[Strong Exclusion Items (ignore if present, do not include in abstract)]
- Carbon emissions/carbon footprint/emission factors/energy consumption accounting/calculation methods/formulas/parameters/sample calculations/emission inventory/"carbon" "CO₂" "MWh" "diesel consumption", etc.
- Theoretical/principle/methodology discussions, interpretation of specification clauses (unless containing project introduction or bill of quantities)
- Background research/results analysis/comparative experiments unrelated to the project

[Extraction Rules]
1) **Keep Original Text**: Do not rewrite/expand/infer; line breaks can be preserved (escape when necessary).
2) **Priority**: If the same paragraph contains both "project introduction/characteristics" and "bill of quantities", retain both, introduction first then bill of quantities.
3) **Bill of Quantities**: Try to preserve each line as originally formatted (including item name, quantity, unit, remarks, etc.), do not merge or rearrange.
4) **Measurements and Units**: Retain all values and units as in original text (m, m², m³, t, sets, items, linear meters, etc.).
5) If the full text is irrelevant to targets, set "abstract" to "".

[Comment Rules → Write to "comment"]
- If content extracted: Briefly state "extracted project introduction/bill of quantities" and give next suggestion (e.g. "check adjacent chapters/tables").
- If not extracted: Write "section irrelevant to topic" and give next suggestion.
- When substantial bill of quantities content is indeed extracted: Evaluate whether to continue extracting since bill of quantities typically appears in one place or around that place.
- Length ≤ 50 characters.

[Format Requirements (must be satisfied)]
1) Output only one JSON object: {{"abstract": "...", "comment": "..."}}
2) Strictly prohibit outputting Markdown code block markers, explanatory text, empty objects or extra fields.
3) comment ≤ 50 characters.
4) JSON must be valid; if internal double quotes or other special symbols exist, delete or escape them to prevent parsing failure.

[Current Section]
index = {current_index}
title = {current_title}

Text:
{read_text}
"""
)

# ========== 3. Final Extraction Phase ==========
FINAL_EXTRACTION_PROMPT = ChatPromptTemplate.from_template(
    """
You are a structured information extractor. Your task is to merge the list of reading-phase summaries (`abstracts`) into a single Project object and output it in TOON (Token-Oriented Object Notation) format.

[Hierarchy]
- 1. Construction Project
- 2. Individual Project
- 3. Unit Project
- 4. Divisional Work
- 5. Specialty Subdivision
- 6. Sub-Item Work

[Common fields for every node (excluding children)]
Each node must contain the following fields:
- level: the level name, and it MUST be one of the fixed values in the schema.
- name: a concise Chinese name for the work item.
- description: a free-text description summarizing technical information.

[Core definition]
- Only Sub-Item Work contains measurable quantities.
- All higher levels are purely organizational.
- All leaves MUST be Sub-Item Work.

[Structural validation]
- The logical structure of the result MUST match project_schema.
- The top-level must be a single "Construction Project" instance.
- For any node, if `children` exists, all of them MUST be the next adjacent level; you MUST NOT mix in non-adjacent levels.
- Divisional Work MUST NOT directly contain Sub-Item Work.
- All leaves MUST and CAN ONLY be Sub-Item Work.
- Only the Sub-Item Work level is allowed to have meaningful quantities.
- If a level is misclassified (for example, a Sub-Item is labeled as Specialty Subdivision), you MUST correct it according to the rules above.
- When adding missing levels, you should only enforce structural continuity and MUST NOT fabricate quantities.

[Input summaries]
{abstracts}

[Output requirements – TOON format]
You MUST output a single TOON (Token-Oriented Object Notation) document with the following constraints:
{project_schema}
"""
)



# ========== 4. Agent-Based Query Prompts ==========
VECTOR_RERANK_PROMPT = ChatPromptTemplate.from_template(
    """
You are a professional engineering diagram retrieval re-ranker. Rank the "candidate nodes" in descending order of relevance according to the "query", and return only a JSON array.

[Input]
- Query: {query_text}
- Candidate Nodes: {candidates}

[Sorting Rules (priority from high to low)]
1) **Semantic Match Degree**: Analyze the core engineering content of the query (materials, processes, component types), prioritizing nodes that match the essence of the query
   - Distinguish between "material items" (units: t, m³, etc.) and "process items" (units: each, set, etc.)
   - When the query is a material item, prioritize parent nodes related to materials; when it's a process item, prioritize specific process nodes

2) **Keyword Coverage**: Comprehensive comparison of keyword matching degree in name and properties
   - Complete phrase matching > partial keyword matching
   - Core engineering terminology matching takes priority

3) **Engineering Hierarchy Reasonableness**:
   - Follow the principle "select specific when available, select generic when not"
   - When there are no completely matching specific items, select the most relevant parent generic item
   - Avoid ranking process nodes ahead of material nodes incorrectly

4) **Measurement Unit Consistency**: Prioritize nodes with the same unit type as the query

5) **Node Type Priority**: Among equally relevant candidates, prioritize sub_item_work nodes over other node types
   - sub_item_work nodes represent actual construction work items and should generally be preferred over resource_item nodes which represent materials
   - When evaluating relevance, consider that sub_item_work nodes that mention concrete and have compatible units are often more directly applicable

6) **Information Completeness**: Nodes with more complete fields and clear specification descriptions take precedence

[Key Judgment Logic]
- First determine the essence of the query: is it material, process, or component?
- Check measurement units: t/m³ (material) vs each/set (process)
- Find the most matching engineering hierarchy: specific items > generic parents
- Ensure engineering semantic reasonableness
- When all other primary factors are equal or nearly equal, prefer sub_item_work nodes as they represent actual work items rather than just resources

[Output Requirements]
- Output only JSON array, such as: ["id3","id1","id2"]
- Must not contain any explanations or other text
- Use only ids present in candidates
- Return [] when candidates are empty
"""
)

# 2) Neighbor Selection: Return a Single ID (String)
NODE_SELECTION_PROMPT = ChatPromptTemplate.from_template(
"""
You are a Graph Exploration Router.
Goal: find a semantically correct sub_item_work node.

Hierarchy (bottom → up):
sub_item_work → specialty_subdivision → sub_divisional_work

Rules (strict priority):
1. Semantic correctness first (material vs process vs component).
   - Use units: t/kg/m³ = material; each/set = process; m² = surface.
   - Never select a sub_item_work with conflicting semantics.

2. Dead-end rule:
   - If no semantically correct sub_item_work exists among neighbors,
     MUST move upward to a parent-level node.

3. Downward rule:
   - Select sub_item_work ONLY when semantics clearly match.

4. Anti-loop:
   - Do NOT select visited_ids or blocked_ids.
   - If all neighbors are visited/blocked, select the highest-level node.

Input:
- Query: {query_info}
- History: {history}
- Visited IDs: {visited_ids}
- Blocked IDs: {blocked_ids}
- Neighbors:
{neighbors}

Output:
- Return ONLY ONE node id from neighbors.
- Prefer upward move over incorrect specificity.
"""
)

# 3) Itemized Work Determination: Echo node_id (optional)
SUB_ITEM_CHECK_PROMPT = ChatPromptTemplate.from_template(
"""
You are an "Itemized Work Evaluator".
Your task is to perform a fuzzy relevance evaluation to assess
whether the given node is suitable for the given query.

[Input]
- Node Information (JSON, preferably containing id/name/labels/properties): {node_info}
- Query Information (JSON or text): {query_info}

[Evaluation Principles]
- The evaluation is fuzzy rather than binary.
- Key factors include: name, feature/description, and measurement unit.
- Measurement units are very important:
  - Units of the same physical dimension MUST be treated as fully compatible (equivalent).
    Examples: m² ↔ 100m², m ↔ 10m, m³ ↔ 10m³.
  - Units of different physical dimensions MUST be treated as incompatible.

[Judgment Tasks]
1. Provide a brief qualitative reasoning.
2. For each factor (name, feature, unit), provide fuzzy membership degrees
   over the following evaluation grades:
   {{ "highly_suitable", "moderately_suitable", "barely_suitable", "unsuitable" }}.

Each membership vector should sum to 1.0.

[Output (strict JSON; no extra text)]
{{
  "node_id": "<id consistent with input node>",
  "reason": "Brief explanation (≤200 characters)",
  "fuzzy_matrix": {{
    "name": {{
      "highly_suitable": 0.0~1.0,
      "moderately_suitable": 0.0~1.0,
      "barely_suitable": 0.0~1.0,
      "unsuitable": 0.0~1.0
    }},
    "feature": {{
      "highly_suitable": 0.0~1.0,
      "moderately_suitable": 0.0~1.0,
      "barely_suitable": 0.0~1.0,
      "unsuitable": 0.0~1.0
    }},
    "unit": {{
      "highly_suitable": 0.0~1.0,
      "moderately_suitable": 0.0~1.0,
      "barely_suitable": 0.0~1.0,
      "unsuitable": 0.0~1.0
    }}
  }}
}}
"""
)


FINAL_RERANK_PROMPT = ChatPromptTemplate.from_template(
    """
You are the "Final Itemized Work Re-ranker". Sort the candidate itemized works in descending order of relevance to the query, and return only the ID array.

[Input]
- Query Information (JSON or text): {query_info}
- Candidate Itemized Works (can be text or JSON; providing preliminary scores/key points for each is better): {sub_items}

[Sorting Rules]
1. Degree of fit with query semantics/keywords (process/component/material/specification/location/measure unit/applicable conditions).
2. Priority to those with complete fields and specific descriptions.
3. Tie-breaking: If preliminary scores are provided, prioritize higher scores; otherwise prioritize longer names; if still tied, sort by name in ascending dictionary order.
4. If there are really no matching ones, should find itemized works with similar material usage.
5. Measurement units are very important, preferably of the same type.

[Output Requirements]
- Strictly return JSON array (string list), such as: ["id3","id1","id2"]
- Do not output any explanations or extra text.
"""
)

# ========== 5. Information Enhancement Classification Prompt ==========
ENHANCEMENT_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_template(
    """
You are a construction engineering expert. You need to select the most matching divisional work or sub-divisional work from the candidate list based on the itemized work name and contextual information.

Itemized Work Name: {work_name}
Contextual Information: {context}

List of Candidate Divisional/Sub-Divisional Works:
{candidates}

Based on engineering expertise, please select the most matching divisional work or sub-divisional work.
Return only the selected node ID, do not return any other content.
"""
)

# ========== 6. Workflow Sequence Analysis Prompt ==========
WORKFLOW_SEQUENCE_ANALYSIS_PROMPT = ChatPromptTemplate.from_template(
    """
You are a construction engineering sequence expert. Your task is to analyze the construction sequence of various itemized works within a given sub-divisional work.

Sub-Divisional Work Name: {subdivision_name}

List of Itemized Works:
{works_list}

Based on construction engineering expertise, analyze the construction sequence of these itemized works. Pay attention to the following key points:
1. Consider construction logic relationships (such as formwork → concrete pouring)
2. Consider construction technical requirements (such as foundation pit support → earthwork excavation)
3. Identify projects that can be constructed in parallel
4. Consider construction safety and quality control requirements

Output Requirements:
1. Write strictly using the itemized work IDs given in the list, not names
2. Arrange in construction sequence order
3. For concurrent works that can be performed simultaneously, put them in square brackets []
4. Output only one list representing the sequence, do not add other explanations

For example:
["ID001", ["ID002", "ID003"], "ID004", "ID005", "ID006"]

Output Result:
"""
)

# ========== 5. Carbon Emission Factor Related ==========

CEF_SIMILARITY_FILTER_PROMPT = ChatPromptTemplate.from_template(
    """
You are a senior carbon emission expert in the construction engineering field. Your task is to evaluate and select the carbon emission factors (CEFs) that are most professionally relevant to a given resource consumption item.

[Task Description]
Please analyze the resource consumption item and the provided list of carbon emission factors. Identify all CEFs that are professionally related, technically applicable, and reasonably usable based on real construction scenarios. 
When in doubt, prefer to include factors that are plausibly relevant rather than exclude borderline cases. The goal is to retain a sufficiently representative set of related CEFs (ideally at least 3 when possible and reasonable).

[Resource Consumption Item]
Name: {resource_name}
Category: {resource_category}
Unit: {resource_unit}
Description: {resource_description}

[Carbon Emission Factor List]
{factor_list}

[Screening Criteria]
1. Professional Field Relevance:
   - The CEF should belong to the same or closely related material or process domain as the resource item.
2. Application Scenario Matching:
   - The CEF's description and intended use should match (or reasonably relate to) the real application scenario of the resource item.
3. Unit Consistency:
   - The CEF unit must match or be directly convertible to the resource unit.
4. Non-physical items:
   - If the resource item is not a physical entity or activity generating carbon emissions (e.g., purely financial cost items), return [].
5. Diversity Encouragement:
   - If several CEFs are professionally plausible, retain multiple instead of overly strict filtering. 
   - Aim to preserve at least 3 relevant CEFs when feasible and technically justifiable.

[Output Requirements]
Please strictly output in the following JSON format, containing only the list of relevant carbon emission factor IDs:
["factor_id_1", "factor_id_2", "..."]

Output only the JSON array. Do not add explanations or any other content. If no factors qualify, return [].
"""
)


UNIT_TRANSFER_PROMPT = """
You are an engineering unit conversion expert. Current working mode: [{mode}].

❗Important Notes:
- "team" represents "shift" (machine shift).
- **"t" strictly means metric ton (1 t = 1000 kg), never shift.**

⚠️ Critical warning:
- Your reasoning MAY be correct, but the final transfer_function is OFTEN wrong if not derived strictly from the reasoning.
- The transfer_function MUST be derived directly from the equivalence stated in reasoning.
- Any mismatch between reasoning and transfer_function is considered an ERROR.

Your task is to generate a Python lambda function converting
FROM [Project Unit] TO [Target Unit].

[Project Context]:
{project_info}

[Project Unit] (input x): {project_unit}
[Target Unit] (output): {target_unit}

{additional_context}

Engineering rules (MUST follow):

1. Explicit equivalence (MANDATORY):
   In reasoning, you MUST write exactly ONE clear equivalence:
   - "1 {project_unit} = k {target_unit}"
   - OR "1 {target_unit} = k {project_unit}"

2. Derivation order (MANDATORY):
   - First write the equivalence in reasoning.
   - THEN derive transfer_function strictly from that equivalence.
   - DO NOT invent a different coefficient or direction in transfer_function.

3. Direction rule (STRICT):
   - If "1 {project_unit} = k {target_unit}" → lambda x: x * k
   - If "1 {target_unit} = k {project_unit}" → lambda x: x / k

4. Sanity check:
   - The implied magnitude must match basic engineering common sense.
   - If not, the result is INVALID.

Output ONLY the following JSON (no extra text):
{{
  "reasoning": "State the equivalence first, then briefly justify the assumption.",
  "transfer_function": "lambda x: ..."
}}
"""





# Resource consumption items and carbon emission factor semantic embedding enhancement, mainly letting LLM generate a description of less than 100 words based on understanding of these materials, mainly describing the material's...
SEMANTIC_BRIEF_PROMPT = ChatPromptTemplate.from_template("""
You are a carbon emission factor expert in the field of construction and materials. Based on the following JSON information, generate a Chinese introduction of ≤100 characters:
{node_info}

Requirements:
1) List the industry common names of resource items (such as hot-rolled carbon steel bars i.e. rebar);
2) Point out applicable situations and provide a brief introduction.
Output only the final introduction, single line, no extra symbols.
""")


# Newly added batch processing prompt
ENHANCEMENT_BATCH_PROCESS_PROMPT = """
Please perform standardized processing on these names and generate concise descriptions based on the following itemized work information under the same sub-divisional work.
Guessed project category: {context}

Itemized work information:
{items_info}

Requirements:
1. Process each itemized work separately
2. Name standardization: Maintain professional terminology accuracy, unify expression methods
3. Description generation: Generate descriptions for each itemized work, if the original description doesn't need modification then leave it unchanged
4. Strictly output result in the following JSON format:
[
  {{
    "name": "Standardized itemized work name",
    "description": "Concise description of the itemized work, some introduction should be given within 100 characters"
  }},
  ...
]
5. Do not output any extra text, only output the JSON array
"""

CEF_RERANK_PROMPT = ChatPromptTemplate.from_template("""
You are an expert in carbon emission assessment for the construction industry. 
Based on the given resource consumption item and a list of carbon emission factors, 
select the most appropriate carbon emission factor.

【Task Description】
Analyze the resource consumption item and the list of carbon emission factors, 
and select the most suitable factor by considering the following criteria:
1. Professional relevance: whether the emission factor belongs to the same technical/industrial domain as the resource.
2. Scenario applicability: whether the emission factor matches the actual usage scenario of the resource.
3. Unit consistency: whether the units are consistent or can be reasonably converted.
4. Project suitability: based on the project context, determine which factor best fits the situation.

【Project Information】
{project_info}

【Resource Consumption Item】
Name: {resource_name}
Category: {resource_category}
Unit: {resource_unit}
Description: {resource_description}

【Carbon Emission Factor List】
{factor_list}

【Output Requirement】
Output ONLY the ID of the best-matching carbon emission factor, in the exact format:
"factor_id"

If none of the factors are suitable, return null. 
For example, if the resource is mechanical equipment but all factors are for materials or energy, you should return null.
""")


RISK_PROMPT = """
You are an expert in carbon emission assessment for the construction industry.

Your output space is strictly limited to the following tokens:
{candidate_tokens}

Each token corresponds to one carbon emission factor (EF_ID).
Your task:
- Evaluate all factors based on semantic relevance, engineering logic,
  scenario applicability, and unit compatibility.
- Think step-by-step internally.
- Then output ONLY the single token you consider most suitable.
- Do NOT output explanations, reasoning, or multiple tokens.
- Output must be exactly one token from this set: {candidate_tokens}

Project Information:
{project_info}

Resource Item:
name={resource_name}
category={resource_category}
unit={resource_unit}
description={resource_description}

Candidate Carbon Emission Factors:
{factor_list}
"""



# ========== 6. Itemized Work Supplement Analysis ==========
SUB_ITEM_COMPLETENESS_ANALYSIS_PROMPT = ChatPromptTemplate.from_template("""
You are an engineering expert in the construction field. Determine whether itemized works need to be supplemented; prioritize repairing process breakpoints and missing prerequisite essential processes while ensuring no duplication.

[Project Information]
{project_info}

[Itemized Work Family Relationship Structure]
{family_relationship}

[Existing Itemized Works]
{existing_quota}

[Supplement Determination]
The itemized work family relationship structure is for reference only (this family relationship may also be wrong so please dialectically consider it). You need to think for yourself whether there are missing necessary itemized works based on the existing itemized works, and only complete what is absolutely necessary.
For example: Diaphragm wall slotting, diaphragm wall concrete, but lacking diaphragm wall rebar cage in between, then the rebar cage needs to be supplemented.
If not absolutely necessary, please do not casually supplement, for example, if excavation already exists as mechanical earthwork, then do not add manual earthwork.

[Deduplication/Uniqueness]
- Prohibit near-duplicates caused by synonyms/aliases/granularity differences with existing items; high semantic overlap is considered duplication and must not be added.
- If existing items have different names but descriptions already cover the process to be supplemented, consider it already included and do not supplement.

[Quantity Estimation Principles]
- Prioritize using existing itemized work quantities, family relationships, and industry standard parameters to derive reasonable quantities and measurement units.
- If reasonable assumptions exist (such as hole depth approximately equal to grouting pile length, total holes can be calculated by volume÷cross-sectional area), conservative estimates based on common processes can be made, and clearly select measurement units (such as m, m², m³, item).
- Only return to default: quantity=1.0, unit="item" when key parameters are truly missing and reasonable estimates cannot be derived.

[Output Requirements]
- Need supplementation: Output only "bare JSON" array, elements in the form {{ "name":"itemized work name","id":"itemized work ID (can be empty)","scale":{{"quantity":quantity,"unit":"unit"}} }}.
- No supplementation needed: Output [].
- Strictly prohibit any code block markers (such as ```, ```json), strictly prohibit outputting any text outside JSON.

[Output Only One (Do Not Add Extra Content)]
- When supplementing:
[{{"name":"itemized work name","id":"itemized work ID (can be empty string)","scale":{{"quantity":quantity,"unit":"unit"}}}}]
- When not supplementing:
[]
""")



