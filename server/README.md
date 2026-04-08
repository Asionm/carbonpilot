# CarbonPilot Server

The server component of CarbonPilot provides RESTful APIs for carbon emission calculation and result analysis.

## API Endpoints

### Upload Project File
```
POST /upload-project
```
Upload a project file (PDF, Excel, TXT, MD, etc.) to start carbon emission calculation.

Parameters:
- `file`: The project file to upload
- `project_name`: Name of the project
- `config`: (Optional) JSON string with calculation configuration

Returns:
```json
{
  "message": "File uploaded successfully",
  "project_name": "Example Project",
  "file_path": "/path/to/file",
  "file_hash": "abcd1234",
  "file_name": "example.pdf",
  "content_type": "application/pdf",
  "sse_endpoint": "/sse/Example Project",
  "calculation_endpoint": "/calculate-emission"
}
```

### Start Carbon Emission Calculation
```
POST /calculate-emission
```
Start the carbon emission calculation process for an uploaded file.

Parameters:
- `project_name`: Name of the project
- `file_hash`: Hash of the uploaded file
- `config`: (Optional) JSON string with calculation configuration

Returns:
```json
{
  "status": "Calculation started",
  "project_name": "Example Project"
}
```

### Server-Sent Events Stream
```
GET /sse/{project_name}
```
Stream real-time updates during the carbon emission calculation process.

Returns:
Server-sent events with calculation progress and status updates.

### Chat with Results
```
POST /chat
```
Chat with the calculation results using LLM.

Request Body:
```json
{
  "project_name": "Example Project",
  "messages": [
    {
      "role": "user",
      "content": "What is the total carbon emission?"
    }
  ],
  "config": {
    "provider": "openai",
    "model_name": "gpt-4",
    "temperature": 0.7
  }
}
```

Returns:
```json
{
  "response": "The total carbon emission is 125.5 tons CO2."
}
```

### Get Current Configuration
```
GET /config
```
Get the current server configuration.

Returns:
```json
{
  "llm_provider": "openai",
  "llm_model_name": "gpt-4",
  "llm_temperature": "0.7",
  "llm_max_tokens": "8192",
  "neo4j_uri": "bolt://localhost:7687",
  "server_port": "8000"
}
```

### Update Configuration
```
POST /config
```
Update server configuration (temporary, for current session).

Request Body:
```json
{
  "provider": "openai",
  "model_name": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 8192,
  "api_base": "https://api.openai.com/v1",
  "api_key": "sk-..."
}
```

Returns:
Updated configuration.

## Configuration

The server can be configured using environment variables or through the `/config` API endpoint.

Environment Variables:
- `SERVER_PORT`: Port for the server (default: 8000)
- `SERVER_TITLE`: Server title (default: "CarbonPilot API Server")
- `SERVER_DESCRIPTION`: Server description (default: "API server for CarbonPilot carbon emission calculation system")
- `LLM_PROVIDER`: LLM provider (openai, ollama, etc.)
- `LLM_MODEL_NAME`: LLM model name
- `LLM_TEMPERATURE`: LLM temperature setting
- `LLM_MAX_TOKENS`: Maximum tokens for LLM responses
- `LLM_OPENAI_API_BASE`: OpenAI API base URL
- `LLM_OPENAI_API_KEY`: OpenAI API key
- `LLM_OLLAMA_BASE_URL`: Ollama base URL
- `NEO4J_URI`: Neo4j database URI
- `NEO4J_USERNAME`: Neo4j username
- `NEO4J_PASSWORD`: Neo4j password

## Running the Server

To run the server:

```bash
python server/main.py
```

Or using uvicorn:

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
```