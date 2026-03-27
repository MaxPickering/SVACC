# SVACC - Simple Video Annotator for Classes with Cropping

Desktop Python application for loading MP4 videos, setting START and END points, and saving a single click marker coordinate.

## Features

- Video playback with play/pause and seek slider
- Video list loaded from the `videos/` folder
- START and END timestamp capture at current playback position
- Left-click positive marker (single red marker)
- Right-click negative marker (multiple blue markers)
- ROI mode for rectangular area selection (draw with click-drag)
- Per-video JSON sidecar output in `data/`
- Metadata persistence (duration and available resolution/fps)

## Folder Layout

- `videos/`: place your `.mp4` input files here
- `data/`: generated sidecar JSON files
- `src/`: application source code

## Windows Setup (.venv)

1. Create virtual environment:

   ```powershell
   py -m venv .venv
   ```

2. Activate environment:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. Run app:

   ```powershell
   python -m src.main
   ```

## JSON Schema (per video)

Each video creates one JSON file in `data/` with this structure:

```json
{
  "schema_version": 1,
  "updated_at_utc": "2026-03-27T10:00:00+00:00",
  "metadata": {
    "file_name": "example.mp4",
    "relative_path": "videos/example.mp4",
    "file_size_bytes": 12345678,
    "modified_time_utc": "2026-03-27T09:59:00+00:00",
    "duration_ms": 60000,
    "width": 1920,
    "height": 1080,
    "fps": 30.0
  },
  "annotations": {
    "start_sec": 1.25,
    "end_sec": 10.75,
    "marker": {
      "x_px": 640,
      "y_px": 360,
      "x_norm": 0.333333,
      "y_norm": 0.333333,
      "captured_at_utc": "2026-03-27T10:00:10+00:00"
    },
    "negative_markers": [
      {
        "x_px": 820,
        "y_px": 410,
        "x_norm": 0.427083,
        "y_norm": 0.379630,
        "captured_at_utc": "2026-03-27T10:00:12+00:00"
      }
    ],
    "last_position_ms": 10750
  }
}
```

## Notes

- Positive marker is single-value: each new left click overwrites the previous positive marker.
- Negative markers are multi-value: each right click appends a new negative marker.
- ROI is single-value: each new ROI drag overwrites the previous ROI rectangle.
- Keyboard shortcuts: `Space` play/pause, `Left/Right` seek, `S` set START, `E` set END, `R` toggle ROI mode, `Ctrl+Z` undo last marker (positive or negative).
- START/END validation warns when END is before START.
- If JSON is malformed, the app falls back to default annotations for that video.
