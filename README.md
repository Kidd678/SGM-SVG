# SGM-SVG：语义场景图-运动计划协同的动态 SVG 生成系统

SGM-SVG 是一个面向 NLP 课程大作业的动态 SVG 信息图生成系统。系统可以根据自然语言提示词生成带动画的 SVG 信息图，并输出对应的 SVG、PNG 截图和 JSON 质量报告。

本项目的核心思想是：**让大语言模型负责语义理解、视觉设计和动画意图，让程序负责稳定的动画注入、浏览器渲染检查和质量反馈**。相比让模型一次性直接写完整动态 SVG，SGM-SVG 将任务拆分为语义场景图、静态 SVG、运动计划、动画注入和质量检查几个阶段，从而提升生成结果的结构可控性和可解释性。

## 主要功能

- 根据自然语言提示词生成动态 SVG 信息图。
- 先生成结构化语义场景图，再生成 SVG，便于分析和修复。
- 支持静态 SVG 与动画计划分离，降低模型直接编写复杂动画代码的不稳定性。
- 使用 Python 根据 MotionPlan 注入 CSS 动画。
- 使用 Playwright 调用真实浏览器检查最终帧，发现重叠、越界、字号过小等问题。
- 检查主要语义块是否按照合理顺序依次出现。
- 支持浏览器质量检查后的自动修复。
- 支持前端输入最后一次人工修改意见，在当前结果基础上继续修改。
- 支持中文和英文提示词，并尽量保持输出语言与输入语言一致。

## 系统架构

```text
用户提示词
  -> SceneGraphAgent
     生成语义场景图，包括标题、语言、视觉类型、叙事说明、元素、角色、顺序和连接关系。
  -> StaticSvgAgent
     根据语义场景图生成静态 SVG。
  -> MotionPlannerAgent / 确定性 MotionPlan
     规划每个语义元素的出现时间、动画类型和持续时间。
  -> Animation Injector
     将 MotionPlan 转换为 CSS 动画并注入 SVG。
  -> Browser QA
     使用 Playwright 渲染最终帧并检查几何质量。
  -> Animation QA
     检查动画出现顺序是否符合语义阅读顺序。
  -> 可选自动修复
     若发现明显布局问题，修复静态 SVG 并复用原动画计划。
  -> 输出 SVG / PNG / JSON
  -> 可选人工修改
     用户在前端输入最后一次修改意见，系统基于当前 SVG 继续修订。
```

## 项目结构

```text
.
├── app.py                    # FastAPI 后端入口和前端页面服务
├── agents/
│   └── generation.py          # SceneGraphAgent、StaticSvgAgent、MotionPlannerAgent
├── core/
│   ├── animation.py           # MotionPlan 到 CSS 动画的注入逻辑
│   ├── config.py              # 模型、端口、超时和环境变量配置
│   ├── llm_client.py          # OpenAI-compatible 模型客户端
│   ├── pipeline.py            # SGM-SVG 主流程
│   └── schemas.py             # 最终系统的数据结构定义
├── quality/                   # 浏览器检查、动画检查、SVG 清理等质量模块
├── scripts/
│   ├── run_experiment.py      # 命令行实验入口
│   └── smoke_frontend.py      # 前端冒烟测试脚本
├── static/
│   └── index.html             # 前端页面
├── outputs/                   # 示例 SVG、PNG 和 JSON 输出
├── requirements.txt           # Python 依赖
├── .env.example               # 环境变量模板
└── README.md
```

## 安装依赖

建议使用 Python 3.10 或更高版本。

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

如果本机已经安装 Chrome 或 Edge，Playwright 通常也可以直接使用本地浏览器；但为了稳定运行，仍建议安装 Chromium。

## 配置环境变量

复制环境变量模板：

```powershell
copy .env.example .env
```

然后在 `.env` 中填写需要使用的 API Key。`.env` 已经被 `.gitignore` 忽略，不会提交到 GitHub。

可配置的模型包括：

- MiniMax-M2.5
- DeepSeek-V4-Pro
- GLM-5.1
- MiMo-V2.5-Pro

默认模型可通过 `.env` 中的 `DEFAULT_MODEL_ID` 修改。

## 启动前端

在项目根目录运行：

```powershell
python .\app.py
```

然后打开浏览器访问：

```text
http://127.0.0.1:8020
```

前端提供五个固定测试提示词、模型选择、实时进度日志、结果预览、SVG/PNG/JSON 下载，以及最后一次人工修改输入框。

## 命令行运行

也可以直接通过脚本运行单个实验：

```powershell
python .\scripts\run_experiment.py "大语言模型的基本原理"
```

生成结果会保存在 `outputs/` 目录中。

## 课程实验中的技术路线

本项目最终报告中主要对比三条路线：

1. **单 Agent 基线**：一个大语言模型直接根据提示词生成完整动态 SVG。优点是简单直接，缺点是缺少中间结构，动画和布局难以控制。
2. **复杂多智能体流水线**：将任务拆成语义理解、视觉规划、SVG 生成、动画规划、质量检查等多个 Agent。优点是分工清晰，缺点是链路较长，错误容易在阶段之间传播。
3. **SGM-SVG 最终系统**：保留语义结构化和质量检查，但将静态图形与动画注入解耦，使系统更稳定、更容易解释，也更适合展示实验创新点。

## 输出内容

每次生成通常会输出：

- `.svg`：最终动态 SVG。
- `.png`：浏览器最终帧截图。
- `.json`：语义场景图、质量指标、耗时和文件路径等信息。

`outputs/` 中保留了一些示例结果，便于复现实验报告中的展示图。

## 注意事项

- 不要提交 `.env` 文件，真实 API Key 只保存在本地。
- Browser QA 依赖 Playwright 和 Chromium/Chrome/Edge 浏览器。
- 对事实准确性要求较高的题目，建议额外提供事实表或引入检索增强。
- 当前系统重点提升结构完整性、动画顺序和几何可读性，复杂审美判断仍依赖模型能力和人工筛选。
