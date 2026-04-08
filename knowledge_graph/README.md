# Knowledge Graph

This directory contains the code for building and managing knowledge graphs related to carbon emission calculations. It involves entity extraction from various documents and storing the results in the Neo4j knowledge graph database, while enhancing relationships within the knowledge graph.

## Components

### CEF (Carbon Emission Factor)
- Entity extraction and relationship building for carbon emission factors
- Cache management for CEF data
- Relationship querying and rollback mechanisms
- Vectorization support for similarity searches

### Quota
- Query mechanisms for carbon quota data
- Static data storage in JSON format
- Utility functions for PDF extraction, LLM-based extraction, and rule matching
- Relationship enhancement tools
- Knowledge graph generation and rollback capabilities

## Key Features

1. **Entity Extraction**: Extracts entities from various document formats for carbon emission calculations
2. **Graph Storage**: Stores structured carbon-related data in Neo4j graph database
3. **Relationship Enhancement**: Enhances connections between entities for better inference
4. **Vectorization**: Converts entities to vector representations for similarity searches
5. **Retrieval**: Provides querying capabilities for downstream carbon emission calculation services

## Usage

In the current implementation, only the retrieval functionality serves the subsequent carbon emission calculation process. The knowledge graph construction itself is a customized one-time operation.

## Directory Structure