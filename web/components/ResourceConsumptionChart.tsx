'use client';

import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { useLanguage } from '../utils/LanguageContext';

interface ResourceConsumption {
  name?: string;
  resource_name?: string;
  emission: number;
  category?: string;
  resource_id?: string;
  total_value?: number;
  unit?: string;
  count?: number;
}

interface ResourceConsumptionChartProps {
  data: ResourceConsumption[];
}

const ResourceConsumptionChart: React.FC<ResourceConsumptionChartProps> = ({ data }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const { t } = useLanguage();

  useEffect(() => {
    if (!data || !ref.current) return;

    // Initialize or get existing chart instance
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current);
    }
    console.log(data);

    // Sort by emission and get top 10 items
    const sortedData = [...data].sort((a, b) => b.emission - a.emission);
    const topData = sortedData.slice(0, 10);
    console.log(topData);

    if (topData.length === 0) {
      ref.current.innerHTML = `<p class="text-center text-gray-500 py-10">${t('noResourceDataAvailable')}</p>`;
      return;
    }

    // Truncate long names
    const truncateName = (name: string, maxLength = 20) => {
          return name?.length > maxLength ? name.substring(0, maxLength) + '...' : name;
    };

    // Configure chart options
    const option: echarts.EChartsOption = {
      title: {
        text: t('top10ResourceConsumptionItems'),
        textStyle: {
          fontSize: 16,
          fontWeight: 'normal'
        },
        left: 'center'
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        },
        formatter: (params: any) => {
          const item = topData[params[0].dataIndex];
          return `
            <strong>${item.name || item.resource_name || 'Unknown'}</strong><br/>
            Category: ${item.category || 'N/A'}<br/>
            Emission: ${item.emission?.toFixed(2) || '0.00'} tCO₂<br/>
          `;
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: topData.map(item => truncateName(item.name || item.resource_name || 'Unknown')),
        axisLabel: {
          rotate: -45,
          interval: 0
        }
      },
      yAxis: {
        type: 'value',
        name: 'Emissions (tCO₂)'
      },
      series: [
        {
          name: 'Emissions',
          type: 'bar',
          barWidth: '60%',
          data: topData.map(item => item.emission || 0),
          itemStyle: {
            color: '#96ceb4'
          },
          emphasis: {
            itemStyle: {
              color: '#ff6b6b'
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
      <h3 className="text-lg font-medium text-gray-800 mb-3">{t('top10ResourceConsumptionItems')}</h3>
      <div ref={ref} style={{ width: '100%', height: '400px' }}></div>
      <div className="mt-4 text-sm text-gray-600">
        {t('showingTop10Resources')}
      </div>
    </div>
  );
};

export default ResourceConsumptionChart;