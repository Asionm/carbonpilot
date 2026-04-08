# configs\embedding_wrapper.py
from dotenv import load_dotenv
import os
from langchain_ollama import OllamaEmbeddings

# load .env file
load_dotenv(override=True)

class EmbeddingWrapper:

    def __init__(self, model=None, base_url=None, temperature=0.01):

        self.model = model or os.getenv("EMBEDDING_MODEL", "bge-m3")
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.temperature = temperature
        
        self.embeddings = OllamaEmbeddings(
            model=self.model,
            base_url=self.base_url,
            temperature=self.temperature
        )

    def get_embeddings(self):
        return self.embeddings

    def set_embedding_info(self, model=None, base_url=None, temperature=None):

        self.model = model or self.model
        self.base_url = base_url or self.base_url
        self.temperature = temperature or self.temperature
        

        self.embeddings = OllamaEmbeddings(
            model=self.model,
            base_url=self.base_url,
            temperature=self.temperature
        )

    def embed_query(self, text):

        return self.embeddings.embed_query(text)

    def embed_documents(self, texts):

        return self.embeddings.embed_documents(texts)