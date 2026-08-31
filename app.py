# E:\00000\Rahstaa\My_gallery_2\app.py
# Complete updated app.py with Blueprint registration and Upload endpoint

import os
import json
import shutil
import subprocess
import sys
import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
import io

# Import Blueprints
from routes.template_routes import template_bp
from routes.video_routes import video_bp

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

# ============================================================
# PATHS
# ============================================================
BASE_PATH = Path(r'E:\00000\Rahstaa\My_gallery_2')
IMAGES_PATH = BASE_PATH / 'images'
VIDEOS_PATH = BASE_PATH / 'videos'
ASSETS_PATH = BASE_PATH / 'assets'
OUTPUT_PATH = BASE_PATH / 'output'
GALLERY_DATA_PATH = BASE_PATH / 'gallery_data'
THUMBNAILS_PATH = GALLERY_DATA_PATH / 'thumbnails'
PREVIEWS_PATH = GALLERY_DATA_PATH / 'video_previews'

# Ensure directories exist
for path in [IMAGES_PATH, VIDEOS_PATH, ASSETS_PATH, OUTPUT_PATH, GALLERY_DATA_PATH, THUMBNAILS_PATH, PREVIEWS_PATH]:
    path.mkdir(parents=True, exist_ok=True)

# Allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac'}

# Register Blueprints
app.register_blueprint(template_bp, url_prefix='/template')
app.register_blueprint(video_bp, url_prefix='/video')

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
    except Exception as e:
        print(f"Error loading gallery data: {e}")
        return {'persons': [], 'media': [], 'stats': {'total_persons': 0, 'total_media': 0, 'total_faces': 0}}

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

def get_templates():
    """Get all template folders in assets"""
    templates = []
    if ASSETS_PATH.exists():
        for folder in ASSETS_PATH.iterdir():
            if folder.is_dir():
                template_data = {
                    'name': folder.name,
                    'path': str(folder),
                    'has_starting': any(f.name.startswith('starting') for f in folder.iterdir() if f.is_file()),
                    'has_ending': any(f.name.startswith('ending') for f in folder.iterdir() if f.is_file()),
                    'has_music': any(f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS for f in folder.iterdir() if f.is_file()),
                    'has_captions': (folder / 'Captions.txt').exists(),
                    'created': datetime.fromtimestamp(folder.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                }
                templates.append(template_data)
    return sorted(templates, key=lambda x: x['created'], reverse=True)

def run_gallery_builder(media_files):
    """Run the gallery builder script with new media files"""
    try:
        # Get the Python executable
        python_exe = sys.executable
        build_script = BASE_PATH / 'build_gallery.py'
        
        if not build_script.exists():
            return {'success': False, 'error': 'build_gallery.py not found'}
        
        # Create temp directory for media
        temp_dir = Path(tempfile.mkdtemp())
        
        # Copy media files to temp
        copied_files = []
        for file_data in media_files:
            if isinstance(file_data, dict):
                # Handle dict with path and name
                src = file_data.get('path')
                if src and Path(src).exists():
                    dst = temp_dir / Path(src).name
                    shutil.copy2(src, dst)
                    copied_files.append(dst.name)
            elif isinstance(file_data, (str, Path)):
                src = Path(file_data)
                if src.exists():
                    dst = temp_dir / src.name
                    shutil.copy2(src, dst)
                    copied_files.append(dst.name)
        
        if not copied_files:
            shutil.rmtree(temp_dir)
            return {'success': False, 'error': 'No valid media files to process'}
        
        # Run the build script
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['GALLERY_BASE_PATH'] = str(BASE_PATH)
        
        result = subprocess.run(
            [python_exe, str(build_script), '--media-dir', str(temp_dir)],
            capture_output=True,
            text=True,
            timeout=600,  # Increased timeout for large files
            env=env,
            cwd=str(BASE_PATH),
            encoding='utf-8',
            errors='replace'
        )
        
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            return {'success': False, 'error': error_msg[:500]}
        
        return {'success': True, 'output': result.stdout}
        
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Gallery build timed out'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def process_uploaded_files(media_files):
    """
    Process uploaded files directly using the gallery builder's process_new_media function.
    This is faster than running subprocess for each upload.
    """
    try:
        # Import the process_new_media function from build_gallery
        # Try different import approaches
        try:
            from build_gallery import process_new_media
            print("✅ Imported process_new_media from build_gallery")
        except ImportError:
            try:
                from build_gallery import process_new_images as process_new_media
                print("✅ Imported process_new_images as process_new_media")
            except ImportError:
                # Fallback: run as subprocess
                print("⚠️ Could not import, falling back to subprocess")
                return run_gallery_builder(media_files)
        
        # Get the names of the uploaded files
        file_names = []
        for file_data in media_files:
            if isinstance(file_data, dict):
                name = file_data.get('name')
                if name:
                    file_names.append(name)
            elif isinstance(file_data, (str, Path)):
                file_names.append(Path(file_data).name)
        
        if not file_names:
            return {'success': False, 'error': 'No valid media files to process'}
        
        print(f"📸 Processing {len(file_names)} files: {file_names}")
        
        # Call the process_new_media function
        result = process_new_media(file_names)
        
        if result:
            # Get updated gallery data for complete stats
            gallery_data = get_gallery_data()
            
            return {
                'success': True,
                'output': f"Processed {result.get('processed', 0)} files, {result.get('new_persons', 0)} new persons",
                'result': {
                    'processed': result.get('processed', 0),
                    'total_faces': result.get('total_faces', 0),
                    'new_persons': result.get('new_persons', 0),
                    'matched_faces': result.get('matched_faces', 0),
                    'gallery_stats': gallery_data.get('stats', {})
                }
            }
        else:
            return {'success': False, 'error': 'Processing returned no result'}
        
    except Exception as e:
        print(f"❌ Error in process_uploaded_files: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to subprocess
        return run_gallery_builder(media_files)

# ============================================================
# MAIN ROUTES
# ============================================================

@app.route('/')
def index():
    """Dashboard page"""
    gallery_data = get_gallery_data()
    templates = get_templates()
    images = get_all_images()
    videos = get_all_videos()
    
    return render_template('home.html',
                         gallery_data=gallery_data,
                         templates=templates,
                         total_images=len(images),
                         total_videos=len(videos),
                         total_templates=len(templates),
                         active_page='home')

@app.route('/people')
def people_page():
    """People gallery page"""
    gallery_data = get_gallery_data()
    return render_template('people.html', 
                         gallery_data=gallery_data,
                         active_page='people')

@app.route('/person/<int:person_id>')
def person_detail(person_id):
    """Person detail view with media selection"""
    gallery_data = get_gallery_data()
    person = next((p for p in gallery_data.get('persons', []) if p.get('id') == person_id), None)
    
    if not person:
        flash('Person not found', 'error')
        return redirect(url_for('people_page'))
    
    templates = get_templates()
    
    return render_template('person_detail.html',
                         person=person,
                         templates=templates,
                         active_page='people')

@app.route('/templates')
def templates_page():
    """Templates management page"""
    templates = get_templates()
    return render_template('templates.html', 
                         templates=templates,
                         active_page='templates')

@app.route('/upload')
def upload_page():
    """Upload page"""
    return render_template('upload.html', active_page='upload')

# ============================================================
# API ENDPOINTS
# ============================================================

@app.route('/api/gallery')
def api_gallery():
    """Get complete gallery data"""
    return jsonify(get_gallery_data())

@app.route('/api/templates')
def api_templates():
    """Get all templates"""
    templates = get_templates()
    return jsonify({'templates': templates})

@app.route('/api/person/<int:person_id>/media')
def api_person_media(person_id):
    """Get media for a specific person"""
    gallery_data = get_gallery_data()
    person = next((p for p in gallery_data.get('persons', []) if p.get('id') == person_id), None)
    if not person:
        return jsonify({'images': [], 'videos': []})
    
    media_list = person.get('media', [])
    images = [m.get('name') for m in media_list if m.get('type') == 'image']
    videos = [m.get('name') for m in media_list if m.get('type') == 'video']
    
    return jsonify({'images': images, 'videos': videos})

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Upload files and process them"""
    try:
        print("\n" + "="*60)
        print("📤 UPLOAD REQUEST RECEIVED")
        print("="*60)
        
        if 'files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files selected'}), 400
        
        print(f"📁 Received {len(files)} files")
        
        uploaded_images = []
        uploaded_videos = []
        processed_files = []
        
        for file in files:
            if file.filename == '':
                continue
            
            filename = secure_filename(file.filename)
            file_ext = Path(filename).suffix.lower()
            
            # Handle zip files
            if file_ext == '.zip':
                print(f"📦 Processing zip: {filename}")
                try:
                    zip_data = file.read()
                    with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zip_ref:
                        for zip_info in zip_ref.namelist():
                            zip_filename = Path(zip_info).name
                            zip_ext = Path(zip_filename).suffix.lower()
                            
                            # Extract only images and videos
                            if zip_ext in ALLOWED_IMAGE_EXTENSIONS:
                                zip_data_content = zip_ref.read(zip_info)
                                save_path = IMAGES_PATH / zip_filename
                                # Handle duplicate filenames
                                counter = 1
                                while save_path.exists():
                                    name, ext = os.path.splitext(zip_filename)
                                    new_name = f"{name}_{counter}{ext}"
                                    save_path = IMAGES_PATH / new_name
                                    counter += 1
                                with open(save_path, 'wb') as f:
                                    f.write(zip_data_content)
                                uploaded_images.append({'path': save_path, 'name': save_path.name})
                                processed_files.append({'name': save_path.name, 'type': 'image'})
                                print(f"   ✅ Extracted image: {save_path.name}")
                            
                            elif zip_ext in ALLOWED_VIDEO_EXTENSIONS:
                                zip_data_content = zip_ref.read(zip_info)
                                save_path = VIDEOS_PATH / zip_filename
                                counter = 1
                                while save_path.exists():
                                    name, ext = os.path.splitext(zip_filename)
                                    new_name = f"{name}_{counter}{ext}"
                                    save_path = VIDEOS_PATH / new_name
                                    counter += 1
                                with open(save_path, 'wb') as f:
                                    f.write(zip_data_content)
                                uploaded_videos.append({'path': save_path, 'name': save_path.name})
                                processed_files.append({'name': save_path.name, 'type': 'video'})
                                print(f"   ✅ Extracted video: {save_path.name}")
                except Exception as e:
                    print(f"❌ Error processing zip: {e}")
                    return jsonify({'error': f'Error processing zip file: {str(e)}'}), 400
            
            # Handle image files
            elif file_ext in ALLOWED_IMAGE_EXTENSIONS:
                save_path = IMAGES_PATH / filename
                counter = 1
                while save_path.exists():
                    name, ext = os.path.splitext(filename)
                    new_name = f"{name}_{counter}{ext}"
                    save_path = IMAGES_PATH / new_name
                    counter += 1
                file.save(save_path)
                uploaded_images.append({'path': save_path, 'name': save_path.name})
                processed_files.append({'name': save_path.name, 'type': 'image'})
                print(f"   ✅ Saved image: {save_path.name}")
            
            # Handle video files
            elif file_ext in ALLOWED_VIDEO_EXTENSIONS:
                save_path = VIDEOS_PATH / filename
                counter = 1
                while save_path.exists():
                    name, ext = os.path.splitext(filename)
                    new_name = f"{name}_{counter}{ext}"
                    save_path = VIDEOS_PATH / new_name
                    counter += 1
                file.save(save_path)
                uploaded_videos.append({'path': save_path, 'name': save_path.name})
                processed_files.append({'name': save_path.name, 'type': 'video'})
                print(f"   ✅ Saved video: {save_path.name}")
            
            else:
                print(f"   ⚠️ Skipped unsupported file: {filename}")
        
        if not processed_files:
            return jsonify({'error': 'No valid files found to process'}), 400
        
        print(f"\n📊 Upload summary:")
        print(f"   Images: {len(uploaded_images)}")
        print(f"   Videos: {len(uploaded_videos)}")
        
        # Process the uploaded files with the gallery builder
        all_media = uploaded_images + uploaded_videos
        
        print(f"\n🔄 Processing {len(all_media)} files with gallery builder...")
        
        # Try direct import first (faster), fallback to subprocess
        result = process_uploaded_files(all_media)
        
        if result.get('success'):
            print("✅ Gallery builder completed successfully")
            
            # Get updated gallery data
            gallery_data = get_gallery_data()
            
            # Get result details
            result_data = result.get('result', {})
            gallery_stats = result_data.get('gallery_stats', {})
            
            # Build complete stats for UI
            stats = {
                'processed_images': len(uploaded_images),
                'videos_uploaded': len(uploaded_videos),
                'faces_detected': result_data.get('total_faces', 0),
                'new_persons_created': result_data.get('new_persons', 0),
                'matched_faces': result_data.get('matched_faces', 0),
                'total_persons': gallery_stats.get('total_persons', gallery_data.get('stats', {}).get('total_persons', 0)),
                'total_faces': gallery_stats.get('total_faces', gallery_data.get('stats', {}).get('total_faces', 0)),
                'total_media': gallery_stats.get('total_media', gallery_data.get('stats', {}).get('total_media', 0)),
                'processed': result_data.get('processed', 0)
            }
            
            return jsonify({
                'success': True,
                'message': 'Files uploaded and processed successfully',
                'processed': len(processed_files),
                'result': stats
            })
        else:
            error_msg = result.get('error', 'Unknown error')
            print(f"❌ Gallery builder failed: {error_msg}")
            return jsonify({'error': f'Gallery builder failed: {error_msg}'}), 500
        
    except Exception as e:
        print(f"❌ Upload error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ============================================================
# STATIC FILE SERVING
# ============================================================

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve image files"""
    file_path = IMAGES_PATH / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path)

@app.route('/videos/<path:filename>')
def serve_video(filename):
    """Serve video files"""
    file_path = VIDEOS_PATH / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path)

@app.route('/gallery_data/<path:filename>')
def serve_gallery_data(filename):
    """Serve gallery data files"""
    file_path = GALLERY_DATA_PATH / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path)

@app.route('/gallery_data/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    """Serve thumbnails"""
    file_path = THUMBNAILS_PATH / filename
    if not file_path.exists():
        # Return default thumbnail if exists
        default_path = THUMBNAILS_PATH / 'default.jpg'
        if default_path.exists():
            return send_file(default_path)
        return jsonify({'error': 'Not found'}), 404
    return send_file(file_path)

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🎬 FACE GALLERY & VIDEO GENERATOR")
    print("="*60)
    print("  🏠 Home:     http://localhost:5000/")
    print("  👤 People:   http://localhost:5000/people")
    print("  📁 Template: http://localhost:5000/templates")
    print("  📤 Upload:   http://localhost:5000/upload")
    print("  📝 Create:   http://localhost:5000/template/create")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)