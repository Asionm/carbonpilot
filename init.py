import time
from knowledge_graph.neo4j_init import create_neo4j_container
from knowledge_graph.kw_generator import engineering_knowledge_generator, carbon_knowledge_generator

create_neo4j_container(container_name="neo4j-carbon-noenhance")

# Wait for 3 minutes to allow the Neo4j container to fully initialize
print("Waiting 3 minutes for Neo4j container to initialize...")
time.sleep(180)

# By default, semantic enhancement is enabled
engineering_knowledge_generator(enable_semantic_enhancement=False)
carbon_knowledge_generator(enable_semantic_enhancement=False)