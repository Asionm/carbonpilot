'use client';

import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { useLanguage } from '../utils/LanguageContext';

interface SubItemWork {
  name: string;
  emission: number;
  id?: string;
  path?: string[];
}

interface TopSubItemWorksChartProps {
  data: SubItemWork[];
}

const TopSubItemWorksChart: React.FC<TopSubItemWorksChartProps> = ({ data }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const { t } = useLanguage();

  useEffect(() => {
    if (!data || !ref.current) return;

    // Initialize or get existing chart instance
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current);
    }

    // Get top 10 items by sorting first
    const sortedData = [...data].sort((a, b) => b.emission - a.emission);
    const topData = sortedData.slice(0, 10);
    console.log(topData);

    // Truncate long names
    const truncateName = (name: string, maxLength = 12) => {
      return name.length > maxLength ? name.substring(0, maxLength) + '...' : name;
    };

    // Configure chart options
    const option: echarts.EChartsOption = {
      title: {
        text: t('top10SubItemWorksByEmissions'),
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
          return `${item.name}<br/>${t('emissionsTco2').replace('{value}', params[0].value.toFixed(2))}`;
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '30%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: topData.map(item => truncateName(item.name)),
        axisLabel: {
          rotate: -45,
          interval: 0,
          fontSize: 12,
          margin: 10
        }
      },
      yAxis: {
        type: 'value',
        name: 'Emissions (tCO₂)',
        nameTextStyle: {
          fontSize: 12
        },
        axisLabel: {
          fontSize: 12
        }
      },
      series: [
        {
          name: 'Emissions',
          type: 'bar',
          barWidth: '60%',
          data: topData.map(item => item.emission),
          itemStyle: {
            color: '#4ecdc4'
          },
          emphasis: {
            itemStyle: {
              color: '#ff6b6b'
            }
          },
          label: {
            show: true,
            position: 'top',
            formatter: (params: any) => params.value.toFixed(2),
            fontSize: 12,
            color: '#333',
            rotate: 0
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
      <h3 className="text-lg font-medium text-gray-800 mb-3">{t('top10SubItemWorksByEmissions')}</h3>
      <div ref={ref} style={{ width: '100%', height: '400px' }}></div>
      <div className="mt-4 text-sm text-gray-600">
        {t('showingTop10SubItemWorks')}
      </div>
    </div>
  );
};

export default TopSubItemWorksChart;