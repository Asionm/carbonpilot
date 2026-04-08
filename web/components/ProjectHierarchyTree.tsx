'use client';

import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { useLanguage } from '../utils/LanguageContext';

interface TreeNode {
  name: string;
  children?: TreeNode[];
  value?: number;
  itemStyle?: {
    color?: string;
  };
}

interface ProjectHierarchyTreeProps {
  data: any;
}

const ProjectHierarchyTree: React.FC<ProjectHierarchyTreeProps> = ({ data }) => {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const { t } = useLanguage();

  /* ----------------------------------------
   * Convert backend hierarchical data to ECharts Treemap structure
   * ---------------------------------------- */
  const convertToTreemapData = (node: any): TreeNode | null => {
    if (!node || !node.name) return null;

    const treeNode: TreeNode = {
      name: node.name,
      itemStyle: {}
    };

    // Color map based on levels
    const colorMap: Record<string, string> = {
      construction_project: '#5470c6',
      individual_project: '#91cc75',
      unit_project: '#fac858',
      sub_divisional_work: '#ee6666',
      specialty_subdivision: '#73c0de',
      sub_item_work: '#3ba272'
    };
    treeNode.itemStyle!.color = colorMap[node.level] || '#fc8452';

    const children: TreeNode[] = [];

    // Convert child nodes recursively
    if (Array.isArray(node.children)) {
      node.children.forEach((child: any) => {
        const converted = convertToTreemapData(child);
        if (converted) children.push(converted);
      });
    }

    const isLowestWorkLevel = node.level === 'sub_item_work';

    // Only attach resource items to the lowest engineering level
    if (isLowestWorkLevel && Array.isArray(node.resource_items)) {
      node.resource_items.forEach((item: any) => {
        if (item?.resource_name) {
          const v =
            typeof item.emission === 'number'
              ? Math.abs(item.emission / 1000)
              : 0;

          children.push({
            name: item.resource_name,
            value: v > 0 ? v : 0.001,
            itemStyle: { color: '#9a60b4' }
          });
        }
      });
    }

    if (children.length > 0) {
      treeNode.children = children;
      // Let ECharts auto-sum values from children
    } else {
      // Leaf node → calculate its value
      let value = 0;

      if (typeof node.properties?.emission_tco2 === 'number') {
        value += Math.abs(node.properties.emission_tco2);
      }

      if (Array.isArray(node.resource_items)) {
        node.resource_items.forEach((item: any) => {
          if (typeof item.emission === 'number') {
            value += Math.abs(item.emission / 1000);
          }
        });
      }

      treeNode.value = value > 0 ? value : 0.001;
    }

    return treeNode;
  };

  /* ----------------------------------------
   * Initialize ECharts instance once
   * ---------------------------------------- */
  useEffect(() => {
    if (ref.current && !chartRef.current) {
      chartRef.current = echarts.init(ref.current);

      const resize = () => chartRef.current?.resize();
      window.addEventListener('resize', resize);

      return () => {
        window.removeEventListener('resize', resize);
        chartRef.current?.dispose();
        chartRef.current = null;
      };
    }
  }, []);

  /* ----------------------------------------
   * Update chart whenever data changes
   * ---------------------------------------- */
  useEffect(() => {
    if (!chartRef.current || !data) return;

    const treemapData = convertToTreemapData(data);
    if (!treemapData) {
      if (ref.current) {
        ref.current.innerHTML =
          `<p class="text-center text-gray-500 py-10">${t('noValidHierarchyData')}</p>`;
      }
      return;
    }

    const option: echarts.EChartsCoreOption = {
      title: {
        text: t('projectHierarchyTreemap'),
        left: 'center',
        textStyle: { fontSize: 16, fontWeight: 'normal' }
      },
      tooltip: {
        formatter: (info: any) => {
          const path =
            info.treePathInfo?.map((n: any) => n.name).join(' > ') || info.name;
          const v = typeof info.value === 'number' ? info.value : 0;
          return `${path}<br/>${t('emissionsTco2').replace('{value}', v.toFixed(2))}`;
        }
      },
      series: [
        {
          name: 'Project Hierarchy',
          type: 'treemap',
          data: [treemapData],

          /* ⭐ KEY: Expand only one level at a time */
          leafDepth: 1, // Only show immediate children initially
          nodeClick: 'zoomToNode', // Drill down when clicking

          visibleMin: 0,

          label: {
            show: true,
            formatter: '{b}',
            color: '#fff',
            fontSize: 12,
            fontWeight: 'bold'
          },
          upperLabel: {
            show: true,
            height: 20,
            color: '#000',
            fontWeight: 'bold'
          },

          breadcrumb: {
            show: true,
            height: 22
          },

          itemStyle: {
            borderColor: '#fff',
            borderWidth: 1,
            gapWidth: 1
          },
          levels: [
            { itemStyle: { borderWidth: 0, gapWidth: 5 } },
            { itemStyle: { gapWidth: 2 } },
            {
              colorSaturation: [0.3, 0.6],
              itemStyle: { gapWidth: 1 }
            }
          ],

          animationDurationUpdate: 500
        }
      ]
    };

    chartRef.current.setOption(option, true);
  }, [data, t]);

  return (
    <div className="bg-gray-50 rounded-lg border border-gray-200 p-4">
      <h3 className="text-lg font-medium text-gray-800 mb-3">
        {t('projectHierarchyTree')}
      </h3>
      <div ref={ref} style={{ width: '100%', height: '500px' }} />

      <div className="mt-4 text-sm text-gray-600">
        <p>
          {t('clickToExpandNextLevel')}
        </p>
        <ul className="list-disc pl-5 mt-2 space-y-1">
          <li className="flex items-center">
            <span className="w-3 h-3 bg-blue-500 rounded-full mr-2" />
            {t('constructionProject')}
          </li>
          <li className="flex items-center">
            <span className="w-3 h-3 bg-green-500 rounded-full mr-2" />
            {t('individualProject')}
          </li>
          <li className="flex items-center">
            <span className="w-3 h-3 bg-yellow-500 rounded-full mr-2" />
            {t('unitProject')}
          </li>
          <li className="flex items-center">
            <span className="w-3 h-3 bg-red-500 rounded-full mr-2" />
            {t('subDivisionalWork')}
          </li>
          <li className="flex items-center">
            <span className="w-3 h-3 bg-blue-300 rounded-full mr-2" />
            {t('specialtySubdivision')}
          </li>
          <li className="flex items-center">
            <span className="w-3 h-3 bg-green-700 rounded-full mr-2" />
            {t('subItemWork')}
          </li>
          <li className="flex items-center">
            <span className="w-3 h-3 bg-purple-500 rounded-full mr-2" />
            {t('resourceItems')}
          </li>
        </ul>
      </div>
    </div>
  );
};

export default ProjectHierarchyTree;