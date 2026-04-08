import { ChildNode, CalculationResult } from './schemes';

// Calculate statistics for visualization
export const calculateProjectStats = (calculationResult: CalculationResult | null) => {
  if (!calculationResult) return { projects: 0, subProjects: 0, subItems: 0 }

  let projects = 0
  let subProjects = 0
  let subItems = 0

  const traverse = (nodes: ChildNode | ChildNode[]) => {
    // Handle both array and single object cases
    const nodeList = Array.isArray(nodes) ? nodes : [nodes];
    
    nodeList.forEach(node => {
      // Updated level checks to match the actual data structure
      if (node.level === 'construction_project') projects++
      if (node.level === 'individual_project') subProjects++
      if (node.level === 'sub_item_work') subItems++
      if (node.children) traverse(node.children)
    })
  }

  if (calculationResult.detailed_tree) {
    traverse(calculationResult.detailed_tree)
  }

  return { projects, subProjects, subItems }
}

export const calculateFactorStats = (calculationResult: CalculationResult | null) => {
  if (!calculationResult) return 0

  const factorSet = new Set<string>()

  const traverse = (nodes: ChildNode | ChildNode[]) => {
    // Handle both array and single object cases
    const nodeList = Array.isArray(nodes) ? nodes : [nodes];
    
    nodeList.forEach(node => {
      if (node.resource_items) {
        node.resource_items.forEach(item => {
          if (item.best_factor) {
            factorSet.add(item.best_factor.id)
          }
        })
      }
      if (node.children) traverse(node.children)
    })
  }

  if (calculationResult.detailed_tree) {
    traverse(calculationResult.detailed_tree)
  }

  return factorSet.size
}

// Process data for charts
export const processProjectEmissionData = (calculationResult: CalculationResult | null) => {
  if (!calculationResult || !calculationResult.detailed_tree) return []

  const emissions: any[] = []

  const traverse = (nodes: ChildNode | ChildNode[], projectName: string) => {
    // Handle both array and single object cases
    const nodeList = Array.isArray(nodes) ? nodes : [nodes];
    
    let projectEmission = 0

    const calculateNodeEmission = (node: ChildNode) => {
      let emission = 0
      if (node.properties?.emission_tco2) {
        emission = node.properties.emission_tco2
      }
      if (node.resource_items) {
        node.resource_items.forEach(item => {
          emission += (item.emission || 0) / 1000 // Convert kgCO2 to tCO2
        })
      }
      return emission
    }

    nodeList.forEach(node => {
      // Updated level checks to match the actual data structure
      if (node.level === 'construction_project') {
        projectName = node.name
        projectEmission = calculateNodeEmission(node)
      } else if (node.level === 'individual_project') {
        projectName = node.name
        projectEmission = calculateNodeEmission(node)
      } else if (node.level === 'unit_project') {
        projectName = node.name
        projectEmission = calculateNodeEmission(node)
      } else if (node.level === 'sub_item_work') {
        projectEmission += calculateNodeEmission(node)
      }

      if (node.children) {
        traverse(node.children, projectName)
      }
    })

    if (projectEmission > 0) {
      emissions.push({ name: projectName, emission: projectEmission })
    }
  }

  traverse(calculationResult.detailed_tree, '')
  return emissions
}

export const processSubProjectData = (calculationResult: CalculationResult | null) => {
  if (!calculationResult || !calculationResult.detailed_tree) return []

  const subProjects: any[] = []

  const traverse = (nodes: ChildNode | ChildNode[]) => {
    // Handle both array and single object cases
    const nodeList = Array.isArray(nodes) ? nodes : [nodes];
    
    nodeList.forEach(node => {
      // Updated level checks to match the actual data结构
      if (node.level === 'sub_divisional_work') {
        const emission = node.properties?.emission_tco2 || 0
        subProjects.push({ 
          name: node.name, 
          emission,
          description: node.description
        })
      }
      if (node.children) traverse(node.children)
    })
  }

  if (calculationResult.detailed_tree) {
    traverse(calculationResult.detailed_tree)
  }

  return subProjects
}

export const processSubItemWorkData = (calculationResult: CalculationResult | null) => {
  if (!calculationResult || !calculationResult.detailed_tree) return []

  const items: any[] = []

  const traverse = (nodes: ChildNode | ChildNode[]) => {
    const list = Array.isArray(nodes) ? nodes : [nodes]

    list.forEach(node => {
      if (node.level === 'sub_item_work') {
        const emission = node.properties?.emission_tco2 || 0
        items.push({
          name: node.name,
          emission,
        })
      }
      if (node.children) traverse(node.children)
    })
  }

  traverse(calculationResult.detailed_tree)
  return items
}

export const processResourceCategoryData = (calculationResult: CalculationResult | null) => {
  if (!calculationResult) return []

  const categoryMap = new Map<string, { emission: number, count: number }>()

  const traverse = (nodes: ChildNode | ChildNode[]) => {
    // Handle both array and single object cases
    const nodeList = Array.isArray(nodes) ? nodes : [nodes];
    
    nodeList.forEach(node => {
      if (node.resource_items) {
        node.resource_items.forEach(item => {
          const emission = (item.emission || 0) / 1000 // Convert kgCO2 to tCO2
          const category = item.category || 'Unknown'
          
          if (categoryMap.has(category)) {
            const existing = categoryMap.get(category)!
            categoryMap.set(category, {
              emission: existing.emission + emission,
              count: existing.count + 1
            })
          } else {
            categoryMap.set(category, {
              emission,
              count: 1
            })
          }
        })
      }
      if (node.children) traverse(node.children)
    })
  }

  if (calculationResult.detailed_tree) {
    traverse(calculationResult.detailed_tree)
  }

  return Array.from(categoryMap.entries()).map(([category, data]) => ({
    category,
    emission: data.emission,
    count: data.count
  }))
}

export const processMaterialData = (calculationResult: CalculationResult | null) => {
  if (!calculationResult) return []

  // Using a map to aggregate materials by name
  const materialMap = new Map<string, { 
    emission: number, 
    category: string,
    count: number,
    totalValue: number,
    unit: string
  }>()

  const traverse = (nodes: ChildNode | ChildNode[]) => {
    // Handle both array and single object cases
    const nodeList = Array.isArray(nodes) ? nodes : [nodes];
    
    nodeList.forEach(node => {
      if (node.resource_items) {
        node.resource_items.forEach(item => {
          const emission = (item.emission || 0) / 1000 // Convert kgCO2 to tCO2
          const name = item.resource_name || 'Unknown Material'
          const category = item.category || 'Unknown'
          const value = item.value || 0
          const unit = item.unit || ''
          
          if (materialMap.has(name)) {
            const existing = materialMap.get(name)!
            materialMap.set(name, {
              emission: existing.emission + emission,
              category: existing.category,
              count: existing.count + 1,
              totalValue: existing.totalValue + value,
              unit: existing.unit || unit // Keep existing unit or use new one
            })
          } else {
            materialMap.set(name, {
              emission,
              category,
              count: 1,
              totalValue: value,
              unit
            })
          }
        })
      }
      if (node.children) traverse(node.children)
    })
  }

  if (calculationResult.detailed_tree) {
    traverse(calculationResult.detailed_tree)
  }

  // Convert map to array with proper structure
  return Array.from(materialMap.entries()).map(([name, data]) => ({
    name,
    emission: data.emission,
    category: data.category,
    count: data.count,
    total_value: data.totalValue,
    unit: data.unit
  }))
}