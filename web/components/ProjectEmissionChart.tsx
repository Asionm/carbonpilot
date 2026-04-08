import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface ProjectEmissionData {
  name: string;
  emission: number;
}

interface ProjectEmissionChartProps {
  data: ProjectEmissionData[];
  title: string;
}

const ProjectEmissionChart: React.FC<ProjectEmissionChartProps> = ({ data, title }) => {
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
          left: 'center',
          textStyle: {
            fontSize: 18,
            fontWeight: 'bold',
            fontFamily: 'Times New Roman'
          }
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          },
          formatter: (params: any) => {
            const param = params[0];
            return `${param.name}<br/>${param.seriesName}: ${param.value.toFixed(2)} tCO2`;
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
          data: data.map(item => item.name),
          axisLabel: {
            rotate: 45,
            interval: 0,
            fontSize: 16,
            fontFamily: 'Times New Roman'
          }
        },
        yAxis: {
          type: 'value',
          name: 'Emissions (tCO2)',
          nameTextStyle: {
            fontSize: 16,
            fontFamily: 'Times New Roman'
          },
          axisLabel: {
            fontSize: 14,
            fontFamily: 'Times New Roman'
          }
        },
        series: [{
          name: 'Emission',
          data: data.map(item => item.emission),
          type: 'bar',
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#3b82f6' },
              { offset: 1, color: '#1d4ed8' }
            ])
          },
          barWidth: '60%',
          emphasis: {
            itemStyle: {
              color: '#1d4ed8'
            }
          }
        }],
        textStyle: {
          fontFamily: 'Times New Roman',
          fontSize: 16
        }
      };

      chartInstance.current.setOption(option);
      
      // Make chart responsive
      const handleResize = () => {
        chartInstance.current?.resize();
      };
      
      window.addEventListener('resize', handleResize);
      
      return () => {
        window.removeEventListener('resize', handleResize);
        chartInstance.current?.dispose();
      };
    }
  }, [data, title]);

  return <div ref={chartRef} style={{ height: '400px', width: '100%' }} />;
};

export default ProjectEmissionChart;