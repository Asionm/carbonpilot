'use client'

import React, { useEffect, useRef } from 'react'
import { Neo4jConfig, LLMConfig, AgentConfig } from '../utils/schemes'
import { api } from '../utils/api'
import MemoryVisualization from './CacheVisualization'
import { useLanguage } from '../utils/LanguageContext'

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  neo4jConfig: Neo4jConfig;
  onUpdateNeo4jConfig: (config: Partial<Neo4jConfig>) => void;
  llmConfig: LLMConfig;
  onUpdateLlmConfig: (config: Partial<LLMConfig>) => void;
  agentConfig: AgentConfig;
  onUpdateAgentConfig: (config: Partial<AgentConfig>) => void;
}

export default function SettingsModal({ 
  isOpen, 
  onClose,
  neo4jConfig,
  onUpdateNeo4jConfig,
  llmConfig,
  onUpdateLlmConfig,
  agentConfig,
  onUpdateAgentConfig
}: SettingsModalProps) {
  const modalRef = useRef<HTMLDivElement>(null)
  const { language, setLanguage, t } = useLanguage()

  // Handle escape key to close modal
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    }

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = 'unset'
    }
  }, [isOpen, onClose])

  // Handle click outside to close modal
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(event.target as Node)) {
        onClose()
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div 
        ref={modalRef}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <div className="sticky top-0 bg-white border-b border-gray-200 p-6 flex justify-between items-center rounded-t-2xl">
          <h2 className="text-2xl font-bold text-gray-900">{t('systemSettings')}</h2>
          <button 
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 p-2 rounded-full hover:bg-gray-100 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-8">
          {/* Neo4j Configuration */}
          <div className="bg-gray-50 rounded-xl p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-purple-500" viewBox="0 0 20 20" fill="currentColor">
                <path d="M2 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1H3a1 1 0 01-1-1V4zM8 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1H9a1 1 0 01-1-1V4zM15 3a1 1 0 00-1 1v12a1 1 0 001 1h2a1 1 0 001-1V4a1 1 0 00-1-1h-2z" />
              </svg>
              {t('neo4jDatabaseConfiguration')}
            </h3>
            
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('uri')}</label>
                <input
                  type="text"
                  value={neo4jConfig.uri}
                  onChange={(e) => onUpdateNeo4jConfig({ uri: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('uriPlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('username')}</label>
                <input
                  type="text"
                  value={neo4jConfig.username}
                  onChange={(e) => onUpdateNeo4jConfig({ username: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('databasePlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('password')}</label>
                <input
                  type="password"
                  value={neo4jConfig.password}
                  onChange={(e) => onUpdateNeo4jConfig({ password: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('passwordPlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('database')}</label>
                <input
                  type="text"
                  value={neo4jConfig.database}
                  onChange={(e) => onUpdateNeo4jConfig({ database: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('databasePlaceholder')}
                />
              </div>
            </div>
          </div>

          {/* LLM Configuration */}
          <div className="bg-gray-50 rounded-xl p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-blue-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
              {t('largeLanguageModelConfiguration')}
            </h3>
            
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('provider')}</label>
                <select
                  value={llmConfig.provider}
                  onChange={(e) => onUpdateLlmConfig({ provider: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                >
                  <option value="openai">OpenAI</option>
                  <option value="ollama">Ollama</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('modelName')}</label>
                <input
                  type="text"
                  value={llmConfig.model_name}
                  onChange={(e) => onUpdateLlmConfig({ model_name: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('modelNamePlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('temperature')}: <span className="font-semibold text-blue-600">{llmConfig.temperature}</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={llmConfig.temperature}
                  onChange={(e) => onUpdateLlmConfig({ temperature: parseFloat(e.target.value) })}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>{t('precise')}</span>
                  <span>{t('creative')}</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('maxTokens')}</label>
                <input
                  type="number"
                  value={llmConfig.max_tokens}
                  onChange={(e) => onUpdateLlmConfig({ max_tokens: parseInt(e.target.value) })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('maxTokensPlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('apiBase')}</label>
                <input
                  type="text"
                  value={llmConfig.api_base}
                  onChange={(e) => onUpdateLlmConfig({ api_base: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('apiBasePlaceholder')}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('apiKey')}</label>
                <input
                  type="password"
                  value={llmConfig.api_key}
                  onChange={(e) => onUpdateLlmConfig({ api_key: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition"
                  placeholder={t('apiKeyPlaceholder')}
                />
              </div>
            </div>
          </div>

          {/* Language Settings */}
          <div className="bg-gray-50 rounded-xl p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-indigo-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M7 2a1 1 0 011 1v1h3a1 1 0 110 2H9.578a18.87 18.87 0 01-1.724 4.78c.29.354.596.696.914 1.026a1 1 0 11-1.44 1.389c-.188-.196-.373-.396-.554-.6a19.098 19.098 0 01-3.107 3.567 1 1 0 01-1.334-1.49 17.087 17.087 0 003.13-3.733 18.992 18.992 0 01-1.487-2.494 1 1 0 111.79-.89c.234.47.489.928.764 1.372.417-.934.752-1.913.997-2.927H3a1 1 0 110-2h3V3a1 1 0 011-1zm6 6a1 1 0 01.894.553l2.991 5.982a.869.869 0 01.02.037l.99 1.98a1 1 0 11-1.79.895L15.383 16h-4.764l-.724 1.447a1 1 0 11-1.788-.894l.99-1.98.019-.038 2.99-5.982A1 1 0 0113 8zm-1.382 6h2.764L13 11.236 11.618 14z" clipRule="evenodd" />
              </svg>
              {t('language')}
            </h3>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    {t('language')} / 语言
                  </label>
                  <p className="text-xs text-gray-500 mt-1">{t('choosePreferredLanguage')} / 选择您偏好的界面语言</p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => setLanguage('en')}
                    className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                      language === 'en'
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    English
                  </button>
                  <button
                    onClick={() => setLanguage('zh')}
                    className={`px-4 py-2 text-sm rounded-lg transition-colors ${
                      language === 'zh'
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    中文
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Agent Configuration */}
          <div className="bg-gray-50 rounded-xl p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-emerald-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M12.586 4.586a2 2 0 112.828 2.828l-3 3a2 2 0 01-2.828 0 1 1 0 00-1.414 1.414 4 4 0 005.656 0l3-3a4 4 0 00-5.656-5.656l-1.5 1.5a1 1 0 101.414 1.414l1.5-1.5zm-5 5a2 2 0 012.828 0 1 1 0 101.414-1.414 4 4 0 00-5.656 0l-3 3a4 4 0 105.656 5.656l1.5-1.5a1 1 0 10-1.414-1.414l-1.5 1.5a2 2 0 11-2.828-2.828l3-3z" clipRule="evenodd" />
              </svg>
              {t('agentConfiguration')}
            </h3>
            
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    {t('informationEnhancement')}
                  </label>
                  <p className="text-xs text-gray-500 mt-1">{t('controlInformationEnhancement')}</p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => onUpdateAgentConfig({ information_enhancement: 0 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.information_enhancement === 0
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('off')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ information_enhancement: 1 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.information_enhancement >= 1
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('on')}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    {t('wbsCorrection')}
                  </label>
                  <p className="text-xs text-gray-500 mt-1">{t('enableWBSCorrection')}</p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => onUpdateAgentConfig({ wbs_correction: 0 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.wbs_correction === 0
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('off')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ wbs_correction: 1 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.wbs_correction === 1
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('on')}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    {t('semanticSearch')}
                  </label>
                  <p className="text-xs text-gray-500 mt-1">{t('enableSemanticSearch')}</p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => onUpdateAgentConfig({ agnetic_search: 0 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.agnetic_search === 0
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('off')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ agnetic_search: 1 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.agnetic_search === 1
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('on')}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">{t('factorAlignmentMode')}</label>
                <div className="grid grid-cols-4 gap-2">
                  <button
                    onClick={() => onUpdateAgentConfig({ factor_alignment_mode: 0 })}
                    className={`px-3 py-2 text-sm rounded-lg transition-colors ${
                      agentConfig.factor_alignment_mode === 0
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('highestSimilarity')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ factor_alignment_mode: 1 })}
                    className={`px-3 py-2 text-sm rounded-lg transition-colors ${
                      agentConfig.factor_alignment_mode === 1
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('llmRerankHighest')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ factor_alignment_mode: 2 })}
                    className={`px-3 py-2 text-sm rounded-lg transition-colors ${
                      agentConfig.factor_alignment_mode === 2
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('llmRerankAverage')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ factor_alignment_mode: 3 })}
                    className={`px-3 py-2 text-sm rounded-lg transition-colors ${
                      agentConfig.factor_alignment_mode === 3
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('llmRerankLargest')}
                  </button>
                </div>
                <p className="text-xs text-gray-500 mt-1">{t('chooseFactorAlignmentMode')}</p>
                
                {/* Warning message for API compatibility */}
                <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-xs text-yellow-700">
                    {'Warning: When the API interface does not support outputting top_logprobs (probability information), please only select the highestSimilarity mode, otherwise calculations will not work properly.'}
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    {t('memory')}
                  </label>
                  <p className="text-xs text-gray-500 mt-1">{t('enableMemoryInformation')}</p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => onUpdateAgentConfig({ memory_information: 0 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.memory_information === 0
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('off')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ memory_information: 1 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.memory_information === 1
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('on')}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-gray-700">
                    {t('memory')} Unit
                  </label>
                  <p className="text-xs text-gray-500 mt-1">{t('enableMemoryUnit')}</p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => onUpdateAgentConfig({ memory_unit: 0 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.memory_unit === 0
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('off')}
                  </button>
                  <button
                    onClick={() => onUpdateAgentConfig({ memory_unit: 1 })}
                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                      agentConfig.memory_unit === 1
                        ? 'bg-blue-500 text-white shadow'
                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    }`}
                  >
                    {t('on')}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Memory Management */}
          <div className="bg-gray-50 rounded-xl p-5 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2 text-amber-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
              </svg>
              {t('memoryManagement')}
            </h3>
            
            <div className="pt-2">
              <MemoryVisualization />
            </div>
          </div>
        </div>

        <div className="sticky bottom-0 bg-white border-t border-gray-200 p-6 rounded-b-2xl">
          <div className="flex justify-end space-x-3">
            <button
              onClick={async () => {
                try {
                  // 保存配置到后端
                  await api.config.update({
                    neo4j_config: neo4jConfig,
                    llm_config: llmConfig,
                    agent_config: agentConfig
                  });
                  alert(t('configurationSavedSuccessfully'));
                } catch (error) {
                  console.error('Failed to save configuration:', error);
                  alert(t('failedToSaveConfiguration'));
                }
              }}
              className="px-6 py-3 bg-gradient-to-r from-green-500 to-emerald-500 text-white font-medium rounded-lg shadow hover:from-green-600 hover:to-emerald-600 transition-all"
            >
              {t('saveConfiguration')}
            </button>
            <button
              onClick={onClose}
              className="px-6 py-3 bg-gradient-to-r from-blue-500 to-emerald-500 text-white font-medium rounded-lg shadow hover:from-blue-600 hover:to-emerald-600 transition-all"
            >
              {t('closeSettings')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}