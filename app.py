from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

V2_ROOT = Path(__file__).resolve().parent
if str(V2_ROOT) in sys.path:
    sys.path.remove(str(V2_ROOT))
sys.path.insert(0, str(V2_ROOT))

from core.config import DEFAULT_MODEL_ID, MODEL_PROFILES, settings  # noqa: E402
from core.pipeline import V2Pipeline  # noqa: E402
from core.schemas import MotionPlan, SceneGraph  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="版本2 动态 SVG 视觉叙事实验室")


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=2000)
    model_id: str = DEFAULT_MODEL_ID
    use_llm_motion: bool = True
    repair_static: bool = True


class ReviseRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=2000)
    model_id: str = DEFAULT_MODEL_ID
    scene_graph: SceneGraph
    motion_plan: MotionPlan
    svg: str = Field(min_length=20)
    instruction: str = Field(min_length=2, max_length=1000)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(V2_ROOT / "static" / "index.html")


@app.get("/api/models")
def list_models() -> dict:
    return {
        "default": DEFAULT_MODEL_ID,
        "models": [
            {"id": profile.id, "label": profile.label}
            for profile in MODEL_PROFILES.values()
        ],
    }


@app.post("/api/generate")
def generate(request: GenerateRequest) -> dict:
    try:
        result = V2Pipeline(model_id=request.model_id).run(
            request.prompt.strip(),
            use_llm_motion=request.use_llm_motion,
            repair_static=request.repair_static,
        )
        return _result_payload(result)
    except Exception as exc:
        logger.exception("版本2生成任务失败")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/revise")
def revise(request: ReviseRequest) -> dict:
    try:
        result = V2Pipeline(model_id=request.model_id).revise(
            prompt=request.prompt.strip(),
            scene_graph=request.scene_graph,
            motion_plan=request.motion_plan,
            current_svg=request.svg,
            user_instruction=request.instruction.strip(),
        )
        return _result_payload(result)
    except Exception as exc:
        logger.exception("版本2人工修改任务失败")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/generate/stream")
async def generate_stream(
    prompt: str,
    model_id: str = DEFAULT_MODEL_ID,
    use_llm_motion: bool = True,
    repair_static: bool = True,
) -> StreamingResponse:
    if len(prompt.strip()) < 2:
        raise HTTPException(status_code=400, detail="提示词太短")

    async def events():
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def progress_callback(event: str, data: dict) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, (event, data))

        def run_pipeline() -> None:
            try:
                result = V2Pipeline(
                    model_id=model_id,
                    progress_callback=progress_callback,
                ).run(
                    prompt.strip(),
                    use_llm_motion=use_llm_motion,
                    repair_static=repair_static,
                )
                progress_callback("result", _result_payload(result))
            except Exception as exc:
                logger.exception("版本2流式生成任务失败")
                progress_callback("error", {"detail": str(exc)})

        task = asyncio.create_task(asyncio.to_thread(run_pipeline))
        while True:
            event, data = await queue.get()
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            if event in {"result", "error"}:
                break
        await task

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/output/{filename}")
def output_file(filename: str) -> FileResponse:
    path = (V2_ROOT / "outputs" / filename).resolve()
    output_root = (V2_ROOT / "outputs").resolve()
    if output_root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="输出文件不存在")
    return FileResponse(path)


def _result_payload(result: object) -> dict:
    svg_path = Path(result.svg_path)
    png_path = Path(result.png_path)
    json_path = Path(result.json_path)
    svg = svg_path.read_text(encoding="utf-8")
    report = json.loads(json_path.read_text(encoding="utf-8"))
    payload = result.model_dump()
    payload["svg"] = svg
    payload["report"] = report
    payload["files"] = {
        "svg": f"/api/output/{svg_path.name}",
        "png": f"/api/output/{png_path.name}",
        "json": f"/api/output/{json_path.name}",
    }
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        app_dir=str(V2_ROOT),
    )
