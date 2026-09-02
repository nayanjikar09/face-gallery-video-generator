from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from sklearn.cluster import DBSCAN

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
SIMILARITY_THRESHOLD = 0.45
MIN_FACE_SIZE = 10
THUMBNAIL_SIZE = 200


@dataclass(frozen=True)
class Settings:
    base_path: Path
    model_name: str = os.environ.get("FACE_MODEL", "buffalo_l")
    det_size: int = int(os.environ.get("FACE_DET_SIZE", "320"))
    video_samples: int = int(os.environ.get("VIDEO_SAMPLES", "30"))
    flip_fallback: bool = os.environ.get("FACE_FLIP_FALLBACK") == "1"

    @property
    def images_dir(self) -> Path:
        return self.base_path / "images"

    @property
    def videos_dir(self) -> Path:
        return self.base_path / "videos"

    @property
    def data_dir(self) -> Path:
        return self.base_path / "gallery_data"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def gallery_file(self) -> Path:
        return self.data_dir / "gallery_data.json"

    @property
    def index_file(self) -> Path:
        return self.data_dir / "processed.json"


def default_base_path() -> Path:
    configured = os.environ.get("GALLERY_BASE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent


def prepare_directories(settings: Settings) -> None:
    for directory in (settings.images_dir, settings.videos_dir,
                      settings.data_dir, settings.thumbnails_dir):
        directory.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return fallback


def atomic_json_write(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, default=json_default)
    temporary.replace(path)


def json_default(value: Any) -> Any:
    """Convert NumPy scalars/arrays before JSON encoding.

    OpenCV and InsightFace return NumPy values; this guard keeps persistence
    safe even when a future change introduces another NumPy-derived field.
    """
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON-encode {type(value).__name__}")


def media_record(path: Path, kind: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path.resolve()),
        "size": stat.st_size,
        "modified": stat.st_mtime_ns,
        "type": kind,
    }


def scan_media(directory: Path, extensions: set[str], kind: str) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    return sorted(
        (media_record(path, kind) for path in directory.iterdir()
         if path.is_file() and path.suffix.lower() in extensions),
        key=lambda item: item["name"].casefold(),
    )


def fingerprint(media: dict[str, Any]) -> dict[str, int]:
    return {"size": int(media["size"]), "modified": int(media["modified"])}


def is_changed(media: dict[str, Any], index: dict[str, Any]) -> bool:
    return index.get(media["name"], {}) != fingerprint(media)


def initialise_face_app(settings: Settings) -> FaceAnalysis:
    """Create the model once, trying smaller compatible fallbacks if needed."""
    names = [settings.model_name, "buffalo_m", "buffalo_s"]
    errors: list[str] = []
    for name in dict.fromkeys(names):
        try:
            app = FaceAnalysis(name=name, providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=0, det_size=(settings.det_size, settings.det_size))
            print(f"Face model ready: {name} ({settings.det_size}x{settings.det_size})")
            return app
        except Exception as error:  # model availability differs by installation
            errors.append(f"{name}: {error}")
    raise RuntimeError("Unable to initialise InsightFace. " + " | ".join(errors))


def clip_box(box: np.ndarray, width: int, height: int) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = box.astype(int)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 - x1 < MIN_FACE_SIZE or y2 - y1 < MIN_FACE_SIZE:
        return None
    return int(x1), int(y1), int(x2), int(y2)


def analyse_frame(frame: np.ndarray, app: FaceAnalysis, *, allow_flip: bool = False) -> list[dict[str, Any]]:
    """Run one inference call and retain only valid crops and embeddings."""
    if frame is None or frame.size == 0:
        return []
    faces = app.get(frame)
    if not faces and allow_flip:
        mirrored = cv2.flip(frame, 1)
        faces = app.get(mirrored)
        width = frame.shape[1]
        for face in faces:
            x1, y1, x2, y2 = face.bbox
            face.bbox = np.array([width - x2, y1, width - x1, y2])

    height, width = frame.shape[:2]
    records: list[dict[str, Any]] = []
    for face in faces:
        box = clip_box(face.bbox, width, height)
        if box is None:
            continue
        x1, y1, x2, y2 = box
        records.append({
            "bbox": [x1, y1, x2, y2],
            "embedding": np.asarray(face.embedding, dtype=np.float32),
            "crop": frame[y1:y2, x1:x2].copy(),
            "det_score": float(face.det_score),
        })
    return records


def read_image_faces(media: dict[str, Any], app: FaceAnalysis, settings: Settings) -> list[dict[str, Any]]:
    frame = cv2.imread(media["path"])
    if frame is None:
        print(f"  Skipped unreadable image: {media['name']}")
        return []
    height, width = frame.shape[:2]
    if min(height, width) < 64:
        scale = max(2, int(np.ceil(128 / min(height, width))))
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return attach_source(analyse_frame(frame, app, allow_flip=settings.flip_fallback), media)


def sample_positions(frame_count: int, samples: int) -> np.ndarray:
    if frame_count <= 0:
        return np.empty(0, dtype=np.int64)
    return np.unique(np.linspace(0, frame_count - 1, num=min(frame_count, samples), dtype=np.int64))


def read_video_faces(media: dict[str, Any], app: FaceAnalysis, settings: Settings) -> list[dict[str, Any]]:
    cap = cv2.VideoCapture(media["path"])
    if not cap.isOpened():
        print(f"  Skipped unreadable video: {media['name']}")
        return []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        positions = sample_positions(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), settings.video_samples)
        result: list[dict[str, Any]] = []
        # Seeking only requested samples avoids detector inference on irrelevant frames.
        for index in positions:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = cap.read()
            if not ok:
                continue
            for face in attach_source(analyse_frame(frame, app), media):
                face["frame"] = int(index)
                face["timestamp"] = float(index / fps) if fps > 0 else 0.0
                result.append(face)
        return result
    finally:
        cap.release()


def attach_source(faces: list[dict[str, Any]], media: dict[str, Any]) -> list[dict[str, Any]]:
    for face in faces:
        face["media"] = media["name"]
        face["media_path"] = media["path"]
        face["source_type"] = media["type"]
    return faces


def process_media(items: Iterable[dict[str, Any]], app: FaceAnalysis, settings: Settings) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    faces: list[dict[str, Any]] = []
    processed: dict[str, dict[str, Any]] = {}
    items = list(items)
    for number, media in enumerate(items, 1):
        print(f"[{number}/{len(items)}] {media['name']}")
        try:
            found = (read_image_faces(media, app, settings) if media["type"] == "image"
                     else read_video_faces(media, app, settings))
        except Exception as error:
            print(f"  Error: {error}")
            found = []
        info = dict(media)
        info["faces_detected"] = len(found)
        processed[media["name"]] = info
        faces.extend(found)
        print(f"  Faces: {len(found)}")
    return faces, processed


def normalized_rows(vectors: list[Any]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)


def match_existing(faces: list[dict[str, Any]], persons: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [(person, person.get("embedding")) for person in persons if person.get("embedding")]
    if not faces or not candidates:
        return [], faces
    person_vectors = normalized_rows([embedding for _, embedding in candidates])
    face_vectors = normalized_rows([face["embedding"] for face in faces])
    scores = face_vectors @ person_vectors.T
    best = scores.argmax(axis=1)
    matched, unmatched = [], []
    for face, position, score in zip(faces, best, scores[np.arange(len(faces)), best]):
        if score >= SIMILARITY_THRESHOLD:
            face["person"] = candidates[int(position)][0]
            matched.append(face)
        else:
            unmatched.append(face)
    return matched, unmatched


def occurrence(face: dict[str, Any]) -> dict[str, Any]:
    item = {"media": face["media"], "confidence": face["det_score"], "bbox": face["bbox"]}
    if face["source_type"] == "video":
        item.update(frame=face["frame"], timestamp=face["timestamp"])
    return item


def add_faces_to_person(person: dict[str, Any], faces: list[dict[str, Any]], media_info: dict[str, dict[str, Any]]) -> None:
    by_name = {entry["name"]: entry for entry in person.setdefault("media", [])}
    occurrences = person.setdefault("occurrences", [])
    for face in faces:
        name = face["media"]
        entry = by_name.get(name)
        if entry is None:
            item = media_info[name]
            entry = {"name": name, "path": item["path"], "type": item["type"], "occurrences": 0}
            person["media"].append(entry)
            by_name[name] = entry
        entry["occurrences"] += 1
        occurrences.append(occurrence(face))
    person["face_count"] = len(occurrences)
    person["media_count"] = len(person["media"])


def remove_reprocessed_media(persons: list[dict[str, Any]], media_names: set[str]) -> None:
    """Remove old sightings before replacing a modified file's analysis."""
    for person in persons:
        person["occurrences"] = [entry for entry in person.get("occurrences", [])
                                 if entry.get("media") not in media_names]
        person["media"] = [entry for entry in person.get("media", [])
                           if entry.get("name") not in media_names]
        person["face_count"] = len(person["occurrences"])
        person["media_count"] = len(person["media"])


def create_people(faces: list[dict[str, Any]], persons: list[dict[str, Any]], media_info: dict[str, dict[str, Any]], settings: Settings) -> int:
    if not faces:
        return 0
    vectors = normalized_rows([face["embedding"] for face in faces])
    labels = DBSCAN(eps=1 - SIMILARITY_THRESHOLD, min_samples=1, metric="cosine").fit_predict(vectors)
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for label, face in zip(labels, faces):
        groups[int(label)].append(face)
    next_id = max((int(person.get("id", -1)) for person in persons), default=-1) + 1
    for group in groups.values():
        representative = max(group, key=lambda face: face["det_score"])
        thumbnail = f"person_{next_id}.jpg"
        crop = representative["crop"]
        if crop.size:
            crop = cv2.resize(crop, (THUMBNAIL_SIZE, THUMBNAIL_SIZE), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(settings.thumbnails_dir / thumbnail), crop)
        person = {"id": next_id, "thumbnail": thumbnail,
                  "embedding": representative["embedding"].astype(float).tolist(),
                  "media": [], "occurrences": []}
        add_faces_to_person(person, group, media_info)
        persons.append(person)
        next_id += 1
    return len(groups)


def build_gallery(items: list[dict[str, Any]], app: FaceAnalysis, settings: Settings, *, incremental: bool) -> dict[str, int]:
    existing = read_json(settings.gallery_file, {"media": [], "persons": []})
    people = existing.get("persons", [])
    media_by_name = {item["name"]: item for item in existing.get("media", [])}
    index = read_json(settings.index_file, {})
    targets = [item for item in items if not incremental or is_changed(item, index)]
    if not targets:
        print("All media is unchanged; nothing to process.")
        return {"processed": 0, "total_faces": 0, "new_persons": 0}
    # A modified file replaces rather than duplicates its old detections.
    remove_reprocessed_media(people, {item["name"] for item in targets})
    people[:] = [person for person in people if person.get("occurrences")]
    faces, processed = process_media(targets, app, settings)
    media_by_name.update(processed)
    matched, unmatched = match_existing(faces, people)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for face in matched:
        grouped[id(face["person"])].append(face)
    for group in grouped.values():
        add_faces_to_person(group[0]["person"], group, processed)
    new_people = create_people(unmatched, people, processed, settings)
    gallery = {"media": sorted(media_by_name.values(), key=lambda item: item["name"].casefold()),
               "persons": people,
               "stats": {"total_media": len(media_by_name),
                         "total_faces": sum(person.get("face_count", 0) for person in people),
                         "total_persons": len(people)}}
    atomic_json_write(settings.gallery_file, gallery)
    for item in processed.values():
        index[item["name"]] = fingerprint(item)
    atomic_json_write(settings.index_file, index)
    return {"processed": len(processed), "total_faces": len(faces), "new_persons": new_people}


def process_new_media(new_media_names: list[str]) -> dict[str, int]:
    """Compatibility entry point for app.py: process named files in gallery folders."""
    settings = Settings(default_base_path())
    prepare_directories(settings)
    items = scan_media(settings.images_dir, IMAGE_EXTENSIONS, "image") + scan_media(settings.videos_dir, VIDEO_EXTENSIONS, "video")
    wanted = set(new_media_names)
    return build_gallery([item for item in items if item["name"] in wanted], initialise_face_app(settings), settings, incremental=False)


process_new_images = process_new_media


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an incremental face gallery")
    parser.add_argument("--media-dir", type=Path, help="Process only media from this directory")
    args = parser.parse_args()
    settings = Settings(default_base_path())
    prepare_directories(settings)
    app = initialise_face_app(settings)
    if args.media_dir:
        directory = args.media_dir.expanduser().resolve()
        items = (scan_media(directory, IMAGE_EXTENSIONS, "image") +
                 scan_media(directory, VIDEO_EXTENSIONS, "video"))
        result = build_gallery(items, app, settings, incremental=False)
    else:
        items = (scan_media(settings.images_dir, IMAGE_EXTENSIONS, "image") +
                 scan_media(settings.videos_dir, VIDEO_EXTENSIONS, "video"))
        result = build_gallery(items, app, settings, incremental=True)
    print(f"Completed: {result['processed']} media, {result['total_faces']} faces, {result['new_persons']} new people")


if __name__ == "__main__":
    main()
