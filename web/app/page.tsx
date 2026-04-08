'use client'

import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import UploadSection from '../components/UploadSection'
import ResultsSection from '../components/ResultsSection'
import ChatSection from '../components/ChatSection'
import HistorySection from '../components/HistorySection'
import SettingsModal from '../components/SettingsModal' // 添加设置模态框导入
import { api } from '../utils/api' // 导入统一API接口
import { CalculationResult, ChatMessage, Neo4jConfig, LLMConfig, AgentConfig } from '../utils/schemes'
import {
  calculateProjectStats,
  calculateFactorStats,
  processSubItemWorkData,
  processMaterialData
} from '../utils/dataHandler'
import { LanguageProvider, useLanguage } from '../utils/LanguageContext'


function HomeContent() {
  const { t } = useLanguage()
  // State management
  const [activeTab, setActiveTab] = useState<'upload' | 'results' | 'chat' | 'history'>('upload')
  const [isLoading, setIsLoading] = useState(false)
  const [progress, setProgress] = useState({
    status: "",
    percentage: 0,
    stepText: "",
    itemName: ""
  });
  const [calculationResult, setCalculationResult] = useState<CalculationResult | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [isChatLoading, setIsChatLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [history, setHistory] = useState<any[]>([])
  const [selectedHistory, setSelectedHistory] = useState<any>(null)
  const [neo4jConfig, setNeo4jConfig] = useState<Neo4jConfig>({
    uri: 'bolt://localhost:7687',
    username: 'neo4j',
    password: '',
    database: 'neo4j'
  })

  const [llmConfig, setLlmConfig] = useState<LLMConfig>({
    provider: 'openai',
    model_name: 'qwen3-next-80b-a3b-instruct',
    temperature: 0.7,
    max_tokens: 32768,
    api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    api_key: ''
  })

  const [agentConfig, setAgentConfig] = useState<AgentConfig>({
    information_enhancement: 0,
    wbs_correction: 1,
    agnetic_search: 1,
    factor_alignment_mode: 0,
    memory_information: 1,
    memory_unit: 1
  })

  const [isSettingsOpen, setIsSettingsOpen] = useState(false) // 添加设置模态框状态

    // Update partial configuration functions
  const updateNeo4jConfig = (newConfig: Partial<Neo4jConfig>) => {
    setNeo4jConfig(prev => ({
      ...prev,
      ...newConfig
    }))
  }



  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom of chat
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [chatMessages])

  // Fetch initial configuration on component mount
  useEffect(() => {
    const loadConfig = async () => {
      try {
        // Load config from backend
        const configResponse = await api.config.getCurrent()
        if (configResponse?.data) {
          const configData = configResponse.data;
          if (configData.neo4j_config) {
            setNeo4jConfig(configData.neo4j_config);
          }
          if (configData.llm_config) {
            setLlmConfig(configData.llm_config);
          }
          if (configData.agent_config) {
            setAgentConfig(configData.agent_config);
          }
        }
      } catch (error) {
        console.error('Failed to load initial configuration:', error)
        // 使用默认配置继续，已定义的初始状态将作为默认值
      }
    }

    loadConfig()
    fetchHistory()
  }, [])

  // Fetch history data from API
  const fetchHistory = async () => {
    try {
      const response = await api.history.getAll()
      if (response?.data) {
        setHistory(response.data)
      }
    } catch (error: any) {
      console.error('Failed to fetch history:', error)
      // 可以添加用户友好的错误提示
      // setError('无法获取历史记录，请稍后重试')
    }
  }

  // Update partial LLM configuration
  const updateLlmConfig = (newConfig: Partial<LLMConfig>) => {
    setLlmConfig(prev => ({
      ...prev,
      ...newConfig
    }))
  }

  // Update partial Agent configuration
  const updateAgentConfig = (newConfig: Partial<AgentConfig>) => {
    setAgentConfig(prev => ({
      ...prev,
      ...newConfig
    }))
  }


  /**
   * Handle project file upload, trigger backend calculation,
   * and listen to real-time SSE progress events.
   */
  const handleFileUpload = async (formData: FormData) => {
    setIsLoading(true);
    setProgress({
      status: "Uploading file...",
      percentage: 0,
      stepText: "",
      itemName: ""
    });

    try {
      // 1) Upload file
      const uploadRes = await api.project.upload(formData);
      const { project_name, file_hash } = uploadRes.data;

      setProgress({
        status: "Starting calculation...",
        percentage: 3,
        stepText: "",
        itemName: ""
      });

      // 2) Start calculation
      const calcForm = new FormData();
      calcForm.append("project_name", project_name);
      calcForm.append("file_hash", file_hash);
      await api.project.calculate(calcForm);

      // 3) SSE subscription
      const sseUrl = api.sse.connect(project_name);
      const es = new EventSource(sseUrl);

      // ----------------------
      // Listen for "status"
      // ----------------------
      es.addEventListener("status", (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);

          const pct = data.progress ?? 0;
          const msg = data.message ?? "";

          let stepText = "";
          if (data.step) {
            const stepNames: Record<number, string> = {
              1: "Step 1 — Information Extraction",
              2: "Step 2 — Information Completion",
              3: "Step 3 — Emission Factor Matching",
              4: "Step 4 — Aggregation & Summary",
            };
            stepText = stepNames[data.step];
          }

          setProgress({
            percentage: pct,
            status: msg,
            stepText,
            itemName: data.name, // optional
          });

          if (data.completed) {
            es.close();
            setIsLoading(false);
            // Automatically switch to results tab when calculation is complete
            setTimeout(async () => {
              try {
                const response = await api.history.getDetail(project_name);
                setCalculationResult(response.data);
                setSelectedHistory(null);
                setActiveTab('results');
              } catch (error) {
                console.error('Failed to load calculation results:', error);
              }
            }, 500); // Small delay to ensure backend is ready
          }
        } catch (err) {
          console.error("SSE status parse error:", err);
        }
      });


      // ----------------------
      // Listen for "workflow"
      // ----------------------
      es.addEventListener("workflow", (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          console.log("Workflow:", data.message);
        } catch (err) {
          console.error("Failed to parse SSE 'workflow' event:", err);
        }
      });

      // ----------------------
      // Connection Error
      // ----------------------
      es.onerror = (err) => {
        console.error("SSE connection error:", err);
        es.close();
        setIsLoading(false);
        setProgress({
          status: "Error during calculation",
          percentage: 0,
          stepText: "",
          itemName: ""
        });
      };

    } catch (err) {
      console.error("Upload/Calculation failed:", err);
      setIsLoading(false);
      setProgress({
        status: "Failed",
        percentage: 0,
        stepText: "",
        itemName: ""
      });
    }
  };


  const refreshHistory = async () => {
    try {
      const response = await api.history.getAll();
      setHistory(response.data || []);
    } catch (err) {
      console.error("Failed to fetch history:", err);
    }
  };


  const handleChatSubmit = async () => {
    if (!chatInput.trim() || isChatLoading) return

    const userMessage: ChatMessage = {
      role: 'user',
      content: chatInput,
      timestamp: new Date()
    }

    const updatedMessages = [...chatMessages, userMessage]
    setChatMessages(updatedMessages)
    setChatInput('')
    setIsChatLoading(true)
    setIsStreaming(true)

    try {
      // 使用项目名称和消息调用新的聊天API
      const projectName = calculationResult?.project_name || selectedHistory?.project_name;
      
      if (!projectName) {
        throw new Error('No project selected');
      }

      // 创建一个ReadableStream来处理流式响应
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
          messages: updatedMessages,
          config: {
            provider: llmConfig.provider,
            model_name: llmConfig.model_name,
            temperature: llmConfig.temperature,
            max_tokens: llmConfig.max_tokens,
            api_base: llmConfig.api_base,
            api_key: llmConfig.api_key
          }
        })
      });

      if (!response.body) {
        throw new Error('ReadableStream not supported');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      // 创建助手消息
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date()
      };
      
      setChatMessages(prev => [...prev, assistantMessage]);
      
      // 读取流式响应
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        // 解码数据块
        const chunk = decoder.decode(value, { stream: true });
        
        // 更新助手消息内容
        setChatMessages(prev => {
          const newMessages = [...prev];
          const lastMessage = newMessages[newMessages.length - 1];
          if (lastMessage.role === 'assistant') {
            lastMessage.content += chunk;
          }
          return newMessages;
        });
      }
    } catch (error) {
      console.error('Chat error:', error)
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request.',
        timestamp: new Date()
      }
      setChatMessages(prev => [...prev, errorMessage])
    } finally {
      setIsChatLoading(false)
      setIsStreaming(false)
    }
  }

  const handleClearChatHistory = async () => {
    try {
      const projectName = calculationResult?.project_name || selectedHistory?.project_name;
      
      if (!projectName) {
        throw new Error('No project selected');
      }

      await fetch(`/api/chat/history/${projectName}`, {
        method: 'DELETE'
      });

      // 清空本地聊天记录
      setChatMessages([]);
    } catch (error) {
      console.error('Failed to clear chat history:', error);
    }
  };

  const loadHistoryItem = async (item: any) => {
    try {
      const response = await api.history.getDetail(item.project_name)
      setCalculationResult(response.data)
      setSelectedHistory(item)
      setActiveTab('results')
    } catch (error) {
      console.error('Failed to load history item:', error)
    }
  }

  // 检查是否有项目结果数据
  const hasProjectResults = !!calculationResult || !!selectedHistory;



  return (
    <div className="min-h-screen flex flex-col relative overflow-hidden bg-[#f6f9f7]">

      {/* 🌿 Low-carbon animated background */}
      <div className="absolute inset-0 -z-10 pointer-events-none overflow-hidden">
        
        {/* Base soft gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-green-50 via-blue-50 to-white" />

        {/* Floating low-carbon blobs */}
        <div className="absolute w-[750px] h-[750px] bg-green-200/35 rounded-full blur-3xl animate-blob top-[-10%] left-[-10%]" />
        <div className="absolute w-[650px] h-[650px] bg-blue-200/35 rounded-full blur-3xl animate-blob animation-delay-2000 top-[30%] right-[-15%]" />
        <div className="absolute w-[550px] h-[550px] bg-teal-200/35 rounded-full blur-3xl animate-blob animation-delay-4000 bottom-[-20%] left-[20%]" />

        {/* Subtle moving light layer for depth */}
        <div className="absolute inset-0 bg-gradient-to-t from-white/60 to-transparent backdrop-blur-[2px] animate-softpulse" />
      </div>

      {/* HEADER */}
      <header className="fixed top-0 left-0 right-0 backdrop-blur-lg bg-white/70 border-b border-gray-200 shadow-sm z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">

          {/* Logo Section */}
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-green-600 to-blue-600 text-transparent bg-clip-text">
              {t('kcecAgent')}
            </h1>
          </div>

          {/* Navigation */}
          <nav className="flex items-center space-x-2 bg-white/60 backdrop-blur-md p-1 rounded-xl shadow-inner border border-gray-100">
            {[
              { id: "upload", label: t('uploadTab') },
              { id: "results", label: t('resultsTab') },
              { id: "chat", label: t('chatTab') },
              { id: "history", label: t('historyTab') }
            ].map((tab) => {
              // Disable Results and Chat tabs when there's no project data
              const isDisabled = (tab.id === "results" || tab.id === "chat") && !hasProjectResults;
              
              return (
                <button
                  key={tab.id}
                  id={tab.id === "upload" ? "upload-tab" : undefined}
                  onClick={() => !isDisabled && setActiveTab(tab.id as 'upload' | 'results' | 'chat' | 'history')}
                  disabled={isDisabled}
                  className={`
                    px-4 py-2 rounded-lg text-sm font-medium transition-all
                    ${
                      isDisabled 
                        ? "text-gray-400 cursor-not-allowed" 
                        : activeTab === tab.id
                          ? "bg-gradient-to-r from-green-400 to-blue-400 text-white shadow-md"
                          : "text-gray-600 hover:bg-gray-100"
                    }
                  `}
                >
                  {tab.label}
                </button>
              );
            })}

            {/* Settings Button */}
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="ml-2 w-9 h-9 flex items-center justify-center rounded-lg 
                        bg-gray-100 hover:bg-gray-200 
                        text-gray-600 hover:text-gray-800
                        shadow-inner hover:shadow transition-all"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="w-5 h-5"
              >
                <path
                  fillRule="evenodd"
                  d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z"
                  clipRule="evenodd"
                />
              </svg>
            </button>



          </nav>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="flex-grow pt-24 pb-10"> {/* Added pt-24 to account for fixed header height */}
        <div className="max-w-7xl mx-auto px-6">

          <div className="bg-white/90 backdrop-blur-xl border border-gray-100 shadow-2xl rounded-2xl p-8">

            {/* Upload */}
            {activeTab === "upload" && (
              <UploadSection
                onFileUpload={handleFileUpload}
                isLoading={isLoading}
                progress={progress}
              />
            )}

            {/* Results */}
            {activeTab === "results" && calculationResult && (
              <ResultsSection
                calculationResult={calculationResult}
                selectedHistoryItem={selectedHistory}


                calculateProjectStats={() => calculateProjectStats(calculationResult)}
                calculateFactorStats={() => calculateFactorStats(calculationResult)}

                processProjectHierarchyData={() => calculationResult?.detailed_tree || []}
                processTopSubItemWorks={() => processSubItemWorkData(calculationResult)}
                processEmissionByStage={() => calculationResult?.detailed_tree || []}
                processResourceConsumption={() => processMaterialData(calculationResult)}
              />
            )}


            {/* Chat */}
            {activeTab === "chat" && (
              <ChatSection
                projectName={calculationResult?.project_name || selectedHistory?.project_name || ''}
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                chatMessages={chatMessages}
                setChatMessages={setChatMessages}
                userInput={chatInput}
                setUserInput={setChatInput}
                hasProjectResults={!!calculationResult}
                handleClearChatHistory={handleClearChatHistory}
              />
            )}

            {/* History */}
            {activeTab === "history" && (
              <HistorySection
                history={history}
                onLoadItem={loadHistoryItem}
                selectedHistory={selectedHistory}
                onRefresh={refreshHistory}
              />
            )}

          </div>
        </div>
      </main>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        neo4jConfig={neo4jConfig}
        onUpdateNeo4jConfig={updateNeo4jConfig}
        llmConfig={llmConfig}
        onUpdateLlmConfig={updateLlmConfig}
        agentConfig={agentConfig}
        onUpdateAgentConfig={updateAgentConfig}
      />
    </div>
  );
}

export default function Home() {
  return (
    <LanguageProvider>
      <HomeContent />
    </LanguageProvider>
  );
}
