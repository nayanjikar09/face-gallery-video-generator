#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Face Gallery Builder - Image & Video Version
Processes images and videos, builds the gallery data

Usage:
    python build_gallery.py [--media-dir DIRECTORY]

Environment Variables:
    GALLERY_BASE_PATH - Base path for the gallery
"""

import os
import sys
import cv2
import numpy as np
import json
import time
import argparse
from pathlib import Path
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# Face detection
import insightface
from insightface.app import FaceAnalysis
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import normalize

# ==================== CONFIGURATION ====================

def get_base_path():
    """Get the base path dynamically"""
    env_path = os.environ.get('GALLERY_BASE_PATH')
    if env_path:
        return Path(env_path)
    
    current_dir = Path(__file__).parent
    if (current_dir / 'images').exists() and (current_dir / 'videos').exists():
        return current_dir
    
    return Path(r'E:\00000\Rahstaa\My_gallery_2')

BASE_PATH = get_base_path()
IMAGE_FOLDER = str(BASE_PATH / "images")
VIDEO_FOLDER = str(BASE_PATH / "videos")
GALLERY_FOLDER = str(BASE_PATH / "gallery_data")
THUMBNAIL_FOLDER = os.path.join(GALLERY_FOLDER, "thumbnails")
PREVIEW_FOLDER = os.path.join(GALLERY_FOLDER, "video_previews")
PROCESSED_FILE = os.path.join(GALLERY_FOLDER, "processed.json")
SIMILARITY_THRESHOLD = 0.45
MAX_PERSONS = 50
MIN_FACE_SIZE = 10
FRAME_INTERVAL = 30
MAX_FRAMES_PER_VIDEO = 30

# Create folders
os.makedirs(GALLERY_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

print("=" * 60)
print("📸 FACE GALLERY BUILDER - IMAGES & VIDEOS")
print("=" * 60)
print(f"📁 Base Path: {BASE_PATH}")
print(f"📁 Images folder: {IMAGE_FOLDER}")
print(f"📁 Videos folder: {VIDEO_FOLDER}")
print(f"📁 Gallery folder: {GALLERY_FOLDER}")
print("=" * 60)

# ==================== ARGUMENT PARSING ====================

def parse_arguments():
    parser = argparse.ArgumentParser(description='Build face gallery from images and videos')
    parser.add_argument('--media-dir', type=str, default=None, help='Directory containing media to process')
    return parser.parse_args()

# ==================== IMAGE SCANNER ====================

def list_images(folder_path):
    """Find all image files"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    images = []
    
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        return images
    
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                try:
                    img = cv2.imread(file_path)
                    height, width = img.shape[:2] if img is not None else (0, 0)
                except:
                    height, width = 0, 0
                    
                images.append({
                    'name': file,
                    'path': file_path,
                    'size': os.path.getsize(file_path),
                    'modified': os.path.getmtime(file_path),
                    'width': width,
                    'height': height
                })
    
    return sorted(images, key=lambda x: x['name'])

def list_videos(folder_path):
    """Find all video files"""
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    videos = []
    
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        return videos
    
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            ext = os.path.splitext(file)[1].lower()
            if ext in video_extensions:
                videos.append({
                    'name': file,
                    'path': file_path,
                    'size': os.path.getsize(file_path),
                    'modified': os.path.getmtime(file_path)
                })
    
    return sorted(videos, key=lambda x: x['name'])

# ==================== FACE DETECTION ====================

print("\n🔍 Initializing face detection...")

face_app = None

try:
    face_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
    face_app.prepare(ctx_id=0, det_size=(320, 320))
    print("✅ Face detection initialized with buffalo_l model!")
except Exception as e:
    print(f"⚠️ Error with buffalo_l: {e}")
    try:
        face_app = FaceAnalysis(name='buffalo_m', providers=['CPUExecutionProvider'])
        face_app.prepare(ctx_id=0, det_size=(320, 320))
        print("✅ Face detection initialized with buffalo_m model!")
    except Exception as e2:
        print(f"⚠️ Error with buffalo_m: {e2}")
        try:
            face_app = FaceAnalysis(providers=['CPUExecutionProvider'])
            face_app.prepare(ctx_id=0, det_size=(320, 320))
            print("✅ Face detection initialized with default model!")
        except Exception as e3:
            print(f"❌ All face detection models failed: {e3}")
            face_app = None

def detect_faces_in_image(image_path, face_app, use_upscale=False):
    """Detect faces in an image with optional upscaling for small images"""
    if face_app is None:
        return [], None
    
    frame = cv2.imread(image_path)
    if frame is None:
        return [], None
    
    h, w = frame.shape[:2]
    if h < 64 or w < 64:
        scale_factor = max(2, int(128 / min(h, w)))
        new_w = w * scale_factor
        new_h = h * scale_factor
        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        print(f"    🔍 Upscaled image from {w}x{h} to {new_w}x{new_h}")
    
    detected_faces = []
    
    try:
        faces = face_app.get(frame)
        
        if len(faces) == 0:
            flipped_frame = cv2.flip(frame, 1)
            faces = face_app.get(flipped_frame)
            for face in faces:
                bbox = face.bbox.astype(int)
                h, w = frame.shape[:2]
                x1, y1, x2, y2 = bbox
                new_x1 = w - x2
                new_x2 = w - x1
                face.bbox = np.array([new_x1, y1, new_x2, y2])
        
        for face in faces:
            bbox = face.bbox.astype(int)
            x1, y1, x2, y2 = bbox
            h, w = frame.shape[:2]
            
            x1 = max(0, min(x1, w-1))
            y1 = max(0, min(y1, h-1))
            x2 = max(0, min(x2, w))
            y2 = max(0, min(y2, h))
            
            if (x2 - x1) >= MIN_FACE_SIZE and (y2 - y1) >= MIN_FACE_SIZE:
                face_crop = frame[y1:y2, x1:x2]
                detected_faces.append({
                    'bbox': [int(x1), int(y1), int(x2), int(y2)],
                    'embedding': face.embedding,
                    'crop': face_crop,
                    'det_score': float(face.det_score)
                })
        
        return detected_faces, frame
    except Exception as e:
        print(f"⚠️ Error detecting faces: {e}")
        return [], frame

def extract_frames_from_video(video_path, face_app, interval=30, max_frames=30):
    """Extract frames from video and detect faces"""
    all_faces = []
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return all_faces
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if fps <= 0:
        cap.release()
        return all_faces
    
    frame_count = 0
    extracted_count = 0
    
    while extracted_count < max_frames and frame_count < total_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_count % interval == 0:
            try:
                faces = face_app.get(frame)
                for face in faces:
                    bbox = face.bbox.astype(int)
                    x1, y1, x2, y2 = bbox
                    h, w = frame.shape[:2]
                    
                    x1 = max(0, min(x1, w-1))
                    y1 = max(0, min(y1, h-1))
                    x2 = max(0, min(x2, w))
                    y2 = max(0, min(y2, h))
                    
                    if (x2 - x1) >= MIN_FACE_SIZE and (y2 - y1) >= MIN_FACE_SIZE:
                        face_crop = frame[y1:y2, x1:x2]
                        all_faces.append({
                            'video': os.path.basename(video_path),
                            'video_path': video_path,
                            'frame': frame_count,
                            'timestamp': frame_count / fps if fps > 0 else 0,
                            'bbox': [int(x1), int(y1), int(x2), int(y2)],
                            'embedding': face.embedding,
                            'crop': face_crop,
                            'det_score': float(face.det_score)
                        })
                extracted_count += 1
            except Exception as e:
                print(f"⚠️ Error in frame {frame_count}: {e}")
        
        frame_count += 1
    
    cap.release()
    return all_faces

def get_face_embedding_from_image(image_path, face_app):
    """Get face embedding from an image"""
    faces, _ = detect_faces_in_image(image_path, face_app, use_upscale=True)
    if faces:
        return faces[0]['embedding']
    return None

# ==================== MERGE DUPLICATE PERSONS ====================

def merge_duplicate_persons(persons, face_app):
    """Merge duplicate persons based on face similarity"""
    if len(persons) <= 1:
        return persons
    
    print(f"\n🔍 Checking for duplicate persons...")
    
    person_embeddings = []
    valid_persons = []
    
    for person in persons:
        thumb_path = os.path.join(THUMBNAIL_FOLDER, person['thumbnail'])
        if os.path.exists(thumb_path):
            embedding = get_face_embedding_from_image(thumb_path, face_app)
            if embedding is not None:
                person_embeddings.append(embedding)
                valid_persons.append(person)
            else:
                valid_persons.append(person)
                person_embeddings.append(None)
        else:
            valid_persons.append(person)
            person_embeddings.append(None)
    
    if len(valid_persons) <= 1:
        return valid_persons
    
    merged_groups = []
    used_indices = set()
    
    for i in range(len(valid_persons)):
        if i in used_indices:
            continue
            
        if person_embeddings[i] is None:
            merged_groups.append([i])
            used_indices.add(i)
            continue
        
        group = [i]
        emb_i = person_embeddings[i]
        emb_i_norm = emb_i / np.linalg.norm(emb_i)
        
        for j in range(i + 1, len(valid_persons)):
            if j in used_indices or person_embeddings[j] is None:
                continue
            
            emb_j = person_embeddings[j]
            emb_j_norm = emb_j / np.linalg.norm(emb_j)
            similarity = np.dot(emb_i_norm, emb_j_norm)
            
            if similarity > SIMILARITY_THRESHOLD:
                group.append(j)
                used_indices.add(j)
                print(f"  ✅ Merged Person #{valid_persons[i]['id']} with Person #{valid_persons[j]['id']} (sim: {similarity:.3f})")
        
        used_indices.add(i)
        merged_groups.append(group)
    
    merged_persons = []
    
    for group in merged_groups:
        if len(group) == 1:
            merged_persons.append(valid_persons[group[0]])
        else:
            base_person = valid_persons[group[0]].copy()
            
            all_media = {}
            all_occurrences = []
            
            for idx in group:
                person = valid_persons[idx]
                for m in person.get('media', []):
                    if m['name'] not in all_media:
                        all_media[m['name']] = m
                all_occurrences.extend(person.get('occurrences', []))
            
            base_person['media'] = list(all_media.values())
            base_person['occurrences'] = all_occurrences
            base_person['face_count'] = len(all_occurrences)
            base_person['media_count'] = len(all_media)
            
            best_person = max([valid_persons[idx] for idx in group], key=lambda x: x.get('face_count', 0))
            base_person['thumbnail'] = best_person['thumbnail']
            
            merged_persons.append(base_person)
            print(f"  ✅ Merged {len(group)} persons into Person #{base_person['id']}")
    
    print(f"  ✅ {len(valid_persons)} persons merged into {len(merged_persons)} unique persons")
    
    return merged_persons

# ==================== PROCESS IMAGES ====================

def process_all_images(images, face_app):
    """Process all images and extract faces"""
    all_faces = []
    image_info = {}
    
    print(f"\n🖼️ Processing {len(images)} images...")
    print("-" * 50)
    
    for idx, image in enumerate(images):
        image_name = image['name']
        image_path = image['path']
        
        print(f"  [{idx+1}/{len(images)}] {image_name} (size: {image.get('width', '?')}x{image.get('height', '?')})")
        
        faces, frame = detect_faces_in_image(image_path, face_app, use_upscale=True)
        face_count = len(faces)
        
        image_info[image_name] = {
            'name': image_name,
            'path': image_path,
            'size': image['size'],
            'faces_detected': face_count,
            'modified': image['modified'],
            'type': 'image'
        }
        
        for face in faces:
            all_faces.append({
                'media': image_name,
                'media_path': image_path,
                'embedding': face['embedding'],
                'bbox': face['bbox'],
                'crop': face['crop'],
                'det_score': face['det_score'],
                'source_type': 'image'
            })
        
        print(f"    👤 Faces detected: {face_count}")
    
    return all_faces, image_info

def process_all_videos(videos, face_app):
    """Process all videos and extract faces"""
    all_faces = []
    video_info = {}
    
    print(f"\n🎬 Processing {len(videos)} videos...")
    print("-" * 50)
    
    for idx, video in enumerate(videos):
        video_name = video['name']
        video_path = video['path']
        
        print(f"  [{idx+1}/{len(videos)}] {video_name}")
        
        faces = extract_frames_from_video(video_path, face_app, FRAME_INTERVAL, MAX_FRAMES_PER_VIDEO)
        face_count = len(faces)
        
        video_info[video_name] = {
            'name': video_name,
            'path': video_path,
            'size': video['size'],
            'faces_detected': face_count,
            'modified': video['modified'],
            'type': 'video'
        }
        
        for face in faces:
            all_faces.append({
                'media': video_name,
                'media_path': video_path,
                'embedding': face['embedding'],
                'bbox': face['bbox'],
                'crop': face['crop'],
                'det_score': face['det_score'],
                'source_type': 'video',
                'frame': face['frame'],
                'timestamp': face['timestamp']
            })
        
        print(f"    👤 Faces detected: {face_count}")
    
    return all_faces, video_info

def cluster_faces(face_records, eps=0.4, min_samples=1):
    """Cluster face embeddings using DBSCAN"""
    if not face_records:
        return face_records
    
    try:
        embeddings = np.array([face['embedding'] for face in face_records])
        embeddings = normalize(embeddings)
        
        clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
        labels = clustering.fit_predict(embeddings)
        
        for i, face in enumerate(face_records):
            face['cluster'] = int(labels[i])
        
        return face_records
    except Exception as e:
        print(f"⚠️ Clustering error: {e}")
        for face in face_records:
            face['cluster'] = -1
        return face_records

def get_person_embedding(person, face_app):
    """Get embedding for a person from their thumbnail"""
    thumb_path = os.path.join(THUMBNAIL_FOLDER, person['thumbnail'])
    if os.path.exists(thumb_path):
        return get_face_embedding_from_image(thumb_path, face_app)
    return None

def process_media_from_dir(media_dir, face_app):
    """Process only media from a specific directory (for uploads)"""
    all_faces = []
    all_media_info = {}
    
    media_path = Path(media_dir)
    if not media_path.exists():
        print(f"⚠️ Media directory not found: {media_dir}")
        return all_faces, all_media_info
    
    # Process images in media_dir
    image_data = []
    for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
        for img_path in media_path.glob(f'*{ext}'):
            image_data.append({
                'name': img_path.name,
                'path': str(img_path),
                'size': img_path.stat().st_size,
                'modified': img_path.stat().st_mtime,
                'width': 0,
                'height': 0
            })
        for img_path in media_path.glob(f'*{ext.upper()}'):
            image_data.append({
                'name': img_path.name,
                'path': str(img_path),
                'size': img_path.stat().st_size,
                'modified': img_path.stat().st_mtime,
                'width': 0,
                'height': 0
            })
    
    if image_data:
        image_faces, image_info = process_all_images(image_data, face_app)
        all_faces.extend(image_faces)
        all_media_info.update(image_info)
    
    # Process videos in media_dir
    video_data = []
    for ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
        for vid_path in media_path.glob(f'*{ext}'):
            video_data.append({
                'name': vid_path.name,
                'path': str(vid_path),
                'size': vid_path.stat().st_size,
                'modified': vid_path.stat().st_mtime
            })
        for vid_path in media_path.glob(f'*{ext.upper()}'):
            video_data.append({
                'name': vid_path.name,
                'path': str(vid_path),
                'size': vid_path.stat().st_size,
                'modified': vid_path.stat().st_mtime
            })
    
    if video_data:
        video_faces, video_info = process_all_videos(video_data, face_app)
        all_faces.extend(video_faces)
        all_media_info.update(video_info)
    
    return all_faces, all_media_info

# ==================== PROCESS NEW MEDIA (for upload) ====================

def process_new_media(new_media_names):
    """Process newly uploaded media (images and videos) and update gallery"""
    print("\n" + "=" * 60)
    print("🔄 PROCESS_NEW_MEDIA CALLED")
    print("=" * 60)
    print(f"📸 New media names: {new_media_names}")
    
    if face_app is None:
        print("❌ Face detection is not available.")
        return {'processed': 0, 'message': 'Face detection not available', 'total_faces': 0, 'new_persons': 0}
    
    print(f"✅ Face detection is available")
    
    # Get all images and videos from main folders
    all_images = list_images(IMAGE_FOLDER)
    all_videos = list_videos(VIDEO_FOLDER)
    all_media = all_images + all_videos
    
    print(f"📁 Total media in folders: {len(all_media)}")
    
    # Filter to only new media (by name)
    new_media = [m for m in all_media if m['name'] in new_media_names]
    
    print(f"📸 New media found: {[m['name'] for m in new_media]}")
    
    if not new_media:
        print("⚠️ No new media to process")
        return {'processed': 0, 'message': 'No new media to process'}
    
    print(f"📸 Found {len(new_media)} new media to process")
    
    # Load existing gallery
    json_path = os.path.join(GALLERY_FOLDER, 'gallery_data.json')
    existing_persons = []
    existing_media = {}
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                existing_data = json.load(f)
                existing_persons = existing_data.get('persons', [])
                existing_media = {item['name']: item for item in existing_data.get('media', [])}
        except Exception as e:
            print(f"⚠️ Error loading gallery data: {e}")
    
    print(f"📋 Found {len(existing_persons)} existing persons")
    
    # Process new media - extract faces
    all_faces = []
    all_media_info = {}
    
    # Separate images and videos
    new_images = [m for m in new_media if m['name'].lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'))]
    new_videos = [m for m in new_media if m not in new_images]
    
    if new_images:
        image_faces, image_info = process_all_images(new_images, face_app)
        all_faces.extend(image_faces)
        all_media_info.update(image_info)
    
    if new_videos:
        video_faces, video_info = process_all_videos(new_videos, face_app)
        all_faces.extend(video_faces)
        all_media_info.update(video_info)
    
    if not all_faces:
        print("⚠️ No faces detected in new media")
        for name, info in all_media_info.items():
            existing_media[name] = info
        
        gallery_data = {
            'media': list(existing_media.values()),
            'persons': existing_persons,
            'stats': {
                'total_media': len(existing_media),
                'total_faces': sum(p.get('face_count', 0) for p in existing_persons),
                'total_persons': len(existing_persons)
            }
        }
        
        with open(json_path, 'w') as f:
            json.dump(gallery_data, f, indent=2)
        
        return {'processed': len(new_media), 'total_faces': 0, 'new_persons': 0}
    
    print(f"🔍 Found {len(all_faces)} faces to process")
    
    # Get embeddings for existing persons
    person_embeddings = []
    for person in existing_persons:
        emb = get_person_embedding(person, face_app)
        if emb is not None:
            person_embeddings.append((person, emb))
    
    print(f"📋 Got embeddings for {len(person_embeddings)} existing persons")
    
    # Match each face to existing persons
    matched_faces = []
    unmatched_faces = []
    
    for face in all_faces:
        face_emb = face['embedding']
        face_emb_norm = face_emb / np.linalg.norm(face_emb)
        
        best_match = None
        best_similarity = 0
        
        for person, person_emb in person_embeddings:
            person_emb_norm = person_emb / np.linalg.norm(person_emb)
            similarity = np.dot(face_emb_norm, person_emb_norm)
            
            if similarity > SIMILARITY_THRESHOLD and similarity > best_similarity:
                best_similarity = similarity
                best_match = person
        
        if best_match is not None:
            face['matched_person'] = best_match
            face['similarity'] = best_similarity
            matched_faces.append(face)
            print(f"  ✅ Face matched Person #{best_match['id']} (sim: {best_similarity:.3f})")
        else:
            unmatched_faces.append(face)
            print(f"  ⚠️ Face unmatched, will create new person")
    
    # Update existing persons with matched faces
    for face in matched_faces:
        person = face['matched_person']
        media_name = face['media']
        
        if 'media' not in person:
            person['media'] = []
        
        media_exists = False
        for m in person['media']:
            if m.get('name') == media_name:
                media_exists = True
                m['occurrences'] = m.get('occurrences', 0) + 1
                break
        
        if not media_exists:
            person['media'].append({
                'name': media_name,
                'path': all_media_info[media_name]['path'],
                'occurrences': 1,
                'type': all_media_info[media_name].get('type', 'image')
            })
            print(f"  📸 Added media '{media_name}' to Person #{person['id']}")
        
        if 'occurrences' not in person:
            person['occurrences'] = []
        
        occ = {
            'media': face['media'],
            'confidence': face['det_score'],
            'bbox': face['bbox']
        }
        if face.get('source_type') == 'video':
            occ['frame'] = face.get('frame', 0)
            occ['timestamp'] = face.get('timestamp', 0)
        
        person['occurrences'].append(occ)
        person['face_count'] = len(person.get('occurrences', []))
        person['media_count'] = len(person.get('media', []))
    
    # Create new persons for unmatched faces
    new_persons_created = 0
    
    if unmatched_faces:
        print(f"\n🔗 Clustering {len(unmatched_faces)} unmatched faces...")
        eps_value = 1 - SIMILARITY_THRESHOLD
        unmatched_faces = cluster_faces(unmatched_faces, eps=eps_value, min_samples=1)
        
        cluster_groups = defaultdict(list)
        for face in unmatched_faces:
            cluster = face.get('cluster', -1)
            if cluster >= 0:
                cluster_groups[cluster].append(face)
        
        person_id_counter = max([p.get('id', -1) for p in existing_persons]) + 1 if existing_persons else 0
        
        for cluster_id, faces in cluster_groups.items():
            best_face = max(faces, key=lambda x: x.get('det_score', 0))
            
            thumb_name = f"person_{person_id_counter}.jpg"
            thumb_path = os.path.join(THUMBNAIL_FOLDER, thumb_name)
            if best_face['crop'] is not None and best_face['crop'].size > 0:
                crop = best_face['crop']
                if crop.shape[0] > 200 or crop.shape[1] > 200:
                    crop = cv2.resize(crop, (200, 200), interpolation=cv2.INTER_CUBIC)
                cv2.imwrite(thumb_path, crop)
            
            media_occurrences = defaultdict(list)
            for face in faces:
                media_occurrences[face['media']].append({
                    'confidence': face['det_score'],
                    'bbox': face['bbox']
                })
            
            person_data = {
                'id': person_id_counter,
                'thumbnail': thumb_name,
                'face_count': len(faces),
                'media_count': len(media_occurrences),
                'media': [
                    {
                        'name': media,
                        'path': all_media_info[media]['path'],
                        'occurrences': len(occ),
                        'type': all_media_info[media].get('type', 'image')
                    }
                    for media, occ in media_occurrences.items()
                ],
                'occurrences': [
                    {
                        'media': face['media'],
                        'confidence': face['det_score'],
                        'bbox': face['bbox']
                    }
                    for face in faces
                ]
            }
            existing_persons.append(person_data)
            person_id_counter += 1
            new_persons_created += 1
            print(f"  ✅ Created new Person #{person_data['id']} with {len(faces)} faces and {len(media_occurrences)} media")
    
    # Update media info
    for name, info in all_media_info.items():
        existing_media[name] = info
    
    # Final duplicate check
    print(f"\n🔄 Running final duplicate check...")
    existing_persons = merge_duplicate_persons(existing_persons, face_app)
    
    # Build gallery data
    gallery_data = {
        'media': list(existing_media.values()),
        'persons': existing_persons,
        'stats': {
            'total_media': len(existing_media),
            'total_faces': sum(p.get('face_count', 0) for p in existing_persons),
            'total_persons': len(existing_persons)
        }
    }
    
    # Save gallery data
    try:
        with open(json_path, 'w') as f:
            json.dump(gallery_data, f, indent=2)
        print(f"✅ Gallery data saved to {json_path}")
    except Exception as e:
        print(f"❌ Error saving gallery data: {e}")
    
    # Update processed file
    processed_media = {}
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r') as f:
                processed_media = json.load(f)
        except:
            pass
    
    for name, info in all_media_info.items():
        processed_media[name] = {
            'processed_at': time.time(),
            'modified': info['modified'],
            'faces_detected': info.get('faces_detected', 0),
            'type': info.get('type', 'image')
        }
    
    try:
        with open(PROCESSED_FILE, 'w') as f:
            json.dump(processed_media, f, indent=2)
    except Exception as e:
        print(f"❌ Error saving processed file: {e}")
    
    total_faces = sum(p.get('face_count', 0) for p in existing_persons)
    
    print(f"\n✅ Processing complete:")
    print(f"  - Media: {len(all_media_info)}")
    print(f"  - Faces detected: {len(all_faces)}")
    print(f"  - Matched to existing: {len(matched_faces)}")
    print(f"  - New persons: {new_persons_created}")
    print(f"  - Total persons: {len(existing_persons)}")
    print(f"  - Total faces in gallery: {total_faces}")
    
    return {
        'processed': len(all_media_info),
        'total_faces': len(all_faces),
        'new_persons': new_persons_created
    }

# ==================== MAIN ====================

def main():
    if face_app is None:
        print("❌ Face detection is not available.")
        return
    
    args = parse_arguments()
    
    # If media-dir is provided, process only that directory (for uploads)
    if args.media_dir:
        print(f"\n📂 Processing media from: {args.media_dir}")
        all_faces, all_media_info = process_media_from_dir(args.media_dir, face_app)
    else:
        # Process all media from default folders
        print(f"\n📂 Processing all media from: {IMAGE_FOLDER} and {VIDEO_FOLDER}")
        all_faces = []
        all_media_info = {}
        
        images = list_images(IMAGE_FOLDER)
        if images:
            image_faces, image_info = process_all_images(images, face_app)
            all_faces.extend(image_faces)
            all_media_info.update(image_info)
        
        videos = list_videos(VIDEO_FOLDER)
        if videos:
            video_faces, video_info = process_all_videos(videos, face_app)
            all_faces.extend(video_faces)
            all_media_info.update(video_info)
    
    if not all_faces:
        print("\n⚠️ No faces detected in any media.")
        return
    
    # Load existing data
    json_path = os.path.join(GALLERY_FOLDER, 'gallery_data.json')
    existing_persons = []
    existing_media = {}
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                existing_data = json.load(f)
                existing_persons = existing_data.get('persons', [])
                existing_media = {item['name']: item for item in existing_data.get('media', [])}
        except:
            pass
    
    # Update media info
    for name, info in all_media_info.items():
        existing_media[name] = info
    
    # Build gallery with matching
    print(f"\n🔍 Matching {len(all_faces)} faces to existing persons...")
    
    person_embeddings = []
    for person in existing_persons:
        emb = get_person_embedding(person, face_app)
        if emb is not None:
            person_embeddings.append((person, emb))
    
    matched_faces = []
    unmatched_faces = []
    
    for face in all_faces:
        face_emb = face['embedding']
        face_emb_norm = face_emb / np.linalg.norm(face_emb)
        
        best_match = None
        best_similarity = 0
        
        for person, person_emb in person_embeddings:
            person_emb_norm = person_emb / np.linalg.norm(person_emb)
            similarity = np.dot(face_emb_norm, person_emb_norm)
            
            if similarity > SIMILARITY_THRESHOLD and similarity > best_similarity:
                best_similarity = similarity
                best_match = person
        
        if best_match is not None:
            face['matched_person'] = best_match
            face['similarity'] = best_similarity
            matched_faces.append(face)
        else:
            unmatched_faces.append(face)
    
    # Update existing persons
    for face in matched_faces:
        person = face['matched_person']
        media_name = face['media']
        
        if 'media' not in person:
            person['media'] = []
        
        media_exists = False
        for m in person['media']:
            if m.get('name') == media_name:
                media_exists = True
                m['occurrences'] = m.get('occurrences', 0) + 1
                break
        
        if not media_exists:
            person['media'].append({
                'name': media_name,
                'path': all_media_info[media_name]['path'],
                'occurrences': 1,
                'type': all_media_info[media_name].get('type', 'image')
            })
        
        if 'occurrences' not in person:
            person['occurrences'] = []
        person['occurrences'].append({
            'media': face['media'],
            'confidence': face['det_score'],
            'bbox': face['bbox']
        })
        
        person['face_count'] = len(person['occurrences'])
        person['media_count'] = len(person['media'])
    
    # Create new persons for unmatched
    if unmatched_faces:
        print(f"\n🔗 Clustering {len(unmatched_faces)} unmatched faces...")
        unmatched_faces = cluster_faces(unmatched_faces, eps=0.45, min_samples=1)
        
        cluster_groups = defaultdict(list)
        for face in unmatched_faces:
            cluster = face.get('cluster', -1)
            if cluster >= 0:
                cluster_groups[cluster].append(face)
        
        person_id_counter = max([p.get('id', -1) for p in existing_persons]) + 1 if existing_persons else 0
        
        for cluster_id, faces in cluster_groups.items():
            best_face = max(faces, key=lambda x: x.get('det_score', 0))
            
            thumb_name = f"person_{person_id_counter}.jpg"
            thumb_path = os.path.join(THUMBNAIL_FOLDER, thumb_name)
            if best_face['crop'] is not None and best_face['crop'].size > 0:
                crop = best_face['crop']
                if crop.shape[0] > 200 or crop.shape[1] > 200:
                    crop = cv2.resize(crop, (200, 200), interpolation=cv2.INTER_CUBIC)
                cv2.imwrite(thumb_path, crop)
            
            media_occurrences = defaultdict(list)
            for face in faces:
                media_occurrences[face['media']].append({
                    'confidence': face['det_score'],
                    'bbox': face['bbox']
                })
            
            person_data = {
                'id': person_id_counter,
                'thumbnail': thumb_name,
                'face_count': len(faces),
                'media_count': len(media_occurrences),
                'media': [
                    {
                        'name': media,
                        'path': all_media_info[media]['path'],
                        'occurrences': len(occ),
                        'type': all_media_info[media].get('type', 'image')
                    }
                    for media, occ in media_occurrences.items()
                ],
                'occurrences': [
                    {
                        'media': face['media'],
                        'confidence': face['det_score'],
                        'bbox': face['bbox']
                    }
                    for face in faces
                ]
            }
            existing_persons.append(person_data)
            person_id_counter += 1
    
    # Final duplicate check
    existing_persons = merge_duplicate_persons(existing_persons, face_app)
    
    # Build gallery data
    gallery_data = {
        'media': list(existing_media.values()),
        'persons': existing_persons,
        'stats': {
            'total_media': len(existing_media),
            'total_faces': sum(p.get('face_count', 0) for p in existing_persons),
            'total_persons': len(existing_persons)
        }
    }
    
    # Save data
    with open(json_path, 'w') as f:
        json.dump(gallery_data, f, indent=2)
    
    print("\n" + "=" * 60)
    print("✅ GALLERY BUILT SUCCESSFULLY!")
    print("=" * 60)
    print(f"\n📊 Summary:")
    print(f"  - Media: {gallery_data['stats']['total_media']}")
    print(f"  - Faces: {gallery_data['stats']['total_faces']}")
    print(f"  - Persons: {gallery_data['stats']['total_persons']}")

# ==================== EXPORT FOR APP.PY ====================

# This is the function that your app.py calls
process_new_images = process_new_media

if __name__ == '__main__':
    main()