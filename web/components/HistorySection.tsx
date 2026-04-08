'use client'

import { api } from '../utils/api'
import { useLanguage } from '../utils/LanguageContext'

// Interface for history item
interface HistoryItem {
  project_name: string;
  total_emission: number | string;
  calculation_date: number;
}

// Props for HistorySection component
interface HistorySectionProps {
  history: HistoryItem[];
  onLoadItem: (item: HistoryItem) => void;
  selectedHistory: HistoryItem | null;
  onRefresh?: () => void; // 新增刷新回调
}

// History section component for displaying analysis history
export default function HistorySection({ 
  history, 
  onLoadItem,
  selectedHistory,
  onRefresh
}: HistorySectionProps) {
  const { t } = useLanguage()

  // Delete project handler
  const handleDelete = async (projectName: string) => {
    const confirmed = confirm(t('confirmDeleteProject').replace('{projectName}', projectName))
    if (!confirmed) return;

    try {
      await api.history.delete(projectName);
      alert(t('projectDeletedSuccessfully').replace('{projectName}', projectName));
      onRefresh?.(); // 刷新父级
    } catch (err) {
      console.error(err);
      alert(t('errorDeletingProject'));
    }
  };


  return (
    <div className="bg-white rounded-2xl shadow-xl p-6">
      <div className="mb-8">
        <h2 className="text-4xl font-bold text-green-700 mb-2">{t('analysisHistoryArchive')}</h2>
        <p className="text-gray-600">{t('viewAndLoadPreviousAnalyses')}</p>
      </div>
      
      {history.length === 0 ? (
        <div className="text-center py-16">
          <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-blue-100 mb-6">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">{t('noAnalysisHistory')}</h3>
          <p className="text-gray-500 mb-6">{t('uploadFirstProject')}</p>
          <button
            onClick={() => document.getElementById('upload-tab')?.click()}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            {t('startAnalysis')}
          </button>
        </div>
      ) : (
        <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 rounded-lg">
          <table className="min-w-full divide-y divide-gray-300">
            <thead className="bg-gray-50">
              <tr>
                <th className="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-6">
                  {t('projectName')}
                </th>
                <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                  {t('totalEmissions')}
                </th>
                <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                  {t('calculationDate')}
                </th>
                <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">
                  {t('actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {history.map((item) => (
                <tr 
                  key={item.project_name} 
                  className={
                    selectedHistory?.project_name === item.project_name 
                    ? 'bg-blue-50' 
                    : 'hover:bg-gray-50'
                  }
                >
                  <td className="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-6">
                    {item.project_name}
                  </td>

                  <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                    {typeof item.total_emission === 'number' 
                      ? item.total_emission.toFixed(2) 
                      : item.total_emission}
                  </td>

                  <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                    {new Date(item.calculation_date * 1000).toLocaleDateString()}
                  </td>

                  <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500 flex space-x-4">

                    {/* Load Button */}
                    <button
                      onClick={() => onLoadItem(item)}
                      className="text-blue-600 hover:text-blue-900 flex items-center"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                        <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
                        <path fillRule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
                      </svg>
                      {t('view')}
                    </button>

                    {/* Delete Button */}
                    <button
                      onClick={() => handleDelete(item.project_name)}
                      className="text-red-600 hover:text-red-800 flex items-center"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" 
                        className="h-4 w-4 mr-1" fill="none" 
                        viewBox="0 0 24 24" stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2M4 7h16" 
                        />
                      </svg>
                      {t('delete')}
                    </button>

                  </td>

                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}