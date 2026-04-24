from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .ingest_service import UploadedContractFile

TASK_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / ".runtime" / "ocr_tasks"
MANIFEST_NAME = "manifest.json"



def _task_dir(task_id: str) -> Path:
    return TASK_RUNTIME_ROOT / task_id



def _sanitize_filename(filename: str, index: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or f"file-{index}").strip("._")
    return f"{index:02d}_{stem or f'file-{index}'}"



def stage_ocr_task_files(task_id: str, files: list[UploadedContractFile]) -> None:
    task_dir = _task_dir(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, str | None]] = []
    for index, file in enumerate(files, start=1):
        stored_name = _sanitize_filename(file.filename, index)
        (task_dir / stored_name).write_bytes(file.content)
        manifest.append(
            {
                "filename": file.filename,
                "content_type": file.content_type,
                "stored_name": stored_name,
            }
        )

    (task_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")



def load_staged_ocr_task_files(task_id: str) -> list[UploadedContractFile]:
    task_dir = _task_dir(task_id)
    manifest_path = task_dir / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files: list[UploadedContractFile] = []
    for item in manifest:
        stored_name = str(item.get("stored_name") or "")
        files.append(
            UploadedContractFile(
                filename=str(item.get("filename") or stored_name or "contract.bin"),
                content=(task_dir / stored_name).read_bytes(),
                content_type=item.get("content_type"),
            )
        )
    return files



def cleanup_staged_ocr_task_files(task_id: str) -> None:
    shutil.rmtree(_task_dir(task_id), ignore_errors=True)
