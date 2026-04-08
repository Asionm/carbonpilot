# -*- coding: utf-8 -*-
"""
Knowledge Graph Generator

This module is responsible for generating two types of knowledge: engineering knowledge and carbon emission knowledge.

Engineering Knowledge Generation Process:
1. Extract engineering entities from PDF files into structured data files
2. Build statements from structured files and store knowledge in the knowledge graph database
3. Enhance entity content (to facilitate subsequent semantic matching) and vectorize entities (to prepare for semantic matching and vector operations)
4. Enhance entity relationships in the knowledge graph; primarily focuses on the sequential order of sub-item works

Carbon Emission Knowledge Generation Process:
1. Parse structured carbon emission factor databases and store information in Neo4j graph database
2. Enhance entity content (to facilitate subsequent semantic matching) and vectorize entities (to prepare for semantic matching and vector operations)
3. Pre-build similarity between carbon emission factors and resource items
"""
from knowledge_graph.quota.utils.LLM_extractor import quota_extractor
from knowledge_graph.quota.utils.pdf_extractor import extract_pdf_to_json
from knowledge_graph.quota.utils.rule_match import process_quota_data
from knowledge_graph.quota.utils.KG_generate import generate_quota_knowledge
from knowledge_graph.quota.utils.vectorize import quota_vectorize
from knowledge_graph.quota.utils.relationship_enhanced import engineering_relationships_enhancement
from knowledge_graph.cef.KG_generate import generate_knowledge_graph
from knowledge_graph.cef.vectorize import carbon_vectorize
from knowledge_graph.cef.CEF_work_builder import cef_work_builder



def engineering_knowledge_generator(enable_semantic_enhancement=True):
    '''Information Extraction'''
    # Extract content from PDF files and convert to JSON text data
    # extract_pdf_to_json(pdf_path="knowledge_graph\\quota\\quota_files\\data.pdf", output_dir='knowledge_graph\\quota\\static')

    # Use rules to preprocess the extracted content to locate specific information to make it easier for LLM to extract
    # process_quota_data("knowledge_graph\\quota\\static\\data.json", "knowledge_graph\\quota\\static\\structured_data.json")

    # Entity extraction to extract engineering knowledge
    # quota_extractor()

    '''Store in Neo4j database'''
    generate_quota_knowledge(input_file="knowledge_graph\\quota\\static\\structured_llm_augmented.json")

    '''Information enhancement and vectorization'''
    quota_vectorize(enhance_semantic=enable_semantic_enhancement)

    '''Sequential relationship enhancement'''
    engineering_relationships_enhancement()

def carbon_knowledge_generator(enable_semantic_enhancement=True):
    '''Create carbon emission knowledge graph from structured files'''
    generate_knowledge_graph()

    '''Information enhancement and vectorization'''
    carbon_vectorize(enhance_semantic=enable_semantic_enhancement)

    '''Enhance relationships between resource consumption items and carbon emission factors'''
    cef_work_builder()