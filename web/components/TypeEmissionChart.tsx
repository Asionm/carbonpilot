import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface TypeEmissionData {
  name: string;
  emission: number;
}

interface TypeEmissionChartProps {
  data: TypeEmissionData[];
  title: string;
}

const TypeEmissionChart: React.FC<TypeEmissionChartProps> = ({ data, title }) => {
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
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          }
        },
        xAxis: {
          type: 'category',
          data: data.map(item => item.name),
          axisLabel: {
            rotate: 45,
            interval: 0
          }
        },
        yAxis: {
          type: 'value',
          name: 'Emissions (tCO2)'
        },
        series: [{
          data: data.map(item => item.emission),
          type: 'bar',
          itemStyle: {
            color: '#91cc75'
          }
        }]
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

export default TypeEmissionChart;