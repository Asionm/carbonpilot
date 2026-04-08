import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface ResourceDistributionData {
  name: string;
  emission: number;
}

interface ResourceDistributionChartProps {
  data: ResourceDistributionData[];
  title: string;
}

const ResourceDistributionChart: React.FC<ResourceDistributionChartProps> = ({ data, title }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (chartRef.current) {
      if (chartInstance.current) {
        chartInstance.current.dispose();
      }
      chartInstance.current = echarts.init(chartRef.current);
      
      const option = {
        title: {
          text: title,
          left: 'center'
        },
        tooltip: {
          trigger: 'item',
          formatter: '{a} <br/>{b}: {c} ({d}%)'
        },
        legend: {
          type: 'scroll',
          orient: 'horizontal',
          left: 'center',
          bottom: 0,
          data: data.map(item => item.name),
          textStyle: {
            fontSize: 10
          }
        },
        series: [
          {
            name: title || 'Resource Distribution',
            type: 'pie',
            radius: ['40%', '70%'],
            avoidLabelOverlap: false,
            itemStyle: {
              borderRadius: 10,
              borderColor: '#fff',
              borderWidth: 2
            },
            label: {
              show: data.length <= 10, // Only show labels if not too many items
              formatter: '{b}: {d}%'
            },
            labelLine: {
              show: data.length <= 10
            },
            data: data.map(item => ({
              name: item.name,
              value: item.emission
            })),
            emphasis: {
              itemStyle: {
                shadowBlur: 10,
                shadowOffsetX: 0,
                shadowColor: 'rgba(0, 0, 0, 0.5)'
              },
              label: {
                show: true
              }
            }
          }
        ]
      };
      
      chartInstance.current.setOption(option);
    }

    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
      }
    };
  }, [data, title]);

  useEffect(() => {
    if (chartInstance.current) {
      chartInstance.current.resize();
    }
  }, []);

  return <div ref={chartRef} style={{ width: '100%', height: '400px' }}></div>;
};

export default ResourceDistributionChart;