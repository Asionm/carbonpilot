

<div align="center">
  <p align="center">   <img src="../assets/logo.png" width="30%"/> </p>


<p align="center"><b>交碳智算 CarbonPilot (CPi)</b></p>
<p align="center">
  面向工程的 AI 驱动隐含碳排放量化、可视化与知识推理系统
</p>

<p align="center">
  <span style="
    border:1px dashed #d0d7de;
    border-radius:6px;
    padding:6px 14px;
    font-size:14px;
  ">
    <a href="../README.md"><b>English</b></a>
    &nbsp;|&nbsp;
    <a href="README_CN.md"><b>中文</b></a>
  </span>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-green.svg" />
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/Python-3.13+-blue.svg" />
  </a>
  <a href="https://nodejs.org/">
    <img src="https://img.shields.io/badge/Node.js-16+-green.svg" />
  </a>
  <a href="https://nextjs.org/">
    <img src="https://img.shields.io/badge/Next.js-13.5.6-informational.svg" />
  </a>
</p>
</div>



## 🌱 项目简介

**交碳智算 CarbonPilot** 是一个面向**工程隐含碳排放量化**的知识增强型智能体系统。系统融合了**知识图谱**、**大语言模型（LLMs）**与**交互式可视化技术**，能够对异构工程数据进行自动解析，实现可追溯的碳排放计算、推理分析与对话式交互。本项目主要面向从事**建筑碳排放评估、可持续发展分析以及 AI 辅助决策**的研究人员与工程实践者。



## ✨ 核心能力

- **🧮 一键式碳排放计算**  
  自动解析并处理多源异构工程文档与项目数据

- **📊 交互式结果可视化**  
  通过动态图表对隐含碳排放结果进行分析与对比

- **💬 AI 对话式分析**  
  基于大语言模型，对计算结果与推理过程进行交互式解读

- **🕘 历史数据管理**  
  支持项目历史、碳排放记录及分析过程的持续追踪

- **⚙️ 灵活配置机制**  
  支持数据库、LLM 参数、向量嵌入及智能体行为的灵活配置



## 🎬 演示示例

该演示展示了 **交碳智算 CarbonPilot** 的完整工作流程，包括项目数据输入、隐含碳排放计算，以及基于智能体推理的交互式结果可视化。

<p align="center">
  <img src="../assets/demo.gif" alt="CarbonPilot Demo" width="100%" />
</p>



## 🧱 系统架构

系统采用以 **交碳智算 CarbonPilot 为核心** 的架构设计。智能体通过整合**工程—碳排放知识**、**记忆模块**与**工具调用机制**，对建筑项目进行推理分析。异构工程信息首先被编码为**工作分解结构（WBS）**，随后与工程及隐含碳知识对齐，在智能体推理流程中完成计算与决策，最终输出建筑隐含碳排放评估结果。



## 🖥️ 系统环境要求

- **Python 3.13 及以上**
- **Node.js 16 及以上**
- **Docker**（用于运行 Neo4j 图数据库）



## 🚀 安装说明

### 1️⃣ 后端环境配置

在项目根目录下执行：

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

上述命令将安装系统运行所需的全部后端依赖。



### 2️⃣ 前端依赖安装

进入前端目录：

```bash
cd web
npm install
```

用于安装 Web 界面所需的前端依赖。



### 3️⃣ 图数据库初始化

系统使用 **Neo4j** 作为知识图谱存储，并通过 Docker 运行。

首次运行时，请执行：

```bash
python init.py
```

该脚本将完成：

- Neo4j 容器启动
- 工程知识图谱与隐含碳因子数据初始化

>**补充说明：**
> 初始化过程中将使用 `.env` 文件中配置的**向量嵌入模型**。
> 当前默认嵌入模型为部署在 **Ollama** 中的 **`qwen3-embedding`**，请在初始化前确认对应模型已正确配置并可用。



## ▶️ 使用方式

完成初始化后，通过以下命令启动系统：

```bash
python start.py
```

系统启动过程中将自动：

- 启动后端 API 服务
- 启动前端 Web 应用

启动完成后，可通过浏览器访问：

```bash
http://localhost:3000
```

> **使用提示：**
>  在开始分析之前，请先在 Web 界面**右上角的设置区域**完成 **模型与策略的配置**。
>
> **关于结果可复现性的说明：**
>  由于系统中涉及基于大语言模型的推理过程，不同运行之间可能存在一定的非确定性行为。



## 📂 项目结构说明

```
CarbonPilot/
├── assets/                     # 项目资源文件（Logo、图片、演示文件等）
│
├── configs/                    # 配置封装
│                               #（LLM、向量嵌入、Neo4j、系统参数）
│
├── knowledge_graph/            # 知识图谱构建与处理模块
│   ├── cef/                    # 隐含碳因子（CEF）知识模块
│   └── quota/                  # 清单 / 定额相关查询与工具模块
│
├── schemes/                    # 数据模型与项目信息结构定义
│
├── server/                     # 后端服务与业务逻辑
│   └── routes/                 # API 路由定义
│
├── static/                     # 静态文件、中间缓存与输出结果
│   ├── extraction_cache/       # 文档信息抽取缓存
│   ├── quota_cache/            # 定额相关缓存
│   └── result/                 # 计算结果输出
│
├── tests/                      # 测试脚本与测试用例
│                               #（单元测试、集成测试）
│
├── utils/                      # 公共工具函数
│
├── web/                        # 前端应用（Next.js）
│   ├── app/                    # Next.js App Router
│   ├── components/             # 可复用 React 组件
│   └── utils/                  # 前端工具函数
│
├── init.py                     # 系统初始化脚本
│                               #（Neo4j 启动、知识图谱初始化）
│
├── start.py                    # 系统启动入口
│                               #（后端 + 前端）
│
├── prompts.py                  # 大语言模型提示模板
│
└── README.md                   # 项目说明文档
```



## ⚙️ 配置说明

交碳智算 CarbonPilot 支持多种大语言模型后端（云端或本地）。请确保所选 LLM 后端具备与当前隐含碳因子选择模式相匹配的能力。



## ⚠️ 使用注意事项

**基于概率的隐含碳因子选择模式** 依赖于 LLM API 输出 **logit 或 token 概率信息**。
 如果所使用的 LLM 后端 **不支持概率信息输出**（如 **Ollama**），请使用 **Highest Similarity** 模式。



## 📄 许可证

本项目采用 **MIT License** 开源许可协议，详见 [LICENSE](LICENSE) 文件。