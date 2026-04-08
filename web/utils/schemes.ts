// Define data types
interface ResourceItem {
  resource_id: string;
  resource_name: string;
  category: string;
  unit: string;
  value: number;
  emission: number;
  emission_unit: string;
}

interface BestFactor {
  id: string;
  name: string;
  amount: number;
  unit: string;
  intro: string;
  similarity: number;
  period: string;
  source: string;
  region: string;
  final_score: number;
  sim_score: number;
  ahp_score: number;
  mode: string;
}

interface ResourceItemWithFactor extends ResourceItem {
  best_factor: BestFactor;
}

interface Properties {
  transfered_unit: string;
  transfered_quantity: number;
  used_quantity: number;
  used_unit: string;
  emission_tco2: number;
}

interface ChildNode {
  level: string;
  name: string;
  description: string;
  scale: {
    unit: string;
    quantity: number;
    note: string;
  };
  properties?: Properties;
  resource_items?: ResourceItemWithFactor[];
  children?: ChildNode[];
}

interface CalculationResult {
  project_name?: string; // 添加可选的项目名称字段
  total_emission: number;
  processed_items: number;
  detailed_tree: ChildNode[];
}

// Add new interfaces for our statistics
interface ProjectEmission {
  name: string;
  emission: number;
}

interface ResourceCategoryEmission {
  category: string;
  emission: number;
  count: number;
}

interface MaterialEmission {
  name: string;
  emission: number;
  category: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface LLMConfig {
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  api_base: string;
  api_key: string;
}

// Define data types
interface ResourceItem {
  resource_id: string;
  resource_name: string;
  category: string;
  unit: string;
  value: number;
  emission: number;
  emission_unit: string;
}

interface BestFactor {
  id: string;
  name: string;
  amount: number;
  unit: string;
  intro: string;
  similarity: number;
  period: string;
  source: string;
  region: string;
  final_score: number;
  sim_score: number;
  ahp_score: number;
  mode: string;
}

interface ResourceItemWithFactor extends ResourceItem {
  best_factor: BestFactor;
}

interface Properties {
  transfered_unit: string;
  transfered_quantity: number;
  used_quantity: number;
  used_unit: string;
  emission_tco2: number;
}

interface ChildNode {
  level: string;
  name: string;
  description: string;
  scale: {
    unit: string;
    quantity: number;
    note: string;
  };
  properties?: Properties;
  resource_items?: ResourceItemWithFactor[];
  children?: ChildNode[];
}

interface CalculationResult {
  project_name?: string; // 添加可选的项目名称字段
  total_emission: number;
  processed_items: number;
  detailed_tree: ChildNode[];
}

// Add new interfaces for our statistics
interface ProjectEmission {
  name: string;
  emission: number;
}

interface ResourceCategoryEmission {
  category: string;
  emission: number;
  count: number;
}

interface MaterialEmission {
  name: string;
  emission: number;
  category: string;
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface ChatSectionProps {
  projectName: string
  activeTab: string
  setActiveTab: (tab: 'upload' | 'results' | 'chat' | 'history') => void
  chatMessages: ChatMessage[]
  setChatMessages: (msg: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void
  userInput: string
  setUserInput: (input: string) => void
  hasProjectResults: boolean
  handleClearChatHistory: () => void
  calculationResult?: CalculationResult | null
}


interface LLMConfig {
  provider: string;
  model_name: string;
  temperature: number;
  max_tokens: number;
  api_base: string;
  api_key: string;
}

interface AgentConfig {
  information_enhancement: number;
  wbs_correction: number;
  agnetic_search: number;
  factor_alignment_mode: number;
  memory_information: number;
  memory_unit: number;
}

interface Neo4jConfig {
  uri: string;
  username: string;
  password: string;
  database: string;
}

// Export all interfaces to make this file a module
export type {
  ResourceItem,
  BestFactor,
  ResourceItemWithFactor,
  Properties,
  ChildNode,
  CalculationResult,
  ProjectEmission,
  ResourceCategoryEmission,
  MaterialEmission,
  ChatMessage,
  ChatSectionProps,
  LLMConfig,
  AgentConfig,
  Neo4jConfig
};