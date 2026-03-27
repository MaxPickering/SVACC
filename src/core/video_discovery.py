from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {".mp4"}


def list_videos(videos_dir: Path) -> list[Path]:
    if not videos_dir.exists():
        return []

    files = [
        path
        for path in videos_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort(key=lambda p: p.name.lower())
    return files
