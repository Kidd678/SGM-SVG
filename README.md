# SGM-SVG: Semantic Graph and Motion-plan Driven SVG Generation

SGM-SVG is an experimental dynamic SVG infographic generation system for an NLP course project. It turns a natural-language prompt into an animated SVG by separating semantic planning, static SVG generation, motion planning, deterministic animation injection, browser-based quality checking, and optional human revision.

The core idea is simple: let the language model handle semantic understanding and visual design intent, while the program handles stable animation timing and browser-rendered quality feedback.

## Features

- Text-to-dynamic-SVG generation with OpenAI-compatible LLM APIs.
- Structured scene graph planning before SVG generation.
- Static SVG generation with stable element ids and semantic ordering.
- Motion plan generation and deterministic CSS animation injection.
- Browser QA with Playwright to inspect the final rendered frame.
- Animation QA to check whether major semantic blocks appear in a reasonable order.
- Optional automatic repair for static SVG layout problems.
- Optional final human revision from the web UI.
- Chinese and English prompt support, including language preservation for English prompts.

## Architecture

```text
User Prompt
  -> SceneGraphAgent
     Produces a structured scene graph with title, language, visual type,
     narrative, elements, roles, ordering, and connections.
  -> StaticSvgAgent
     Generates a static SVG from the scene graph.
  -> MotionPlannerAgent / deterministic MotionPlan
     Plans reveal timing and animation effects.
  -> Animation Injector
     Injects CSS animations into the static SVG.
  -> Browser QA
     Uses Playwright to check the final rendered frame.
  -> Animation QA
     Checks semantic reveal order.
  -> Optional Repair
     Repairs the static SVG and reuses the same motion plan.
  -> SVG / PNG / JSON outputs
  -> Optional Human Revision
```

## Project Structure

```text
.
├── app.py                    # FastAPI backend and web entry point
├── agents/
│   └── generation.py          # SceneGraphAgent, StaticSvgAgent, MotionPlannerAgent
├── core/
│   ├── animation.py           # MotionPlan to CSS animation injection
│   ├── config.py              # Model and app configuration
│   ├── llm_client.py          # OpenAI-compatible LLM client
│   ├── pipeline.py            # End-to-end SGM-SVG pipeline
│   └── schemas.py             # SGM-SVG data schemas
├── quality/                   # Browser, animation, sanitizer, and static checks
├── scripts/
│   ├── run_experiment.py      # CLI experiment runner
│   └── smoke_frontend.py      # Frontend smoke test
├── static/
│   └── index.html             # Web UI
├── outputs/                   # Example generated SVG/PNG/JSON outputs
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

Python 3.10 or newer is recommended.

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

Create a local `.env` file from `.env.example` and fill in the API keys you need:

```powershell
copy .env.example .env
```

The `.env` file is ignored by Git and should not be committed.

## Run the Web App

```powershell
python .\app.py
```

Then open:

```text
http://127.0.0.1:8020
```

The frontend provides five fixed test prompts, a model selector, live progress logs, SVG/PNG/JSON outputs, and a final human revision box.

## Run from CLI

```powershell
python .\scripts\run_experiment.py "大语言模型的基本原理"
```

Generated files are saved under `outputs/`.

## Models

The system supports several OpenAI-compatible model routes, configured in `core/config.py`:

- MiniMax-M2.5
- DeepSeek-V4-Pro
- GLM-5.1
- MiMo-V2.5-Pro

The default model can be changed with `DEFAULT_MODEL_ID` in `.env`.

## Notes

- Do not commit `.env`; use `.env.example` for public configuration templates.
- Browser QA requires Playwright and a Chromium-compatible browser.
- The example outputs are included for demonstration and report reproduction.
- For fact-sensitive prompts, retrieval augmentation or user-provided facts are recommended.
