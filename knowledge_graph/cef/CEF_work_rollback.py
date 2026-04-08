# -*- coding: utf-8 -*-
"""
Rollback script for Carbon Emission Factor (Factor) ↔ Resource Item relationships.

This script removes APPLIES_TO relationships between `resource_item` nodes
and `factor` nodes in the Neo4j carbon emission knowledge graph.

Features:
1. Remove ALL APPLIES_TO relationships.
2. Selective removal based on a name pattern.
3. Relationship summary before & after rollback.

Usage:
1. Full rollback:
       python cef/CEF_work_rollback.py

2. Selective rollback (match keyword in resource or factor name):
       python cef/CEF_work_rollback.py --pattern "cement"

3. Only verify the current relationship status:
       python cef/CEF_work_rollback.py --verify
"""

import os
import sys
import argparse

# Add project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from configs.neo4j_wrapper import Neo4jWrapper

# Relationship settings
RELATIONSHIP_TYPE = "APPLIES_TO"
WEIGHT_PROPERTY = "similarity"


def rollback_all_relationships():
    """
    Remove ALL APPLIES_TO relationships between resource_item and factor nodes.
    """
    neo4j = Neo4jWrapper()

    try:
        print("Starting full rollback: removing all APPLIES_TO relationships...")

        # Count existing relationships
        count_query = f"""
        MATCH (r:resource_item)-[rel:{RELATIONSHIP_TYPE}]->(f:factor)
        RETURN count(rel) AS relationship_count
        """
        result = neo4j.execute_query(count_query)
        relationship_count = result[0]["relationship_count"] if result else 0
        print(f"Total relationships before deletion: {relationship_count}")

        if relationship_count == 0:
            print("No relationships found to remove.")
            return

        # Delete all relationships
        delete_query = f"""
        MATCH (r:resource_item)-[rel:{RELATIONSHIP_TYPE}]->(f:factor)
        DELETE rel
        """
        neo4j.execute_query(delete_query)

        print(f"✅ Successfully removed {relationship_count} APPLIES_TO relationships.")

    except Exception as e:
        print(f"❌ Error while deleting relationships: {e}")
    finally:
        neo4j.close()


def selective_rollback(pattern: str):
    """
    Selectively remove APPLIES_TO relationships based on name pattern.

    Args:
        pattern (str): string partially matched against resource_item.name or factor.name
    """
    neo4j = Neo4jWrapper()

    try:
        print(f"Starting selective rollback where name contains pattern '{pattern}'...")

        # Count matched relationships
        count_query = f"""
        MATCH (r:resource_item)-[rel:{RELATIONSHIP_TYPE}]->(f:factor)
        WHERE r.name CONTAINS $pattern OR f.name CONTAINS $pattern
        RETURN count(rel) AS relationship_count
        """
        result = neo4j.execute_query(count_query, {"pattern": pattern})
        relationship_count = result[0]["relationship_count"] if result else 0

        print(f"Matched relationship count: {relationship_count}")

        if relationship_count == 0:
            print("No matching relationships found.")
            return

        # Delete relationships matching the pattern
        delete_query = f"""
        MATCH (r:resource_item)-[rel:{RELATIONSHIP_TYPE}]->(f:factor)
        WHERE r.name CONTAINS $pattern OR f.name CONTAINS $pattern
        DELETE rel
        """
        neo4j.execute_query(delete_query, {"pattern": pattern})

        print(f"✅ Successfully deleted {relationship_count} APPLIES_TO relationships matching '{pattern}'.")

    except Exception as e:
        print(f"❌ Error during selective rollback: {e}")
    finally:
        neo4j.close()


def verify_relationships():
    """
    Display summary of current APPLIES_TO relationships in the graph.
    """
    neo4j = Neo4jWrapper()

    try:
        print("\nVerifying current APPLIES_TO relationship status...")

        # Count all relationships
        count_query = f"""
        MATCH (r:resource_item)-[rel:{RELATIONSHIP_TYPE}]->(f:factor)
        RETURN count(rel) AS relationship_count
        """
        result = neo4j.execute_query(count_query)
        relationship_count = result[0]["relationship_count"] if result else 0

        print(f"  - Total APPLIES_TO relationships: {relationship_count}")

        # Display examples if available
        if relationship_count > 0:
            sample_query = f"""
            MATCH (r:resource_item)-[rel:{RELATIONSHIP_TYPE}]->(f:factor)
            RETURN 
                r.name AS resource_name,
                f.name AS factor_name,
                rel.{WEIGHT_PROPERTY} AS similarity
            ORDER BY rel.{WEIGHT_PROPERTY} DESC
            LIMIT 3
            """
            samples = neo4j.execute_query(sample_query)

            if samples:
                print("  - Top related examples:")
                for sample in samples:
                    print(
                        f"    {sample['resource_name']} → {sample['factor_name']} "
                        f"(similarity: {sample['similarity']:.3f})"
                    )
        else:
            print("  - No APPLIES_TO relationships found.")

    except Exception as e:
        print(f"❌ Error verifying relationships: {e}")
    finally:
        neo4j.close()


def main():
    print("===== CEF ↔ Resource Item APPLIES_TO Relationship Rollback Tool =====")

    parser = argparse.ArgumentParser(
        description="Rollback APPLIES_TO relationships between resource_item and factor nodes."
    )
    parser.add_argument("--pattern", type=str, help="Pattern for selective rollback (substring match)")
    parser.add_argument("--verify", action="store_true", help="Only verify relationship status")

    args = parser.parse_args()

    if args.verify:
        verify_relationships()
        return

    # Show status before deletion
    verify_relationships()

    if args.pattern:
        selective_rollback(args.pattern)
    else:
        rollback_all_relationships()

    # Show status after deletion
    verify_relationships()

    print("\n===== Rollback Completed =====")


if __name__ == "__main__":
    main()
