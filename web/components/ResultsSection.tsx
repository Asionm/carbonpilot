'use client'

import ProjectHierarchyTree from './ProjectHierarchyTree'
import TopSubItemWorksChart from './TopSubItemWorksChart'
import EmissionByStageChart from './EmissionByStageChart'
import ResourceConsumptionChart from './ResourceConsumptionChart'
import { useLanguage } from '../utils/LanguageContext'

interface ResultsSectionProps {
  calculationResult: any;
  selectedHistoryItem: any;

  calculateProjectStats: () => { projects: number; subProjects: number; subItems: number };
  calculateFactorStats: () => number;
  processProjectHierarchyData: () => any;
  processTopSubItemWorks: () => any[];
  processEmissionByStage: () => any[];
  processResourceConsumption: () => any[];
}

export default function ResultsSection({
  calculationResult,
  selectedHistoryItem,

  calculateProjectStats,
  calculateFactorStats,
  processProjectHierarchyData,
  processTopSubItemWorks,
  processEmissionByStage,
  processResourceConsumption
}: ResultsSectionProps) {
  const { t } = useLanguage()
  // Get calculation time if available
  const calculationTime = calculationResult?.summary_emission?.calculation_time || 
                         calculationResult?.calculation_time || 
                         'Unknown';

  return (
    <div className="bg-white rounded-2xl shadow-xl p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-800">
          {selectedHistoryItem ? `${t('resultsFor')} ${selectedHistoryItem.project_name}` : t('calculationResults')}
        </h2>
        {selectedHistoryItem && (
          <div className="text-sm text-gray-500">
            {t('analyzedOn')} {new Date(selectedHistoryItem.calculation_date * 1000).toLocaleDateString()}
          </div>
        )}
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-blue-50 p-5 rounded-xl border border-blue-100">
          <div className="text-blue-800 font-bold text-3xl mb-2">
            {calculationResult && calculationResult.summary_emission && calculationResult.summary_emission.project_total_emission_tco2 ? 
              calculationResult.summary_emission.project_total_emission_tco2.toFixed(2) : 
              (calculationResult && calculationResult.total_emission ? calculationResult.total_emission.toFixed(2) : '0.00')}
          </div>
          <div className="text-blue-600">{t('totalEmissions')}</div>
        </div>
        
        <div className="bg-green-50 p-5 rounded-xl border border-green-100">
          <div className="text-green-800 font-bold text-3xl mb-2">
            {calculateProjectStats().subProjects}
          </div>
          <div className="text-green-600">{t('unitProjects')}</div>
        </div>
        
        <div className="bg-purple-50 p-5 rounded-xl border border-purple-100">
          <div className="text-purple-800 font-bold text-3xl mb-2">
            {calculateFactorStats()}
          </div>
          <div className="text-purple-600">{t('carbonFactorsApplied')}</div>
        </div>
      </div>

      {calculationTime !== 'Unknown' && (
        <div className="mb-8 p-4 bg-gray-50 rounded-lg border border-gray-200">
          <h3 className="text-lg font-medium text-gray-800 mb-2">{t('calculationPerformance')}</h3>
          <p className="text-gray-600">{t('calculationCompletedIn')} {calculationTime} {t('seconds')}</p>
        </div>
      )}
      
      {/* Visualization Section */}
      <div>
        <h3 className="text-lg font-medium text-gray-800 mb-3">{t('emissionAnalysis')}</h3>
        
        {/* Project Hierarchy Tree */}
        <div className="mb-6">
          <ProjectHierarchyTree data={processProjectHierarchyData()} />
        </div>

        {/* Emission by Stage Pie Chart */}
        <div className="mb-6">
          <EmissionByStageChart data={calculationResult?.detailed_tree} />
        </div>
        
        {/* Top Sub Item Works Chart */}
        <div className="mb-6">
          <TopSubItemWorksChart data={processTopSubItemWorks()} />
        </div>
        
        
        {/* Combined Top 10 Resource Consumption Chart */}
        <div className="mb-6">
          <ResourceConsumptionChart data={processResourceConsumption()} />
        </div>
        
        <div className="text-center text-sm text-gray-600">
          <p>{t('calculationCompletedAt')} {new Date().toLocaleString()}</p>
          <p className="mt-1">
            {t('totalEmissions')}: {calculationResult && calculationResult.summary_emission && calculationResult.summary_emission.project_total_emission_tco2 ? 
              calculationResult.summary_emission.project_total_emission_tco2.toFixed(2) : 
              (calculationResult && calculationResult.total_emission ? calculationResult.total_emission.toFixed(2) : '0.00')} tCO2 | 
            {t('unitProjects')}: {calculateProjectStats().subProjects} |
            {t('carbonFactors')}: {calculateFactorStats()}
          </p>
        </div>
      </div>
    </div>
  )
}