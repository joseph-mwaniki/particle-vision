"""
GPU Worker HTTP handler.

Serves as both a local development server and the RunPod serverless entry point.
Accepts training requests from the backend and reports progress via callbacks.
"""

import json
import logging
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib import request as urllib_request

from config import HOST, PORT, USE_MOCK, validate_pipeline_environment
from train import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def send_callback(callback_url: str, payload: dict) -> None:
    """POST status update to the backend callback endpoint."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        callback_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            logger.info("Callback sent: %s → %d", payload.get("status"), resp.status)
    except Exception as e:
        logger.error("Callback failed: %s", e)


def process_job(job_id: str, images_path: str, callback_url: str) -> None:
    """Run training pipeline in a background thread."""

    def on_status(
        status: str,
        log_msg: str,
        progress: int,
        **kwargs: Any,
    ) -> None:
        payload: dict[str, Any] = {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "log": log_msg,
        }
        if kwargs.get("splat_path"):
            payload["splat_path"] = kwargs["splat_path"]
        if kwargs.get("collision_path"):
            payload["collision_path"] = kwargs["collision_path"]
        if kwargs.get("error"):
            payload["error"] = kwargs["error"]
        send_callback(callback_url, payload)

    try:
        if not USE_MOCK:
            from config import require_pipeline_environment

            require_pipeline_environment()

        run_pipeline(job_id, images_path, callback_url, on_status, use_mock=USE_MOCK)
    except Exception as exc:
        tb = traceback.format_exc()
        logger.error("Pipeline failed for job %s: %s\n%s", job_id, exc, tb)
        on_status(
            "FAILED",
            f"[{type(exc).__name__}] {exc}",
            0,
            error=str(exc),
        )


def runpod_handler(event: dict) -> dict:
    """
    RunPod serverless handler entry point.

    Expected input:
      {
        "job_id": "job_abc123",
        "images_path": "/workspace/data/uploads/job_abc123/images.zip",
        "callback_url": "https://api.example.com/internal/worker/callback"
      }
    """
    job_id = event.get("job_id")
    images_path = event.get("images_path")
    callback_url = event.get("callback_url")

    if not all([job_id, images_path, callback_url]):
        return {"status": "rejected", "error": "Missing required fields: job_id, images_path, callback_url"}

    thread = threading.Thread(
        target=process_job,
        args=(job_id, images_path, callback_url),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "accepted", "message": "Job accepted by GPU worker"}


class WorkerHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for local development."""

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status_code: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            checks = validate_pipeline_environment()
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "gpu-worker",
                    "use_mock": USE_MOCK,
                    "pipeline": {name: ok for name, (ok, _msg) in checks.items()},
                },
            )
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_json(404, {"error": "Not found"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        result = runpod_handler(event)
        status_code = 202 if result.get("status") == "accepted" else 400
        self._send_json(status_code, result)


def main() -> None:
    mode = "mock" if USE_MOCK else "real (gsplat)"
    server = HTTPServer((HOST, PORT), WorkerHTTPHandler)
    logger.info("GPU worker listening on http://%s:%d [%s mode]", HOST, PORT, mode)
    logger.info("  GET  /health")
    logger.info("  POST /run")
    server.serve_forever()


if __name__ == "__main__":
    main()
