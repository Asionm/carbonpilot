// utils/api.ts - Unified API interface management file
import axios from 'axios';

// Determine base URL based on environment
const getBaseURL = () => {
  if (typeof window !== 'undefined') {
    // Client-side - use the current host but replace frontend port (3000) with backend port (8000)
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    return `${protocol}//${hostname}:8000/api`;
  } else {
    // Server-side - use localhost:8000
    return 'http://localhost:8000/api';
  }
};

// Create axios instance with dynamic base URL
const apiClient = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000, // Request timeout in milliseconds
});

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    // Can add authentication tokens, etc. here
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Unified error handling
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// Configuration types
interface LLMConfig {
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  api_base: string;
  api_key: string;
}

interface AgentConfig {
  enable_query_agent: boolean;
  think_mode: string;
  enhance_s1: boolean;
  enhance_s2: boolean;
  alignment_mode: string;
  enable_summary_agent: boolean;
}

interface ConfigData {
  llm_config: LLMConfig;
  agent_config: AgentConfig;
}

// API interface definitions
export const api = {
  // Memory management related interfaces
  memory: {
    getStatus: () => apiClient.get('/memory'),
    getContent: (memoryType: string, filename: string) => apiClient.get(`/memory/${memoryType}/${filename}`),
    updateContent: (memoryType: string, filename: string, content: any) => apiClient.put(`/memory/${memoryType}/${filename}`, content),
    clear: (memoryType: string) => apiClient.delete(`/memory/${memoryType}`),
  },

  // History related interfaces
  history: {
    getAll: () => apiClient.get('/history'),
    getDetail: (projectName: string) => apiClient.get(`/history/${projectName}`),
    delete: (projectName: string) =>
      apiClient.delete(`/history/${encodeURIComponent(projectName)}`),
  },

  // Configuration related interfaces
  config: {
    getCurrent: () => apiClient.get('/config'),
    update: (config: ConfigData) => apiClient.post('/config', config),
  },

  // Project upload related interfaces
  project: {
    upload: (formData: FormData) => apiClient.post('/upload-project', formData),
    calculate: (formData: FormData) => apiClient.post('/calculate-emission', formData),
  },

  // SSE related interfaces
  sse: {
    connect: (projectName: string) => {
      // Return full URL for EventSource connection
      return `${getBaseURL()}/sse/${projectName}`;
    },
  },

  // Chat related interfaces
  chat: {
    // Legacy non-streaming chat
    sendMessage: (data: any) => apiClient.post('/chat', data),

    // Streaming chat using SSE (EventSource polyfill POST)
    stream: () => `${getBaseURL()}/chat`,
    
    getHistory: (projectName: string) =>
      apiClient.get(`/chat/history/${encodeURIComponent(projectName)}`),

    clearHistory: (projectName: string) =>
      apiClient.delete(`/chat/history/${encodeURIComponent(projectName)}`),
  
  },

};

export default api;