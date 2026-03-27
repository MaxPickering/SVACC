from datetime import datetime, timezone
from pathlib import Path

from src.core.video_discovery import list_videos
from src.data.json_store import JsonStore
from src.data.models import VideoMetadata, VideoRecord


class VideoManager:
    """Manages video discovery, loading, and metadata."""

    def __init__(self, store: JsonStore, project_root: Path) -> None:
        self.store = store
        self.project_root = project_root
        self.videos_dir = project_root / "videos"

    def list_videos(self) -> list[Path]:
        """Get all videos in videos directory."""
        return list_videos(self.videos_dir)

    def get_video_metadata(self, video_path: Path) -> VideoMetadata:
        """Build metadata for a video file."""
        stat = video_path.stat()
        relative_path = str(video_path.relative_to(self.project_root)).replace("\\", "/")
        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0)
        
        return VideoMetadata(
            file_name=video_path.name,
            relative_path=relative_path,
            file_size_bytes=stat.st_size,
            modified_time_utc=modified.isoformat(),
        )

    def load_or_create_record(self, video_path: Path) -> VideoRecord:
        """Load or create a video record."""
        metadata = self.get_video_metadata(video_path)
        return self.store.load_or_create(metadata)

    def save_record(self, record: VideoRecord) -> None:
        """Save a video record."""
        self.store.save(record)

    def delete_all_annotations(self) -> int:
        """Delete all annotation files. Returns count deleted."""
        deleted_count = 0
        data_dir = self.store.data_dir
        for json_file in data_dir.glob("*.json"):
            try:
                json_file.unlink()
                deleted_count += 1
            except OSError:
                continue
        return deleted_count

    def delete_video_annotations(self, relative_path: str) -> bool:
        """Delete annotations for a specific video. Returns True if deleted."""
        return self.store.delete_for_video(relative_path)

    def record_is_complete(self, record: VideoRecord | None) -> bool:
        """Check if a record has all required annotations."""
        if record is None:
            return False
        return (
            record.annotations.start_sec is not None
            and record.annotations.end_sec is not None
            and record.annotations.marker is not None
        )
