# E:\00000\Rahstaa\My_gallery_2\routes\gallery_routes.py
"""
Gallery Routes - Handle person and media management
"""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
import re

gallery_bp = Blueprint('gallery', __name__, url_prefix='/gallery')

# ============================================================
# PATHS
# ============================================================
BASE_PATH = Path(r'E:\00000\Rahstaa\My_gallery_2')
IMAGES_PATH = BASE_PATH / 'images'
VIDEOS_PATH = BASE_PATH / 'videos'
GALLERY_DATA_PATH = BASE_PATH / 'gallery_data'
THUMBNAILS_PATH = GALLERY_DATA_PATH / 'thumbnails'

# Ensure directories exist
for path in [IMAGES_PATH, VIDEOS_PATH, GALLERY_DATA_PATH, THUMBNAILS_PATH]:
    path.mkdir(parents=True, exist_ok=True)

# Allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_gallery_data():
    """Get gallery data from JSON file"""
    json_path = GALLERY_DATA_PATH / 'gallery_data.json'
    if not json_path.exists():
        return {'persons': [], 'media': [], 'stats': {'total_persons': 0, 'total_media': 0, 'total_faces': 0}}
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'persons': [], 'media': [], 'stats': {'total_persons': 0, 'total_media': 0, 'total_faces': 0}}

def save_gallery_data(data):
    """Save gallery data to JSON file"""
    json_path = GALLERY_DATA_PATH / 'gallery_data.json'
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving gallery data: {e}")
        return False

def get_all_images():
    """Get all images from images folder"""
    images = []
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        images.extend(IMAGES_PATH.glob(f'*{ext}'))
        images.extend(IMAGES_PATH.glob(f'*{ext.upper()}'))
    return sorted(set(images), key=lambda x: x.name)

def get_all_videos():
    """Get all videos from videos folder"""
    videos = []
    for ext in ALLOWED_VIDEO_EXTENSIONS:
        videos.extend(VIDEOS_PATH.glob(f'*{ext}'))
        videos.extend(VIDEOS_PATH.glob(f'*{ext.upper()}'))
    return sorted(set(videos), key=lambda x: x.name)

def get_person_media(person_id):
    """Get all media for a specific person"""
    gallery_data = get_gallery_data()
    person = next((p for p in gallery_data.get('persons', []) if p.get('id') == person_id), None)
    if not person:
        return {'images': [], 'videos': []}
    
    media_list = person.get('media', [])
    images = [m for m in media_list if m.get('type') == 'image']
    videos = [m for m in media_list if m.get('type') == 'video']
    
    return {'images': images, 'videos': videos}

def find_person_by_id(person_id):
    """Find a person by ID"""
    gallery_data = get_gallery_data()
    return next((p for p in gallery_data.get('persons', []) if p.get('id') == person_id), None)

# ============================================================
# ROUTES
# ============================================================

@gallery_bp.route('/')
def gallery_index():
    """Gallery main page"""
    gallery_data = get_gallery_data()
    return render_template('gallery.html', 
                         gallery_data=gallery_data,
                         active_page='gallery')

@gallery_bp.route('/people')
def people():
    """People gallery page"""
    gallery_data = get_gallery_data()
    return render_template('people.html', 
                         gallery_data=gallery_data,
                         active_page='people')

@gallery_bp.route('/person/<int:person_id>')
def person_detail(person_id):
    """Person detail view with media selection"""
    person = find_person_by_id(person_id)
    
    if not person:
        flash('Person not found', 'error')
        return redirect(url_for('people_page'))
    
    # Get templates for video generation
    from app import get_templates
    templates = get_templates()
    
    return render_template('person_detail.html',
                         person=person,
                         templates=templates,
                         active_page='people')

@gallery_bp.route('/upload')
def upload_page():
    """Upload page"""
    return render_template('upload.html', active_page='upload')

# ============================================================
# API ENDPOINTS
# ============================================================

@gallery_bp.route('/api/gallery')
def api_gallery():
    """Get complete gallery data"""
    return jsonify(get_gallery_data())

@gallery_bp.route('/api/persons')
def api_persons():
    """Get persons data only"""
    gallery_data = get_gallery_data()
    return jsonify(gallery_data.get('persons', []))

@gallery_bp.route('/api/person/<int:person_id>')
def api_person(person_id):
    """Get specific person data"""
    person = find_person_by_id(person_id)
    if not person:
        return jsonify({'error': 'Person not found'}), 404
    return jsonify(person)

@gallery_bp.route('/api/person/<int:person_id>/media')
def api_person_media(person_id):
    """Get media for a specific person"""
    return jsonify(get_person_media(person_id))

@gallery_bp.route('/api/images')
def api_images():
    """Get all images data"""
    images = get_all_images()
    return jsonify([{'name': img.name, 'path': str(img)} for img in images])

@gallery_bp.route('/api/videos')
def api_videos():
    """Get all videos data"""
    videos = get_all_videos()
    return jsonify([{'name': vid.name, 'path': str(vid)} for vid in videos])

@gallery_bp.route('/api/media/search')
def search_media():
    """Search media by name"""
    query = request.args.get('q', '').lower().strip()
    if not query:
        return jsonify({'images': [], 'videos': []})
    
    images = [{'name': img.name, 'path': str(img)} for img in get_all_images() if query in img.name.lower()]
    videos = [{'name': vid.name, 'path': str(vid)} for vid in get_all_videos() if query in vid.name.lower()]
    
    return jsonify({'images': images, 'videos': videos})

# ============================================================
# UPLOAD ENDPOINTS
# ============================================================

@gallery_bp.route('/upload/images', methods=['POST'])
def upload_images():
    """Upload images to the images folder"""
    if 'images' not in request.files:
        return jsonify({'error': 'No images provided'}), 400
    
    files = request.files.getlist('images')
    uploaded = []
    errors = []
    
    for file in files:
        if file.filename:
            filename = secure_filename(file.filename)
            file_path = IMAGES_PATH / filename
            
            # Handle duplicate filenames
            counter = 1
            while file_path.exists():
                name, ext = os.path.splitext(filename)
                new_name = f"{name}_{counter}{ext}"
                file_path = IMAGES_PATH / new_name
                counter += 1
            
            try:
                file.save(file_path)
                uploaded.append(file_path.name)
            except Exception as e:
                errors.append(f'{filename}: {str(e)}')
    
    # Trigger gallery rebuild
    if uploaded:
        try:
            from build_gallery import process_new_images
            process_new_images(uploaded)
        except Exception as e:
            print(f"Error processing images: {e}")
    
    return jsonify({
        'success': True,
        'uploaded': uploaded,
        'errors': errors
    })

@gallery_bp.route('/upload/videos', methods=['POST'])
def upload_videos():
    """Upload videos to the videos folder"""
    if 'videos' not in request.files:
        return jsonify({'error': 'No videos provided'}), 400
    
    files = request.files.getlist('videos')
    uploaded = []
    errors = []
    
    for file in files:
        if file.filename:
            filename = secure_filename(file.filename)
            file_path = VIDEOS_PATH / filename
            
            # Handle duplicate filenames
            counter = 1
            while file_path.exists():
                name, ext = os.path.splitext(filename)
                new_name = f"{name}_{counter}{ext}"
                file_path = VIDEOS_PATH / new_name
                counter += 1
            
            try:
                file.save(file_path)
                uploaded.append(file_path.name)
            except Exception as e:
                errors.append(f'{filename}: {str(e)}')
    
    # Trigger gallery rebuild
    if uploaded:
        try:
            from build_gallery import process_new_videos
            process_new_videos(uploaded)
        except Exception as e:
            print(f"Error processing videos: {e}")
    
    return jsonify({
        'success': True,
        'uploaded': uploaded,
        'errors': errors
    })

@gallery_bp.route('/upload/zip', methods=['POST'])
def upload_zip():
    """Upload and extract zip file containing images and videos"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.zip'):
        return jsonify({'error': 'Please upload a zip file'}), 400
    
    import zipfile
    import tempfile
    
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, secure_filename(file.filename))
    file.save(zip_path)
    
    extracted_images = []
    extracted_videos = []
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Walk through extracted files
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                src_path = os.path.join(root, f)
                ext = os.path.splitext(f)[1].lower()
                
                if ext in ALLOWED_IMAGE_EXTENSIONS:
                    # Copy to images folder
                    dst_path = IMAGES_PATH / f
                    counter = 1
                    while dst_path.exists():
                        name, ext2 = os.path.splitext(f)
                        new_name = f"{name}_{counter}{ext2}"
                        dst_path = IMAGES_PATH / new_name
                        counter += 1
                    shutil.copy2(src_path, dst_path)
                    extracted_images.append(dst_path.name)
                    
                elif ext in ALLOWED_VIDEO_EXTENSIONS:
                    # Copy to videos folder
                    dst_path = VIDEOS_PATH / f
                    counter = 1
                    while dst_path.exists():
                        name, ext2 = os.path.splitext(f)
                        new_name = f"{name}_{counter}{ext2}"
                        dst_path = VIDEOS_PATH / new_name
                        counter += 1
                    shutil.copy2(src_path, dst_path)
                    extracted_videos.append(dst_path.name)
        
        # Trigger gallery rebuild
        if extracted_images or extracted_videos:
            try:
                from build_gallery import process_new_images, process_new_videos
                if extracted_images:
                    process_new_images(extracted_images)
                if extracted_videos:
                    process_new_videos(extracted_videos)
            except Exception as e:
                print(f"Error processing files: {e}")
        
        return jsonify({
            'success': True,
            'extracted_images': extracted_images,
            'extracted_videos': extracted_videos,
            'total': len(extracted_images) + len(extracted_videos)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error extracting zip: {str(e)}'}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ============================================================
# STATIC FILE SERVING
# ============================================================

@gallery_bp.route('/images/<path:filename>')
def serve_image(filename):
    """Serve image files from images folder"""
    file_path = IMAGES_PATH / filename
    if not file_path.exists():
        return jsonify({'error': 'Image not found'}), 404
    return send_file(file_path)

@gallery_bp.route('/videos/<path:filename>')
def serve_video(filename):
    """Serve video files from videos folder"""
    file_path = VIDEOS_PATH / filename
    if not file_path.exists():
        return jsonify({'error': 'Video not found'}), 404
    return send_file(file_path)

@gallery_bp.route('/gallery_data/<path:filename>')
def serve_gallery_data(filename):
    """Serve gallery data files"""
    file_path = GALLERY_DATA_PATH / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path)

@gallery_bp.route('/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    """Serve thumbnail images"""
    file_path = THUMBNAILS_PATH / filename
    if not file_path.exists():
        # Return default thumbnail
        default_path = THUMBNAILS_PATH / 'default.jpg'
        if default_path.exists():
            return send_file(default_path)
        return jsonify({'error': 'Thumbnail not found'}), 404
    return send_file(file_path)