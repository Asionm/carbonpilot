'use client';

import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { useLanguage } from '../utils/LanguageContext';

interface EmissionByStageChartProps {
  data: any[]; // Resource items data
}

const EmissionByStageChart: React.FC<EmissionByStageChartProps> = ({ data }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const { t } = useLanguage();

  useEffect(() => {
    if (!data || !ref.current) return;

    // Initialize or get existing chart instance
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current);
    }

    // Process data to get emissions by category
    const categoryEmissions: Record<string, number> = {
      'Material': 0,
      'Transport': 0,
      'Machinery': 0,
      'Labor': 0
    };

    // Process resource items
    const traverse = (nodes: any | any[]) => {
      const nodeList = Array.isArray(nodes) ? nodes : [nodes];
      
      nodeList.forEach((node: any) => {
        if (node.resource_items) {
          node.resource_items.forEach((item: any) => {
            if (item.category && categoryEmissions.hasOwnProperty(item.category)) {
              categoryEmissions[item.category] += (item.emission || 0) / 1000; // Convert to tCO2
            }
          });
        }
        
        if (node.children) {
          traverse(node.children);
        }
      });
    };

    if (data) {
      traverse(data);
    }

    // Filter out zero values and convert to array
    const chartData = Object.entries(categoryEmissions)
      .filter(([_, emission]) => emission > 0)
      .map(([name, emission]) => ({
        name,
        value: emission
      }));

    if (chartData.length === 0) {
      ref.current.innerHTML = `<p class="text-center text-gray-500 py-10">${t('noEmissionDataAvailable')}</p>`;
      return;
    }

    // Configure chart options
    const option: echarts.EChartsOption = {
      title: {
        text: t('emissionsByResourceCategory'),
        textStyle: {
          fontSize: 16,
          fontWeight: 'normal'
        },
        left: 'center'
      },
      tooltip: {
        trigger: 'item',
        formatter: '{a} <br/>{b}: {c} tCO₂ ({d}%)'
      },
      legend: {
        orient: 'horizontal',
        bottom: 10,
        data: chartData.map(item => item.name)
      },
      series: [
        {
          name: 'Emissions',
          type: 'pie',
          radius: '55%',
          center: ['50%', '50%'],
          data: chartData,
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }
      ]
    };

    // Apply chart options
    chartRef.current.setOption(option, true);

    // Handle window resize
    const handleResize = () => {
      chartRef.current?.resize();
    };

    window.addEventListener('resize', handleResize);

    // Clean up event listeners and chart instances
    return () => {
      window.removeEventListener('resize', handleResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [data, t]);

  return (
    <div className="bg-gray-50 rounded-lg border border-gray-200 p-4">
      <h3 className="text-lg font-medium text-gray-800 mb-3">{t('emissionsByResourceCategory')}</h3>
      <div ref={ref} style={{ width: '100%', height: '400px' }}></div>
      <div className="mt-4 text-sm text-gray-600">
        {t('distributionByResourceCategory')}
      </div>
    </div>
  );
};

export default EmissionByStageChart;