// 语言翻译文件
export interface Translations {
  [key: string]: {
    zh: string;
    en: string;
  };
}

const translations: Translations = {
  platformName: {
    zh: "交碳智算 CarbonPilot (CPi)",
    en: "CarbonPilot (CPi)"
  },
  platformFullName: {
    zh: "知识增强的建造工程隐含碳排放智能量化平台",
    en: "Knowledge-augmented Construction Embodied Carbon Quantification Agent"
  },
  platformSubtitle: {
    zh: "知识增强的建造工程隐含碳排放智能量化平台",
    en: "Knowledge-augmented Construction Embodied Carbon Quantification Agent Platform"
  },
  uploadTab: {
    zh: "上传",
    en: "Upload"
  },
  resultsTab: {
    zh: "结果",
    en: "Results"
  },
  chatTab: {
    zh: "聊天",
    en: "Chat"
  },
  historyTab: {
    zh: "历史",
    en: "History"
  },
  systemSettings: {
    zh: "系统设置",
    en: "System Settings"
  },
  informationEnhancement: {
    zh: "信息增强",
    en: "Information Enhancement"
  },
  wbsCorrection: {
    zh: "WBS修正",
    en: "WBS Correction"
  },
  semanticSearch: {
    zh: "Agent搜索",
    en: "Agentic Search"
  },
  factorAlignmentMode: {
    zh: "因子对齐模式",
    en: "Factor Alignment Mode"
  },
  memory: {
    zh: "记忆",
    en: "Memory"
  },
  disabled: {
    zh: "禁用",
    en: "Disabled"
  },
  basic: {
    zh: "基础",
    en: "Basic"
  },
  advanced: {
    zh: "高级",
    en: "Advanced"
  },
  enabled: {
    zh: "启用",
    en: "Enabled"
  },
  disabledCaps: {
    zh: "禁用",
    en: "Disabled"
  },
  strict: {
    zh: "严格",
    en: "Strict"
  },
  flexible: {
    zh: "灵活",
    en: "Flexible"
  },
  neo4jDatabaseConfiguration: {
    zh: "Neo4j数据库配置",
    en: "Neo4j Database Configuration"
  },
  largeLanguageModelConfiguration: {
    zh: "大语言模型配置",
    en: "Large Language Model Configuration"
  },
  agentConfiguration: {
    zh: "代理配置",
    en: "Agent Configuration"
  },
  uri: {
    zh: "连接地址",
    en: "URI"
  },
  username: {
    zh: "用户名",
    en: "Username"
  },
  password: {
    zh: "密码",
    en: "Password"
  },
  database: {
    zh: "图数据库",
    en: "Database"
  },
  provider: {
    zh: "提供商",
    en: "Provider"
  },
  modelName: {
    zh: "模型名称",
    en: "Model Name"
  },
  temperature: {
    zh: "温度",
    en: "Temperature"
  },
  maxTokens: {
    zh: "最大输出Tokens",
    en: "Max Tokens"
  },
  apiBase: {
    zh: "API基础地址",
    en: "API Base"
  },
  apiKey: {
    zh: "API密钥",
    en: "API Key"
  },
  language: {
    zh: "语言",
    en: "Language"
  },
  kcecAgent: {
    zh: "交碳智算 CarbonPilot (CPi)",
    en: "CarbonPilot (CPi)"
  },
  intelligentCarbonEmissionCalculator: {
    zh: "知识增强的建造工程隐含碳排放智能量化平台",
    en: "Knowledge-augmented Construction Embodied Carbon Quantification Agent"
  },
  carbonEmissionAnalysis: {
    zh: "碳排放分析",
    en: "Carbon Emission Analysis"
  },
  upload: {
    zh: "上传",
    en: "Upload"
  },
  results: {
    zh: "结果",
    en: "Results"
  },
  chat: {
    zh: "聊天",
    en: "Chat"
  },
  history: {
    zh: "历史",
    en: "History"
  },
  settings: {
    zh: "设置",
    en: "Settings"
  },
  closeSettings: {
    zh: "关闭设置",
    en: "Close Settings"
  },
  saveConfiguration: {
    zh: "保存配置",
    en: "Save Configuration"
  },
  configurationSavedSuccessfully: {
    zh: "配置保存成功！",
    en: "Configuration saved successfully!"
  },
  failedToSaveConfiguration: {
    zh: "配置保存失败，请重试。",
    en: "Failed to save configuration. Please try again."
  },
  chatAboutProject: {
    zh: "关于项目的聊天",
    en: "Chat about your project"
  },
  clearChat: {
    zh: "清除聊天",
    en: "Clear Chat"
  },
  uploadProjectToStartChat: {
    zh: "上传项目以开始与您的碳助手聊天。",
    en: "Upload a project to start chatting with your carbon assistant."
  },
  uploadProject: {
    zh: "上传项目",
    en: "Upload Project"
  },
  runCalculationToEnableChat: {
    zh: "运行碳排放计算以启用聊天。",
    en: "Run carbon emission calculation to enable chat."
  },
  viewResults: {
    zh: "查看结果",
    en: "View Results"
  },
  askAboutCarbonEmissions: {
    zh: "询问有关碳排放的问题。试试：",
    en: "Ask questions about your carbon emissions. Try:"
  },
  whichItemsEmitMostCarbon: {
    zh: '• "哪些项目碳排放最多？"',
    en: '• "Which items emit the most carbon?"'
  },
  showEmissionBreakdown: {
    zh: '• "按阶段显示排放细分。"',
    en: '• "Show emission breakdown by stage."'
  },
  howToReduceEmissions: {
    zh: '• "如何减少这个项目的排放？"',
    en: '• "How can I reduce emissions in this project?"'
  },
  assistantThinking: {
    zh: "助手正在思考...",
    en: "Assistant is thinking..."
  },
  askAboutCarbon: {
    zh: "询问有关碳排放的问题...",
    en: "Ask something about your carbon emissions..."
  },
  sending: {
    zh: "发送中...",
    en: "Sending..."
  },
  send: {
    zh: "发送",
    en: "Send"
  },
  uriPlaceholder: {
    zh: "bolt://localhost:7687",
    en: "bolt://localhost:7687"
  },
  usernamePlaceholder: {
    zh: "neo4j",
    en: "neo4j"
  },
  passwordPlaceholder: {
    zh: "您的密码",
    en: "your-password"
  },
  databasePlaceholder: {
    zh: "neo4j",
    en: "neo4j"
  },
  modelNamePlaceholder: {
    zh: "例如：gpt-4, qwen3-next-80b-a3b-instruct",
    en: "e.g., gpt-4, qwen3-next-80b-a3b-instruct"
  },
  precise: {
    zh: "精确",
    en: "Precise"
  },
  creative: {
    zh: "创意",
    en: "Creative"
  },
  maxTokensPlaceholder: {
    zh: "32768",
    en: "32768"
  },
  apiBasePlaceholder: {
    zh: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    en: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  },
  apiKeyPlaceholder: {
    zh: "sk-...您的API密钥",
    en: "sk-...your-api-key"
  },
  controlInformationEnhancement: {
    zh: "控制如何增强额外信息",
    en: "Control how additional information is enhanced"
  },
  enableWBSCorrection: {
    zh: "启用工作分解结构修正",
    en: "Enable Work Breakdown Structure correction"
  },
  enableSemanticSearch: {
    zh: "启用语义搜索功能",
    en: "Enable semantic search functionality"
  },
  chooseFactorAlignmentMode: {
    zh: "选择因子对齐模式",
    en: "Choose factor alignment mode"
  },
  enableMemoryInformation: {
    zh: "启用记忆信息功能",
    en: "Enable memory information functionality"
  },
  enableMemoryUnit: {
    zh: "启用记忆单元功能",
    en: "Enable memory unit functionality"
  },
  highestSimilarity: {
    zh: "最高相似度",
    en: "Highest similarity"
  },
  llmRerankHighest: {
    zh: "概率最大",
    en: "LLM rerank highest"
  },
  llmRerankAverage: {
    zh: "加权求和",
    en: "LLM rerank average"
  },
  llmRerankLargest: {
    zh: "碳排放最大",
    en: "LLM rerank largest"
  },
  memoryManagement: {
    zh: "记忆管理",
    en: "Memory Management"
  },
  off: {
    zh: "关闭",
    en: "Off"
  },
  on: {
    zh: "开启",
    en: "On"
  },
  choosePreferredLanguage: {
    zh: "选择您偏好的界面语言",
    en: "Choose your preferred interface language"
  },
  // Upload Section
  uploadYourFile: {
    zh: "上传您的建设项目文件以分析碳排放",
    en: "Upload your construction project file to analyze carbon emissions"
  },
  projectFile: {
    zh: "项目文件",
    en: "Project File"
  },
  uploadFile: {
    zh: "上传文件",
    en: "Upload a file"
  },
  orDragAndDrop: {
    zh: "或拖拽文件到此处",
    en: "or drag and drop"
  },
  supportedFormats: {
    zh: "JSON、CSV、XLSX、IFC 格式，最大10MB",
    en: "JSON, CSV, XLSX, IFC up to 10MB"
  },
  removeFile: {
    zh: "移除文件",
    en: "Remove file"
  },
  projectName: {
    zh: "项目名称",
    en: "Project Name"
  },
  enterProjectName: {
    zh: "输入此项目分析的名称",
    en: "Enter a name for this project analysis"
  },
  startAnalysis: {
    zh: "开始分析",
    en: "Start Analysis"
  },
  processing: {
    zh: "处理中...",
    en: "Processing..."
  },
  // Results Section
  calculationResults: {
    zh: "计算结果",
    en: "Calculation Results"
  },
  resultsFor: {
    zh: "",
    en: "Results for"
  },
  totalEmissions: {
    zh: "总排放量 (tCO₂)",
    en: "Total Emissions (tCO2)"
  },
  emissionAnalysis: {
    zh: "排放分析",
    en: "Emission Analysis"
  },
  analyzedOn: {
    zh: "分析于",
    en: "Analyzed on"
  },
  unitProjects: {
    zh: "单位工程",
    en: "Unit Projects"
  },
  carbonFactorsApplied: {
    zh: "应用的碳因子",
    en: "Carbon Factors Applied"
  },
  calculationPerformance: {
    zh: "计算时长",
    en: "Calculation Performance"
  },
  calculationCompletedIn: {
    zh: "计算完成于",
    en: "Calculation completed in:"
  },
  seconds: {
    zh: "秒",
    en: "seconds"
  },
  calculationCompletedAt: {
    zh: "计算完成于",
    en: "Calculation completed at"
  },
  carbonFactors: {
    zh: "碳排放因子",
    en: "Carbon Factors"
  },
  // History Section
  analysisHistory: {
    zh: "分析历史",
    en: "Analysis History"
  },
  analysisHistoryArchive: {
    zh: "分析历史记录",
    en: "Analysis History Archive"
  },
  noAnalysisHistory: {
    zh: "暂无分析历史",
    en: "No Analysis History"
  },
  uploadFirstProject: {
    zh: "上传您的第一个项目开始分析",
    en: "Upload your first project to start analysis"
  },
  calculationDate: {
    zh: "计算日期",
    en: "Calculation Date"
  },
  viewAndLoadPreviousAnalyses: {
    zh: "查看和加载以前的碳排放分析",
    en: "View and load previous carbon emission analyses"
  },
  actions: {
    zh: "操作",
    en: "Actions"
  },
  view: {
    zh: "查看",
    en: "View"
  },
  delete: {
    zh: "删除",
    en: "Delete"
  },
  confirmDeleteProject: {
    zh: "您确定要删除项目 \"{projectName}\" 吗？",
    en: "Are you sure you want to delete project \"{projectName}\"?"
  },
  projectDeletedSuccessfully: {
    zh: "项目 \"{projectName}\" 删除成功",
    en: "Project \"{projectName}\" deleted successfully"
  },
  errorDeletingProject: {
    zh: "删除项目时出错",
    en: "Error deleting project"
  },
  // Charts and Visualizations
  projectHierarchyTree: {
    zh: "项目层级树",
    en: "Project Hierarchy Tree"
  },
  projectHierarchyTreemap: {
    zh: "项目层级树图",
    en: "Project Hierarchy Treemap"
  },
  noValidHierarchyData: {
    zh: "无有效的层级数据",
    en: "No valid hierarchy data available"
  },
  emissionsTco2: {
    zh: "排放量: {value} tCO₂",
    en: "Emissions: {value} tCO₂"
  },
  clickToExpandNextLevel: {
    zh: "点击任意矩形展开下一层级。矩形大小代表碳排放量。",
    en: "Click any rectangle to expand its next level. Rectangle size represents carbon emissions."
  },
  constructionProject: {
    zh: "建设项目",
    en: "Construction Project"
  },
  individualProject: {
    zh: "单项工程",
    en: "Individual Project"
  },
  unitProject: {
    zh: "单位工程",
    en: "Unit Project"
  },
  subDivisionalWork: {
    zh: "分部工程",
    en: "Sub-Divisional Work"
  },
  specialtySubdivision: {
    zh: "子分部工程",
    en: "Specialty Subdivision"
  },
  subItemWork: {
    zh: "分项工程",
    en: "Sub-Item Work"
  },
  resourceItems: {
    zh: "资源项",
    en: "Resource Items"
  },
  top10SubItemWorksByEmissions: {
    zh: "排放量最高的前10项分项工程",
    en: "Top 10 Sub Item Works by Emissions"
  },
  showingTop10SubItemWorks: {
    zh: "显示碳排放量最高的前10项分项工程。",
    en: "Showing the top 10 sub item works with highest carbon emissions."
  },
  emissionsByResourceCategory: {
    zh: "按资源类别划分的排放量",
    en: "Emissions by Resource Category"
  },
  distributionByResourceCategory: {
    zh: "不同资源类别的碳排放分布。",
    en: "Distribution of carbon emissions across different resource categories."
  },
  noEmissionDataAvailable: {
    zh: "无排放数据",
    en: "No emission data available"
  },
  top10ResourceConsumptionItems: {
    zh: "排放量最高的前10项资源消耗项",
    en: "Top 10 Resource Consumption Items"
  },
  showingTop10Resources: {
    zh: "显示所有类别（人力、材料、机械）中碳排放量最高的前十项资源。",
    en: "Showing the top 10 resource items with highest carbon emissions across all categories (Labor, Material, Machinery)."
  },
  noResourceDataAvailable: {
    zh: "无资源数据",
    en: "No resource data available"
  },
  // Memory Management
  editingMemoryEntry: {
    zh: "编辑记忆条目",
    en: "Editing Memory Entry"
  },
  loading: {
    zh: "加载中...",
    en: "Loading..."
  },
  confirmClearMemory: {
    zh: "您确定要清除所有{memoryType}记忆吗？",
    en: "Are you sure you want to clear all {memoryType} memory?"
  },
  failedToFetchMemoryInformation: {
    zh: "获取记忆信息失败",
    en: "Failed to fetch memory information"
  },
  metaFileNotFound: {
    zh: "未找到元文件，继续执行",
    en: "Meta file not found, continuing without it"
  },
  failedToFetchContent: {
    zh: "获取{memoryType}/{fileName}内容失败",
    en: "Failed to fetch content for {memoryType}/{fileName}"
  },
  failedToClearMemory: {
    zh: "清除{memoryType}记忆失败",
    en: "Failed to clear {memoryType} memory"
  },
  failedToUpdateMemory: {
    zh: "更新{memoryType}/{fileName}记忆失败",
    en: "Failed to update {memoryType}/{fileName}"
  },
  failedToUpdateMemoryContent: {
    zh: "更新记忆内容失败",
    en: "Failed to update memory content"
  },
  editingEntry: {
    zh: "正在编辑{type}条目: {key}",
    en: "Editing {type} entry: {key}"
  },
  entryName: {
    zh: "条目名称",
    en: "Entry Name"
  },
  bestItemId: {
    zh: "最佳项ID",
    en: "Best Item ID"
  },
  bestItemName: {
    zh: "最佳项名称",
    en: "Best Item Name"
  },
  unit: {
    zh: "单位",
    en: "Unit"
  },
  introduction: {
    zh: "介绍",
    en: "Introduction"
  },
  fitReason: {
    zh: "匹配原因",
    en: "Fit Reason"
  },
  score: {
    zh: "得分",
    en: "Score"
  },
  entryKey: {
    zh: "条目键",
    en: "Entry Key"
  },
  projectInfo: {
    zh: "项目信息",
    en: "Project Info"
  },
  projectUnit: {
    zh: "项目单位",
    en: "Project Unit"
  },
  targetUnit: {
    zh: "目标单位",
    en: "Target Unit"
  },
  transferFunction: {
    zh: "转换函数",
    en: "Transfer Function"
  },
  reasoning: {
    zh: "推理过程",
    en: "Reasoning"
  },
  cancel: {
    zh: "取消",
    en: "Cancel"
  },
  saveChanges: {
    zh: "保存更改",
    en: "Save Changes"
  },
  viewAndManageSystemMemory: {
    zh: "查看和管理系统记忆存储",
    en: "View and manage system memory storage"
  },
  unitMemory: {
    zh: "单位转换记忆",
    en: "Unit Memory"
  },
  files: {
    zh: "文件",
    en: "files"
  },
  clear: {
    zh: "清除",
    en: "Clear"
  },
  noUnitMemoryFiles: {
    zh: "无单位记忆文件",
    en: "No unit memory files"
  },
  quotaMemory: {
    zh: "工程定额记忆",
    en: "Quota Memory"
  },
  noQuotaMemoryFiles: {
    zh: "无工程定额记忆文件",
    en: "No quota memory files"
  },
  contentColon: {
    zh: "内容: ",
    en: "Content: "
  },
  metadata: {
    zh: "元数据",
    en: "Metadata"
  },
  globalStep: {
    zh: "全局步骤",
    en: "Global Step"
  },
  entries: {
    zh: "条目",
    en: "Entries"
  },
  edit: {
    zh: "编辑",
    en: "Edit"
  },
  usedTimes: {
    zh: "已使用{count}次",
    en: "Used: {count} times"
  },
  strength: {
    zh: "强度",
    en: "Strength"
  },
  lastStep: {
    zh: "最后: 步骤{step}",
    en: "Last: Step {step}"
  },
  func: {
    zh: "函数",
    en: "Func"
  }
};

export default translations;