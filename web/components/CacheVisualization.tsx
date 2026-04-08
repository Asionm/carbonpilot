'use client'

import React, { useState, useEffect } from 'react'
import { api } from '../utils/api'
import { useLanguage } from '../utils/LanguageContext'

// Interface for memory information
interface MemoryInfo {
  quota: {
    path: string;
    file_count: number;
    exists?: boolean;
  };
  unit: {
    path: string;
    file_count: number;
    exists?: boolean;
  };
}

// Interface for quota memory entry
interface QuotaEntry {
  best_item: {
    id: string;
    name: string;
    properties: {
      id: string;
      unit: string;
      name: string;
      intro: string;
    };
    score: number;
    fit_reason: string;
  };
}

// Interface for quota memory content
interface QuotaMemoryContent {
  meta: {
    global_step: number;
  };
  entries: {
    [key: string]: QuotaEntry;
  };
}

// Interface for unit memory content
interface UnitMemoryContent {
  [key: string]: {
    project_unit: string;
    target_unit: string;
    project_info: string;
    transfer_func: string;
    reasoning: string;
  };
}

// Memory visualization component for managing system memory storage
export default function MemoryVisualization() {
  const { t } = useLanguage()
  const [memoryInfo, setMemoryInfo] = useState<MemoryInfo | null>(null)
  const [selectedMemory, setSelectedMemory] = useState<string | null>(null)
  const [memoryFiles, setMemoryFiles] = useState<{[key: string]: any}>({})
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [editingEntry, setEditingEntry] = useState<{type: string, key: string, data: any} | null>(null)

  // Fetch memory information on component mount
  useEffect(() => {
    fetchMemoryInfo()
  }, [])

  // Fetch memory status from API
  const fetchMemoryInfo = async () => {
    try {
      setLoading(true)
      const response = await api.memory.getStatus()
      setMemoryInfo(response.data)
      setError(null)
    } catch (err) {
      setError(t('failedToFetchMemoryInformation'))
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  // Fetch content of a specific memory file
  const fetchMemoryFileContent = async (memoryType: string, fileName: string) => {
    try {
      const response = await api.memory.getContent(memoryType, fileName)
      setMemoryFiles(prev => ({
        ...prev,
        [`${memoryType}/${fileName}`]: response.data
      }))
      
      // If we're fetching unit conversions, also fetch the meta file
      if (memoryType === 'unit' && fileName === 'unit_conversions_cache.json') {
        try {
          const metaResponse = await api.memory.getContent('unit', '_unit_memory_meta.json');
          setMemoryFiles(prev => ({
            ...prev,
            [`unit/_unit_memory_meta.json`]: metaResponse.data
          }));
        } catch (err) {
          // Meta file might not exist, that's okay
          console.debug(t('metaFileNotFound'));
        }
      }
    } catch (err) {
      console.error(t('failedToFetchContent').replace('{memoryType}', memoryType).replace('{fileName}', fileName), err)
    }
  }

  // Handle click on a memory file
  const handleMemoryFileClick = (memoryType: string, fileName: string) => {
    const key = `${memoryType}/${fileName}`
    if (!memoryFiles[key]) {
      fetchMemoryFileContent(memoryType, fileName)
    }
    setSelectedMemory(key)
    setEditingEntry(null)
  }

  // Clear a specific type of memory
  const clearMemory = async (memoryType: string) => {
    if (!confirm(t('confirmClearMemory').replace('{memoryType}', memoryType))) return;
    
    try {
      await api.memory.clear(memoryType)
      fetchMemoryInfo()
      setSelectedMemory(null)
      setMemoryFiles({})
      setEditingEntry(null)
    } catch (err) {
      console.error(t('failedToClearMemory').replace('{memoryType}', memoryType), err)
      setError(t('failedToClearMemory').replace('{memoryType}', memoryType))
    }
  }

  // Update memory content
  const updateMemoryContent = async (memoryType: string, fileName: string, content: any) => {
    try {
      await api.memory.updateContent(memoryType, fileName, content)
      // Refresh the content
      await fetchMemoryFileContent(memoryType, fileName)
      setEditingEntry(null)
    } catch (err) {
      console.error(t('failedToUpdateMemory').replace('{memoryType}', memoryType).replace('{fileName}', fileName), err)
      setError(t('failedToUpdateMemoryContent'))
    }
  }

  // Start editing a quota entry
  const startEditingQuotaEntry = (entryKey: string, entryData: QuotaEntry) => {
    setEditingEntry({
      type: 'quota',
      key: entryKey,
      data: {...entryData}
    });
  }

  // Start editing a unit entry
  const startEditingUnitEntry = (entryKey: string, entryData: any) => {
    setEditingEntry({
      type: 'unit',
      key: entryKey,
      data: {...entryData}
    });
  }

  // Handle input changes during editing
  const handleEditChange = (field: string, value: any, nestedField?: string) => {
    if (!editingEntry) return;
    
    setEditingEntry(prev => {
      if (!prev) return null;
      
      const newData = {...prev.data};
      if (nestedField) {
        newData[field] = {
          ...newData[field],
          [nestedField]: value
        };
      } else {
        newData[field] = value;
      }
      
      return {
        ...prev,
        data: newData
      };
    });
  }

  // Save edited entry
  const saveEditedEntry = async () => {
    if (!editingEntry || !selectedMemory) return;
    
    const [memoryType, fileName] = selectedMemory.split('/');
    const content = {...memoryFiles[selectedMemory]};
    
    if (editingEntry.type === 'quota') {
      content.entries[editingEntry.key] = editingEntry.data;
    } else if (editingEntry.type === 'unit') {
      content[editingEntry.key] = editingEntry.data;
    }
    
    await updateMemoryContent(memoryType, fileName, content);
  }

  // Cancel editing
  const cancelEditing = () => {
    setEditingEntry(null);
  }

  // Show loading state
  if (loading) {
    return (
      <div className="flex justify-center items-center h-32">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    )
  }

  // Show error message
  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-center">
          <svg className="h-5 w-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <p className="ml-2 text-sm text-red-700">{error}</p>
        </div>
      </div>
    )
  }

  // Editing view
  if (editingEntry && selectedMemory && memoryFiles[selectedMemory]) {
    const content = memoryFiles[selectedMemory];
    
    return (
      <div className="bg-white rounded-2xl shadow-xl p-6">
        <div className="mb-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-2xl font-bold text-gray-800 mb-2">{t('editingMemoryEntry')}</h2>
              <p className="text-gray-600">
                {t('editingEntry').replace('{type}', editingEntry.type).replace('{key}', editingEntry.key)}
              </p>
            </div>
            <button
              onClick={cancelEditing}
              className="px-4 py-2 text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>

        <div className="border border-gray-200 rounded-xl p-4 mb-6">
          {editingEntry.type === 'quota' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('entryName')}</label>
                <input
                  type="text"
                  value={editingEntry.key}
                  disabled
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-100"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('bestItemId')}</label>
                <input
                  type="text"
                  value={editingEntry.data.best_item?.id || ''}
                  onChange={(e) => handleEditChange('best_item', e.target.value, 'id')}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('bestItemName')}</label>
                <input
                  type="text"
                  value={editingEntry.data.best_item?.name || ''}
                  onChange={(e) => handleEditChange('best_item', e.target.value, 'name')}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('unit')}</label>
                <input
                  type="text"
                  value={editingEntry.data.best_item?.properties?.unit || ''}
                  onChange={(e) => handleEditChange('best_item', {...editingEntry.data.best_item, properties: {...editingEntry.data.best_item.properties, unit: e.target.value}})}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('introduction')}</label>
                <textarea
                  value={editingEntry.data.best_item?.properties?.intro || ''}
                  onChange={(e) => handleEditChange('best_item', {...editingEntry.data.best_item, properties: {...editingEntry.data.best_item.properties, intro: e.target.value}})}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('fitReason')}</label>
                <textarea
                  value={editingEntry.data.best_item?.fit_reason || ''}
                  onChange={(e) => handleEditChange('best_item', {...editingEntry.data.best_item, fit_reason: e.target.value})}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('score')}</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={editingEntry.data.best_item?.score || 0}
                  onChange={(e) => handleEditChange('best_item', {...editingEntry.data.best_item, score: parseFloat(e.target.value)})}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>
          )}

          {editingEntry.type === 'unit' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('entryKey')}</label>
                <input
                  type="text"
                  value={editingEntry.key}
                  disabled
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-100"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('projectInfo')}</label>
                <input
                  type="text"
                  value={editingEntry.data.project_info || ''}
                  onChange={(e) => handleEditChange('project_info', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('projectUnit')}</label>
                <input
                  type="text"
                  value={editingEntry.data.project_unit || ''}
                  onChange={(e) => handleEditChange('project_unit', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('targetUnit')}</label>
                <input
                  type="text"
                  value={editingEntry.data.target_unit || ''}
                  onChange={(e) => handleEditChange('target_unit', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('transferFunction')}</label>
                <input
                  type="text"
                  value={editingEntry.data.transfer_func || ''}
                  onChange={(e) => handleEditChange('transfer_func', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">{t('reasoning')}</label>
                <textarea
                  value={editingEntry.data.reasoning || ''}
                  onChange={(e) => handleEditChange('reasoning', e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end space-x-3">
          <button
            onClick={cancelEditing}
            className="px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors"
          >
            {t('cancel')}
          </button>
          <button
            onClick={saveEditedEntry}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            {t('saveChanges')}
          </button>
        </div>
      </div>
    );
  }

  return (
      <div className="bg-white rounded-2xl shadow-xl p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-800 mb-2">{t('memoryManagement')}</h2>
          <p className="text-gray-600">{t('viewAndManageSystemMemory')}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Unit Memory Card */}
          <div className="border border-gray-200 rounded-xl overflow-hidden">
            <div className="bg-gradient-to-r from-blue-500 to-indigo-600 px-4 py-3">
              <h3 className="text-lg font-semibold text-white">{t('unitMemory')}</h3>
            </div>
            
            <div className="p-4">
              {memoryInfo?.unit && memoryInfo.unit.file_count > 0 ? (
                <>
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-sm text-gray-600">
                      {memoryInfo.unit.file_count} {t('files')}
                    </span>
                    <button 
                      onClick={() => clearMemory('unit')}
                      className="text-xs px-3 py-1 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors"
                    >
                      {t('clear')}
                    </button>
                  </div>
                  
                  <div className="max-h-40 overflow-y-auto border border-gray-200 rounded-lg">
                    <ul className="divide-y divide-gray-200">
                      <li>
                        <button
                          onClick={() => handleMemoryFileClick('unit', 'unit_conversions_cache.json')}
                          className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors ${
                            selectedMemory === `unit/unit_conversions_cache.json` ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                          }`}
                        >
                          unit_conversions_cache.json
                        </button>
                      </li>
                    </ul>
                  </div>
                </>
              ) : (
                <div className="text-center py-4">
                  <p className="text-gray-500 text-sm">{t('noUnitMemoryFiles')}</p>
                </div>
              )}
            </div>
          </div>

          {/* Quota Memory Card */}
          <div className="border border-gray-200 rounded-xl overflow-hidden">
            <div className="bg-gradient-to-r from-emerald-500 to-teal-600 px-4 py-3">
              <h3 className="text-lg font-semibold text-white">{t('quotaMemory')}</h3>
            </div>
            
            <div className="p-4">
              {memoryInfo?.quota && memoryInfo.quota.file_count > 0 ? (
                <>
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-sm text-gray-600">
                      {memoryInfo.quota.file_count} {t('files')}
                    </span>
                    <button 
                      onClick={() => clearMemory('quota')}
                      className="text-xs px-3 py-1 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors"
                    >
                      {t('clear')}
                    </button>
                  </div>
                  
                  <div className="max-h-40 overflow-y-auto border border-gray-200 rounded-lg">
                    <ul className="divide-y divide-gray-200">
                      <li>
                        <button
                          onClick={() => handleMemoryFileClick('quota', 'name_based_cache.json')}
                          className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors ${
                            selectedMemory === `quota/name_based_cache.json` ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                          }`}
                        >
                          name_based_cache.json
                        </button>
                      </li>
                    </ul>
                  </div>
                </>
              ) : (
                <div className="text-center py-4">
                  <p className="text-gray-500 text-sm">{t('noQuotaMemoryFiles')}</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* File Content Viewer */}
        {selectedMemory && memoryFiles[selectedMemory] && !editingEntry && (
          <div className="mt-6 border border-gray-200 rounded-xl overflow-hidden">
            <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex justify-between items-center">
              <h3 className="font-medium text-gray-800">{t('contentColon')} {selectedMemory}</h3>
              <button
                onClick={() => setSelectedMemory(null)}
                className="text-gray-500 hover:text-gray-700"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
            
            <div className="p-4 max-h-96 overflow-y-auto">
              {selectedMemory === 'quota/name_based_cache.json' && (
                <div className="space-y-4">
                  <div className="bg-blue-50 p-3 rounded-lg">
                    <h4 className="font-medium text-blue-800">{t('metadata')}</h4>
                    <p className="text-sm text-blue-600">
                      {t('globalStep')}: {(memoryFiles[selectedMemory] as QuotaMemoryContent)?.meta?.global_step || 'N/A'}
                    </p>
                  </div>
                  
                  <div>
                    <h4 className="font-medium text-gray-800 mb-2">{t('entries')} ({Object.keys((memoryFiles[selectedMemory] as QuotaMemoryContent)?.entries || {}).length})</h4>
                    <div className="space-y-3 max-h-60 overflow-y-auto">
                      {Object.entries((memoryFiles[selectedMemory] as QuotaMemoryContent)?.entries || {}).map(([key, entry]) => (
                        <div key={key} className="border border-gray-200 rounded-lg p-3">
                          <div className="flex justify-between">
                            <h5 className="font-medium text-gray-800">{key}</h5>
                            <button
                              onClick={() => startEditingQuotaEntry(key, entry)}
                              className="text-sm px-2 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
                            >
                              {t('edit')}
                            </button>
                          </div>
                          <p className="text-sm text-gray-600 mt-1">
                            {entry.best_item?.properties?.name}
                          </p>
                          <div className="flex justify-between mt-2">
                            <span className="text-xs bg-gray-100 px-2 py-1 rounded">
                              {entry.best_item?.properties?.unit}
                            </span>
                            <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                              {t('score')}: {entry.best_item?.score?.toFixed(2)}
                            </span>
                          </div>
                          {/* Memory Information */}
                          {entry.memory && (
                            <div className="mt-2 pt-2 border-t border-gray-100">
                              <div className="flex justify-between text-xs">
                                <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded">
                                  {t('usedTimes').replace('{count}', entry.memory.use_count)}
                                </span>
                                <span className="bg-yellow-100 text-yellow-800 px-2 py-1 rounded">
                                  {t('strength')}: {entry.memory.strength.toFixed(2)}
                                </span>
                                <span className="bg-indigo-100 text-indigo-800 px-2 py-1 rounded">
                                  {t('lastStep').replace('{step}', entry.memory.last_used_step)}
                                </span>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              
              {selectedMemory === 'unit/unit_conversions_cache.json' && (
              <div className="space-y-4">
                <div>
                  <h4 className="font-medium text-gray-800 mb-2">
                    {t('entries')} ({Object.keys(memoryFiles[selectedMemory] || {}).length})
                  </h4>
                  <div className="space-y-3 max-h-60 overflow-y-auto">
                    {Object.entries(memoryFiles[selectedMemory] || {}).map(([key, entry]: [string, any]) => {
                      // Try to get access count from meta file if available
                      const metaFile = memoryFiles['unit/_unit_memory_meta.json'];
                      const accessCount = metaFile?.access_count?.[key] || 0;
                      
                      return (
                        <div key={key} className="border border-gray-200 rounded-lg p-3">
                          <div className="flex justify-between">
                            <h5 className="font-medium text-gray-800 truncate max-w-xs">{key}</h5>
                            <button
                              onClick={() => startEditingUnitEntry(key, entry)}
                              className="text-sm px-2 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
                            >
                              {t('edit')}
                            </button>
                          </div>
                          <p className="text-sm text-gray-600 mt-1 truncate">
                            {entry.project_info}
                          </p>
                          <div className="flex justify-between mt-2 text-xs">
                            <span className="bg-gray-100 px-2 py-1 rounded">
                              {entry.project_unit} → {entry.target_unit}
                            </span>
                          </div>
                          {/* Memory Information */}
                          <div className="mt-2 pt-2 border-t border-gray-100">
                            <div className="flex justify-between text-xs">
                              <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded">
                                {t('usedTimes').replace('{count}', accessCount)}
                              </span>
                              <span className="bg-indigo-100 text-indigo-800 px-2 py-1 rounded">
                                {t('func')}: {entry.transfer_func}
                              </span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
            </div>
          </div>
        )}
      </div>
    )
}