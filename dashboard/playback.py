import importlib.util
import sys
import tempfile
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Callable

import pandas as pd

from dashboard import database


ROOT_PATH = Path(__file__).resolve().parents[1]


@dataclass
class PlaybackResult:
    video: bytes
    canonical_ids: list[int]
    tracker_ids: list[int]
    incidents: pd.DataFrame
    frame_count: int
    fps: float
    playback_speed: float


def _load_backend_module(
    database_path: Path, text_log_path: Path | None = None
):
    root = str(ROOT_PATH)
    if root not in sys.path:
        sys.path.insert(0, root)

    import db

    original_database_path = db.DB_PATH
    original_text_log_path = db.TEXT_LOG_PATH
    db.DB_PATH = str(database_path.resolve())
    db.TEXT_LOG_PATH = str(
        (text_log_path or ROOT_PATH / "incident_log.txt").resolve()
    )

    module_name = f"_campus_security_playback_{uuid.uuid4().hex}"
    module_path = ROOT_PATH / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load the detection backend: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loaded = False
    try:
        spec.loader.exec_module(module)
        loaded = True
    finally:
        if not loaded:
            db.DB_PATH = original_database_path
            db.TEXT_LOG_PATH = original_text_log_path
            sys.modules.pop(module_name, None)
    return (
        module_name,
        module,
        db,
        original_database_path,
        original_text_log_path,
    )


def _unload_backend_module(
    module_name: str,
    db_module: ModuleType,
    database_path: str,
    text_log_path: str,
) -> None:
    db_module.DB_PATH = database_path
    db_module.TEXT_LOG_PATH = text_log_path
    sys.modules.pop(module_name, None)


def process_sample_video(
    camera: object,
    recording: Path,
    database_path: Path,
    progress_callback: Callable[[int, int], None] | None = None,
    frame_callback: Callable[
        [object, int, int, list[int], list[int]], None
    ] | None = None,
    text_log_path: Path | None = None,
    playback_speed: float = 1.0,
) -> PlaybackResult:
    import cv2
    import imageio_ffmpeg

    recording = recording.resolve()
    if not recording.is_file():
        raise FileNotFoundError(f"Sample video not found: {recording}")

    boundary_id = database.latest_incident_id(database_path)
    (
        module_name,
        backend,
        db_module,
        original_database_path,
        original_text_log_path,
    ) = _load_backend_module(database_path, text_log_path)
    capture = cv2.VideoCapture(str(recording))
    if not capture.isOpened():
        capture.release()
        _unload_backend_module(
            module_name, db_module, original_database_path, original_text_log_path
        )
        raise RuntimeError(f"Could not open sample video: {recording}")

    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if fps <= 0:
        capture.release()
        _unload_backend_module(
            module_name, db_module, original_database_path, original_text_log_path
        )
        raise RuntimeError(f"Sample video has an invalid frame rate: {recording}")
    if playback_speed <= 0:
        capture.release()
        _unload_backend_module(
            module_name, db_module, original_database_path, original_text_log_path
        )
        raise ValueError("Playback speed must be greater than zero.")
    preview_interval = max(1, round(fps / 4))

    playback_camera = replace(
        camera,
        video_path=str(recording),
        model_path=str((ROOT_PATH / camera.model_path).resolve()),
        tracker_config=str((ROOT_PATH / camera.tracker_config).resolve()),
    )
    try:
        state = backend.CameraState(playback_camera)
    except (ImportError, OSError, RuntimeError, ValueError):
        capture.release()
        _unload_backend_module(
            module_name, db_module, original_database_path, original_text_log_path
        )
        raise
    canonical_ids: set[int] = set()
    tracker_ids: set[int] = set()
    original_get_canonical_id = state.reidentifier.get_canonical_id
    original_model_track = state.model.track

    def collect_person_id(**kwargs: object) -> int:
        canonical_id = original_get_canonical_id(**kwargs)
        canonical_ids.add(canonical_id)
        return canonical_id

    def collect_tracker_ids(*args: object, **kwargs: object):
        results = original_model_track(*args, **kwargs)
        if results:
            for box in results[0].boxes:
                if (
                    box.cls is not None
                    and len(box.cls) > 0
                    and state.model.names.get(int(box.cls[0])) == "person"
                    and box.id is not None
                    and len(box.id) > 0
                ):
                    tracker_ids.add(int(box.id[0]))
        return results

    state.reidentifier.get_canonical_id = collect_person_id
    state.model.track = collect_tracker_ids
    frame_count = 0

    try:
        with tempfile.TemporaryDirectory(
            prefix="campus-security-playback-"
        ) as directory:
            output_path = Path(directory) / "tracked.mp4"
            first_frame = None
            while first_frame is None:
                success, frame = capture.read()
                if not success:
                    break
                first_frame = frame
            if first_frame is None:
                raise RuntimeError(f"Sample video contains no readable frames: {recording}")

            height, width = first_frame.shape[:2]
            # Ensure dimensions are divisible by 2 for H.264 (yuv420p) encoding
            width = width - (width % 2)
            height = height - (height % 2)
            writer = imageio_ffmpeg.write_frames(
                str(output_path),
                (width, height),
                fps=fps * playback_speed,
                codec="libx264",
                pix_fmt_in="bgr24",
                pix_fmt_out="yuv420p",
                output_params=["-preset", "ultrafast", "-movflags", "+faststart"],
                macro_block_size=1,
            )
            writer.send(None)
            try:
                frame = first_frame
                while frame is not None:
                    if frame.shape[0] != height or frame.shape[1] != width:
                        frame = frame[:height, :width]
                    annotated = backend.process_frame(state, frame)
                    if annotated.shape[0] != height or annotated.shape[1] != width:
                        annotated = annotated[:height, :width]
                    writer.send(annotated.tobytes())
                    frame_count += 1
                    if progress_callback is not None and (
                        frame_count % preview_interval == 0
                        or frame_count == total_frames
                    ):
                        progress_callback(frame_count, total_frames)
                    if frame_callback is not None and (
                        frame_count % preview_interval == 0
                        or frame_count == total_frames
                    ):
                        frame_callback(
                            annotated,
                            frame_count,
                            total_frames,
                            sorted(tracker_ids),
                            sorted(canonical_ids),
                        )

                    success, next_frame = capture.read()
                    frame = next_frame if success else None
            finally:
                writer.close()

            if frame_count == 0 or not output_path.is_file():
                raise RuntimeError("No annotated video frames were produced.")
            video = output_path.read_bytes()
    finally:
        capture.release()
        _unload_backend_module(
            module_name, db_module, original_database_path, original_text_log_path
        )

    new_incidents = database.load_incidents_after(
        database_path, boundary_id, camera.camera_id
    )
    return PlaybackResult(
        video=video,
        canonical_ids=sorted(canonical_ids),
        tracker_ids=sorted(tracker_ids),
        incidents=new_incidents,
        frame_count=frame_count,
        fps=fps,
        playback_speed=playback_speed,
    )
