
# from configs.llm_wrapper import LLMWrapper
# from configs.neo4j_wrapper import Neo4jWrapper
# from knowledge_graph.quota.query import agent_based_query


# llm = LLMWrapper()
# neo4j = Neo4jWrapper()
# query_agent = agent_based_query.AgentBasedQuery(neo4j_wrapper=neo4j, llm_wrapper=llm)


# query_text = """
#                     {
#                       "level": "sub_item_work",
#                       "name": "带形基础",
#                       "description": "混凝土种类:预拌;混凝土强度等级:C30",
#                       "unit": "m3",
#                       "quantity": 53.48,
#                       "quantity": 64.58,
#                     }
# """

# best_item, resource_items, llm_calls = query_agent.query(
#     query_input=query_text,
#     use_reranker=True,
# )


from utils.toon_decoder import toon_decode


with open("test", "r", encoding='utf8') as f:
    test = f.read()

result = toon_decode(test)

print(result)