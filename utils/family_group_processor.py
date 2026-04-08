from typing import Dict, Any, List, Optional, Generator, Tuple
import logging
from configs.neo4j_wrapper import Neo4jWrapper
from utils.utils import _coerce_float, _extract_resource_base_value, _safe_get, _iter_sub_item_works
from prompts import SUB_ITEM_COMPLETENESS_ANALYSIS_PROMPT
# Import unit conversion tools
from utils.unit_transfer import unit_transfer_llm, compile_safe_lambda
from utils.utils import _coerce_float

logger = logging.getLogger(__name__)


def process_family_group(
    quota_id: str, 
    sub_item_works_with_quota: List[Dict], 
    neo4j_wrapper: Neo4jWrapper,
    processed_families: set,
    plain_query: Any
) -> Optional[Dict[str, Any]]:
    """
    Process a single family group and generate family relationship information
    
    Args:
        quota_id: Quota ID
        sub_item_works_with_quota: List of sub-item works with quota information
        neo4j_wrapper: Neo4j wrapper instance
        processed_families: Set of processed families
        plain_query: Query module
        
    Returns:
        Family group information dictionary or None (if family has no members)
    """
    # Check if this family has already been processed
    if quota_id in processed_families:
        return None
        
    # Get quota family (related PRECEDES relationship network)
    family_info = plain_query.get_precedes_family_with_relationships(neo4j_wrapper.get_driver(), quota_id)
    family_members = family_info.get("members", [])
    family_relationships = family_info.get("relationships", [])
    
    # Skip if no family members
    if not family_members:
        return None
        
    # Create family ID (use the first member's ID in the family as family ID)
    family_id = sorted([member["id"] for member in family_members])[0] if family_members else quota_id
    
    # Mark this family as processed
    for member in family_members:
        member_id = member.get("id")
        if member_id:
            processed_families.add(member_id)
    
    # Collect existing sub-item works belonging to this family
    existing_quota_in_family = [
        item for item in sub_item_works_with_quota 
        if item["quota_id"] in [member["id"] for member in family_members]
    ]
    
    # Generate visual representation of family relationships
    relationship_strings = []
    # Collect all involved nodes
    all_nodes = set()
    for rel in family_relationships:
        source = rel["source"]
        target = rel["target"]
        all_nodes.add(source["id"])
        all_nodes.add(target["id"])
    
    # If total number of nodes does not exceed 20, display all relationships
    if len(all_nodes) <= 20:
        for rel in family_relationships:
            source = rel["source"]
            target = rel["target"]
            source_unit = source.get("unit", "")
            source_unit_str = f"[{source_unit}]" if source_unit else ""
            relationship_strings.append(f"{source['name']}{source_unit_str}({source['id']}) -> {target['name']}({target['id']})")
    else:
        # When nodes exceed 20, prioritize displaying direct relationships
        direct_relationships = []
        
        # Collect direct relationships (relationships involving nodes in existing_quota_in_family)
        existing_quota_ids = [item["quota_id"] for item in existing_quota_in_family]
        for rel in family_relationships:
            source = rel["source"]
            target = rel["target"]
            source_id = source["id"]
            target_id = target["id"]
            
            # If either source or target is in existing quotas, consider it a direct relationship
            if source_id in existing_quota_ids or target_id in existing_quota_ids:
                direct_relationships.append(rel)
        
        # Display direct relationships
        for rel in direct_relationships:
            source = rel["source"]
            target = rel["target"]
            source_unit = source.get("unit", "")
            source_unit_str = f"[{source_unit}]" if source_unit else ""
            relationship_strings.append(f"{source['name']}{source_unit_str}({source['id']}) -> {target['name']}({target['id']})")
    
    # Return family group information
    return {
        "family_id": family_id,
        "members": family_members,
        "existing_members": existing_quota_in_family,
        "relationships": family_relationships,
        "relationship_strings": relationship_strings
    }


def analyze_family_groups(
    family_groups: Dict[str, Dict],
    project_data: Dict[str, Any],
    llm_wrapper: Any
) -> List[Dict[str, Any]]:
    """
    Analyze family groups to identify missing sub-item works
    
    Args:
        family_groups: Dictionary of family groups
        project_data: Project data
        llm_wrapper: LLM wrapper instance
        
    Returns:
        List of missing sub-item works to be supplemented
    """
    missing_items = []
    
    for family_id, family_group in family_groups.items():
        members = family_group.get("members", [])
        existing_members = family_group.get("existing_members", [])
        
        # If family has only one member, no need to analyze
        if len(members) <= 1:
            continue
            
        # If all family members are present, no need to analyze
        if len(existing_members) >= len(members):
            continue
            
        # Prepare data for LLM analysis
        family_member_names = [f"{m['name']} ({m['id']})" for m in members]
        existing_member_names = [f"{m['sub_item_work']['name']} ({m['quota_id']})" for m in existing_members]
        missing_member_names = [name for name in family_member_names if name not in existing_member_names]
        
        # Create context for LLM
        context = {
            "family_members": family_member_names,
            "existing_members": existing_member_names,
            "missing_members": missing_member_names,
            "relationships": family_group.get("relationship_strings", [])
        }
        
        # Use LLM to analyze completeness
        try:
            prompt = SUB_ITEM_COMPLETENESS_ANALYSIS_PROMPT.format(
                family_context=json.dumps(context, ensure_ascii=False, indent=2)
            )
            
            response = llm_wrapper.generate_response(prompt)
            
            # Parse LLM response (should be JSON)
            import json
            try:
                result = json.loads(response)
                items_to_create = result.get("items_to_create", [])
                for item in items_to_create:
                    missing_items.append(item)
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON: %s", response)
                
        except Exception as e:
            logger.warning("LLM analysis failed for family group %s: %s", family_id, e)
    
    return missing_items


def handle_missing_items(
    missing_items: List[Dict[str, Any]], 
    indiviual_projects: Dict[str, Any],
    neo4j_wrapper: Neo4jWrapper
) -> None:
    """
    Handle missing sub-item works by supplementing them into the project data
    
    Args:
        missing_items: List of missing sub-item works to be supplemented
        indiviual_projects: Individual project data
        neo4j_wrapper: Neo4j wrapper instance
    """
    if not missing_items:
        return

    logger.info(f"Need to supplement {len(missing_items)} sub-item works")

    query = """
    MATCH (si:sub_item_work {id: $item_id})-[:BELONGS_TO]->(wc:work_content)
          -[:BELONGS_TO]->(ss:specialty_subdivision)
          -[:BELONGS_TO]->(ss_type:specialty_subdivision_type)
          -[:BELONGS_TO]->(sd:sub_divisional_work)
    RETURN si.name AS sub_item_name,
           si.id   AS sub_item_id,
           wc.content AS work_content,
           ss.name AS specialty_subdivision,
           sd.name AS sub_divisional_work
    """

    # Query to get quota unit
    quota_query = """
    MATCH (q:sub_item_work {id: $quota_id})
    RETURN q.unit AS quota_unit
    """

    driver = neo4j_wrapper.get_driver()
    with driver.session() as session:
        for item in missing_items:
            item_id = item.get("id")
            item_name = item.get("name")
            if not item_id or not item_name:
                continue

            record = session.run(query, item_id=item_id).single()
            if not record:
                logger.warning(f"Hierarchical information not found: {item_name} ({item_id})")
                continue

            sub_item_name = record["sub_item_name"]
            sub_item_id   = record["sub_item_id"]
            ss_name       = record["specialty_subdivision"]
            sd_name       = record["sub_divisional_work"]
            work_content  = record["work_content"]

            # Prepare scale information
            scale = item.get("scale", {})
            quantity = scale.get("quantity", 1.0) if isinstance(scale, dict) else 1.0
            unit = scale.get("unit", "item") if isinstance(scale, dict) else "item"

            # Get quota unit
            quota_record = session.run(quota_query, quota_id=item_id).single()
            quota_unit = quota_record["quota_unit"] if quota_record else ""

            # Prepare resource_items information
            # First construct a temporary sub_item_work_node for querying resource items
            temp_sub_item_work_node = {
                "properties": {
                    "id": sub_item_id
                }
            }
            
            # Get resource_items from database
            try:
                from knowledge_graph.quota.query.query import get_resource_items
                resource_items = get_resource_items(driver=driver, sub_item_work_node=temp_sub_item_work_node) or []
            except Exception as e:
                logger.warning(f"Failed to get resource items {sub_item_name} ({sub_item_id}): {e}")
                resource_items = []
            
            # Import unit conversion related functions
            from utils.unit_transfer import unit_transfer_llm, compile_safe_lambda
            from utils.utils import _coerce_float
            
            # Perform unit conversion
            transfered_quantity = quantity
            transfered_unit = unit
            
            if unit and quota_unit and (unit != quota_unit):
                try:
                    # Prepare additional context with quota info
                    additional_context = f"Matched quota: {item_name} (ID: {item_id})"
                    
                    transfer_func_str = unit_transfer_llm(
                        project_info=work_content,
                        project_unit=unit,
                        target_unit=quota_unit,
                        mode="quantity",
                        additional_context=additional_context
                    )
                    
                    transfer_func = compile_safe_lambda(transfer_func_str)
                    transfered_quantity = float(transfer_func(_coerce_float(quantity, 0.0)))
                    transfered_unit = quota_unit
                except Exception as e:
                    logger.warning(f"Unit conversion failed, falling back to 1:1: {e}")
                    transfered_quantity = _coerce_float(quantity, 0.0)
                    transfered_unit = unit

            # Process resource items and calculate total usage
            processed_resources = []
            for res in resource_items:
                # Copy resource item to avoid modifying original data
                res_copy = res.copy() if isinstance(res, dict) else {}
                # Get base value
                base_val = _extract_resource_base_value(res_copy)
                # Calculate total usage (base value * quantity)
                value_total = base_val * transfered_quantity
                res_copy["value"] = value_total
                # Retain unit as much as possible
                if "unit" not in res_copy and isinstance(res_copy, dict):
                    # If properties.unit exists, pass it through
                    ru = _safe_get(res_copy, "properties", "unit")
                    if ru:
                        res_copy["unit"] = ru
                processed_resources.append(res_copy)

            new_sub_item = {
                "name": sub_item_name,
                "id": sub_item_id,
                "level": "sub_item_work",
                "properties": {
                    "is_supplemented": True,
                    "used_quantity": transfered_quantity,
                    "used_unit": transfered_unit
                },
                "resource_items": processed_resources,
                "matched_quota": {
                    "id": item_id,  # Use the item's own id as the matched quota ID
                    "name": item_name  # Use the item's own name as the matched quota name
                }
            }
            
            # Add scale information
            if "scale" in item:
                new_sub_item["scale"] = item["scale"]

            # Add to project data
            # Find the right place to insert this new sub-item work
            for individual_project in indiviual_projects.get("projects", []):
                for unit_project in individual_project.get("单位工程", []):
                    for sub_div_work in unit_project.get("分部工程", []):
                        if sub_div_work.get("name") == sd_name:
                            for spec_subdiv in sub_div_work.get("专业分部工程", []):
                                if spec_subdiv.get("name") == ss_name:
                                    if "分项工程" not in spec_subdiv:
                                        spec_subdiv["分项工程"] = []
                                    spec_subdiv["分项工程"].append(new_sub_item)
                                    break
                            break
                    break
                break