# E:\00000\Rahstaa\My_gallery_2\routes\video_routes.py
"""
Video Routes - Handle video generation and processing
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, flash, redirect, url_for, current_app
from werkzeug.utils import secure_filename
import zipfile
import io

video_bp = Blueprint('video', __name__, url_prefix='/video')

# ============================================================
# PATHS - Dynamic path resolution for deployment
# ============================================================

def get_base_path():
    """Get the base path dynamically - works in development and production"""
    env_path = os.environ.get('GALLERY_BASE_PATH')
    if env_path:
        return Path(env_path)
    
    try:
        from flask import current_app
        if hasattr(current_app, 'config') and 'BASE_PATH' in current_app.config:
            return Path(current_app.config['BASE_PATH'])
    except:
        pass
    
    current_file = Path(__file__).resolve()
    base = current_file.parent.parent
    
    if (base / 'assets').exists() and (base / 'images').exists():
        return base
    
    return Path(r'E:\00000\Rahstaa\My_gallery_2')

BASE_PATH = get_base_path()
IMAGES_PATH = BASE_PATH / 'images'
VIDEOS_PATH = BASE_PATH / 'videos'
ASSETS_PATH = BASE_PATH / 'assets'
OUTPUT_PATH = BASE_PATH / 'output'
GALLERY_DATA_PATH = BASE_PATH / 'gallery_data'

# Ensure output directory exists
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac'}

print(f"[INIT] Base Path: {BASE_PATH}")
print(f"[INIT] Output Path: {OUTPUT_PATH}")

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_gallery_data():
    json_path = GALLERY_DATA_PATH / 'gallery_data.json'
    if not json_path.exists():
        return {'persons': [], 'media': [], 'stats': {'total_persons': 0, 'total_media': 0, 'total_faces': 0}}
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading gallery data: {e}")
        return {'persons': [], 'media': [], 'stats': {'total_persons': 0, 'total_media': 0, 'total_faces': 0}}

def get_person_media(person_id):
    gallery_data = get_gallery_data()
    person = next((p for p in gallery_data.get('persons', []) if p.get('id') == person_id), None)
    if not person:
        return {'images': [], 'videos': []}
    
    media_list = person.get('media', [])
    images = [m.get('name') for m in media_list if m.get('type') == 'image']
    videos = [m.get('name') for m in media_list if m.get('type') == 'video']
    
    return {'images': images, 'videos': videos}

def get_template_assets(template_name):
    template_path = ASSETS_PATH / template_name
    if not template_path.exists():
        return None
    
    assets = {
        'starting': None,
        'ending': None,
        'music': None,
        'captions': None,
        'extra_images': [],
        'extra_videos': []
    }
    
    for f in template_path.iterdir():
        if f.is_file():
            if f.name.startswith('starting'):
                assets['starting'] = f
            elif f.name.startswith('ending'):
                assets['ending'] = f
            elif f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS:
                assets['music'] = f
            elif f.name == 'Captions.txt':
                assets['captions'] = f
    
    extra_images_path = template_path / 'extra_images'
    if extra_images_path.exists():
        assets['extra_images'] = [f for f in extra_images_path.iterdir() if f.is_file()]
    
    extra_videos_path = template_path / 'extra_videos'
    if extra_videos_path.exists():
        assets['extra_videos'] = [f for f in extra_videos_path.iterdir() if f.is_file()]
    
    return assets

def check_dependencies():
    missing = []
    try:
        import moviepy
    except ImportError:
        missing.append('moviepy')
    try:
        import PIL
    except ImportError:
        missing.append('Pillow')
    try:
        import numpy
    except ImportError:
        missing.append('numpy')
    try:
        import cv2
    except ImportError:
        missing.append('opencv-python')
    return missing

def get_python_executable():
    python_exe = sys.executable
    if 'venv' in python_exe or 'virtualenv' in python_exe:
        return python_exe
    
    try:
        import shutil
        python_path = shutil.which('python')
        if python_path:
            return python_path
    except:
        pass
    
    return python_exe

# ============================================================
# ROUTES
# ============================================================

@video_bp.route('/generate', methods=['POST'])
def generate_video():
    """Generate video for a person using template - saves directly to output folder"""
    try:
        print("\n" + "="*60)
        print("GENERATE VIDEO REQUEST RECEIVED")
        print("="*60)
        
        missing_deps = check_dependencies()
        if missing_deps:
            error_msg = f"Missing dependencies: {', '.join(missing_deps)}. Please install: pip install {' '.join(missing_deps)}"
            print(f"[ERROR] {error_msg}")
            return jsonify({'error': error_msg}), 500
        
        data = request.get_json()
        if not data:
            print("[ERROR] No JSON data received")
            return jsonify({'error': 'No JSON data received'}), 400
        
        print(f"[REQUEST] Data: {json.dumps(data, indent=2)}")
        
        person_id = data.get('person_id')
        template_name = data.get('template_name')
        image_names = data.get('images', [])
        video_names = data.get('videos', [])
        
        print(f"[PERSON ID] {person_id} (type: {type(person_id)})")
        print(f"[TEMPLATE] {template_name}")
        print(f"[IMAGES] {len(image_names)}")
        print(f"[VIDEOS] {len(video_names)}")
        
        if person_id is None:
            print("[ERROR] Person ID is None")
            return jsonify({'error': 'Person ID required'}), 400
        
        try:
            person_id = int(person_id)
        except (ValueError, TypeError):
            print(f"[ERROR] Invalid person_id: {person_id}")
            return jsonify({'error': 'Invalid person ID'}), 400
        
        if not template_name:
            print("[ERROR] Template name required")
            return jsonify({'error': 'Template name required'}), 400
        
        if not image_names and not video_names:
            print("[ERROR] No media selected")
            return jsonify({'error': 'No media selected'}), 400
        
        print(f"[OK] Valid person_id: {person_id}")
        
        template_path = ASSETS_PATH / template_name
        if not template_path.exists():
            print(f"[ERROR] Template not found: {template_path}")
            return jsonify({'error': f'Template "{template_name}" not found'}), 404
        
        print(f"[OK] Template found: {template_path}")
        
        template_assets = get_template_assets(template_name)
        if not template_assets:
            print("[ERROR] Template assets not found")
            return jsonify({'error': 'Template assets not found'}), 404
        
        print("[OK] Template assets loaded")
        
        # Create temp directory for processing (only for copying assets)
        temp_dir = Path(tempfile.mkdtemp())
        print(f"[TEMP] Temp directory for assets: {temp_dir}")
        
        try:
            # Copy person's media to temp
            person_media_path = temp_dir / f'person_{person_id}'
            person_media_path.mkdir(exist_ok=True)
            
            copied_images = []
            for img_name in image_names:
                src = IMAGES_PATH / img_name
                if src.exists():
                    dst = person_media_path / img_name
                    shutil.copy2(src, dst)
                    copied_images.append(img_name)
                    print(f"   [COPY] Image: {img_name}")
            
            copied_videos = []
            for vid_name in video_names:
                src = VIDEOS_PATH / vid_name
                if src.exists():
                    dst = person_media_path / vid_name
                    shutil.copy2(src, dst)
                    copied_videos.append(vid_name)
                    print(f"   [COPY] Video: {vid_name}")
            
            if not copied_images and not copied_videos:
                shutil.rmtree(temp_dir)
                print("[ERROR] No valid media files found")
                return jsonify({'error': 'No valid media files found'}), 400
            
            # Copy template assets to temp
            template_temp_path = temp_dir / 'template'
            template_temp_path.mkdir(exist_ok=True)
            
            if template_assets['starting']:
                shutil.copy2(template_assets['starting'], template_temp_path / template_assets['starting'].name)
                print(f"   [COPY] Starting asset: {template_assets['starting'].name}")
            
            if template_assets['ending']:
                shutil.copy2(template_assets['ending'], template_temp_path / template_assets['ending'].name)
                print(f"   [COPY] Ending asset: {template_assets['ending'].name}")
            
            if template_assets['music']:
                shutil.copy2(template_assets['music'], template_temp_path / template_assets['music'].name)
                print(f"   [COPY] Music: {template_assets['music'].name}")
            
            if template_assets['captions']:
                shutil.copy2(template_assets['captions'], template_temp_path / 'Captions.txt')
                print(f"   [COPY] Captions: Captions.txt")
            
            # Copy extra assets
            extra_images_path = template_temp_path / 'extra_images'
            extra_images_path.mkdir(exist_ok=True)
            for img in template_assets.get('extra_images', []):
                shutil.copy2(img, extra_images_path / img.name)
                print(f"   [COPY] Extra image: {img.name}")
            
            extra_videos_path = template_temp_path / 'extra_videos'
            extra_videos_path.mkdir(exist_ok=True)
            for vid in template_assets.get('extra_videos', []):
                shutil.copy2(vid, extra_videos_path / vid.name)
                print(f"   [COPY] Extra video: {vid.name}")
            
            # Copy person's media to template
            for img in copied_images:
                shutil.copy2(person_media_path / img, extra_images_path / img)
                print(f"   [COPY] Person image to template: {img}")
            
            for vid in copied_videos:
                shutil.copy2(person_media_path / vid, extra_videos_path / vid)
                print(f"   [COPY] Person video to template: {vid}")
            
            short_film_path = BASE_PATH / 'short_film.py'
            if not short_film_path.exists():
                print(f"[ERROR] short_film.py not found at: {short_film_path}")
                return jsonify({'error': 'Video generator script not found'}), 500
            
            python_exe = get_python_executable()
            print(f"[PYTHON] Using Python: {python_exe}")
            
            # Generate output filename - SAVE DIRECTLY TO OUTPUT FOLDER
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"Person_{person_id}_{template_name}_{timestamp}.mp4"
            
            # Create person-specific output folder
            person_output_path = OUTPUT_PATH / f"person_{person_id}"
            person_output_path.mkdir(parents=True, exist_ok=True)
            
            # FINAL OUTPUT PATH - Save directly here!
            final_output_path = person_output_path / output_filename
            print(f"[OUTPUT] Saving directly to: {final_output_path}")
            
            # Build command - WRITE DIRECTLY TO OUTPUT FOLDER
            cmd = [
                python_exe,
                str(short_film_path),
                '--template', template_name,
                '--person-id', str(person_id),
                '--output', str(final_output_path),  # DIRECTLY to output folder!
                '--resolution', '1280x720',
                '--images-list', ','.join(image_names),
                '--videos-list', ','.join(video_names),
                '--max-duration', '9999'  # No limit
            ]
            
            print(f"\n[RUN] Command: {' '.join(cmd)}")
            print(f"[OUTPUT] Video will be saved to: {final_output_path}")
            
            env = os.environ.copy()
            env['TEMPLATE_PATH'] = str(template_temp_path)
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONUTF8'] = '1'
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=600,
                env=env,
                cwd=str(BASE_PATH),
                encoding='utf-8',
                errors='replace'
            )
            
            print(f"\n[OUTPUT] Command output:")
            if result.stdout:
                print(f"   STDOUT: {result.stdout}")
            if result.stderr:
                print(f"   STDERR: {result.stderr}")
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                print(f"[ERROR] Video generation failed: {error_msg[:200]}")
                raise Exception(f"Video generation failed: {error_msg[:200]}")
            
            print("[OK] Video generation command completed")
            
            # Check if video was generated at the final output path
            if final_output_path.exists() and final_output_path.stat().st_size > 0:
                print(f"[OK] Video successfully saved to: {final_output_path}")
                
                # Get file size
                file_size_mb = final_output_path.stat().st_size / (1024 * 1024)
                print(f"[INFO] File size: {file_size_mb:.2f} MB")
                
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                print(f"[CLEANUP] Cleaned up temp directory: {temp_dir}")
                
                # Read the video file for download
                with open(final_output_path, 'rb') as f:
                    video_data = f.read()
                
                # Delete the file after reading (auto-cleanup after download)
                try:
                    final_output_path.unlink()
                    print(f"[CLEANUP] Deleted video after serving: {final_output_path}")
                except Exception as e:
                    print(f"[WARNING] Could not delete video: {e}")
                
                # Try to delete the person folder if empty
                try:
                    if person_output_path.exists() and not any(person_output_path.iterdir()):
                        person_output_path.rmdir()
                        print(f"[CLEANUP] Deleted empty folder: {person_output_path}")
                except Exception as e:
                    pass
                
                # Return video file for download
                return send_file(
                    io.BytesIO(video_data),
                    mimetype='video/mp4',
                    as_attachment=True,
                    download_name=output_filename
                )
            else:
                print(f"[ERROR] Video file not found at: {final_output_path}")
                return jsonify({'error': 'Video generation completed but file not found'}), 500
            
        except subprocess.TimeoutExpired:
            print("[ERROR] Video generation timed out")
            return jsonify({'error': 'Video generation timed out'}), 500
        except Exception as e:
            print(f"[ERROR] Error during video generation: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
        finally:
            # Cleanup if temp_dir still exists
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                print(f"[CLEANUP] Cleaned up temp directory: {temp_dir}")
            
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@video_bp.route('/merge', methods=['POST'])
def merge_files():
    """Merge selected files into a zip archive"""
    try:
        data = request.get_json()
        person_id = data.get('person_id')
        image_names = data.get('images', [])
        video_names = data.get('videos', [])
        
        print(f"\n[MERGE] Request - Person: {person_id}")
        print(f"   Images: {len(image_names)}")
        print(f"   Videos: {len(video_names)}")
        
        if not image_names and not video_names:
            return jsonify({'error': 'No files selected'}), 400
        
        temp_dir = Path(tempfile.mkdtemp())
        media_dir = temp_dir / 'Media'
        photos_dir = media_dir / 'Photos'
        videos_dir = media_dir / 'Videos'
        
        photos_dir.mkdir(parents=True, exist_ok=True)
        videos_dir.mkdir(parents=True, exist_ok=True)
        
        for img_name in image_names:
            src = IMAGES_PATH / img_name
            if src.exists():
                shutil.copy2(src, photos_dir / img_name)
                print(f"   [COPY] Image: {img_name}")
        
        for vid_name in video_names:
            src = VIDEOS_PATH / vid_name
            if src.exists():
                shutil.copy2(src, videos_dir / vid_name)
                print(f"   [COPY] Video: {vid_name}")
        
        zip_filename = f'Person_{person_id}_Media.zip'
        zip_path = temp_dir / zip_filename
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(media_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
        
        with open(zip_path, 'rb') as f:
            zip_data = f.read()
        
        shutil.rmtree(temp_dir)
        
        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        print(f"[ERROR] Merge error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@video_bp.route('/check_dependencies', methods=['GET'])
def check_dependencies_route():
    missing = check_dependencies()
    if missing:
        return jsonify({
            'status': 'error',
            'missing': missing,
            'message': f"Missing dependencies: {', '.join(missing)}. Please install: pip install {' '.join(missing)}"
        }), 500
    else:
        return jsonify({
            'status': 'ok',
            'message': 'All dependencies installed'
        })

@video_bp.route('/info', methods=['GET'])
def system_info():
    return jsonify({
        'base_path': str(BASE_PATH),
        'output_path': str(OUTPUT_PATH),
        'python_executable': sys.executable,
        'python_version': sys.version
    })

@video_bp.route('/list', methods=['GET'])
def list_videos():
    """List all generated videos"""
    try:
        videos = []
        for person_dir in OUTPUT_PATH.iterdir():
            if person_dir.is_dir() and person_dir.name.startswith('person_'):
                person_id = person_dir.name.replace('person_', '')
                for video_file in person_dir.glob('*.mp4'):
                    videos.append({
                        'person_id': person_id,
                        'filename': video_file.name,
                        'path': str(video_file),
                        'size_mb': round(video_file.stat().st_size / (1024 * 1024), 2),
                        'created': datetime.fromtimestamp(video_file.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                    })
        return jsonify({'videos': sorted(videos, key=lambda x: x['created'], reverse=True)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@video_bp.route('/download/<person_id>/<filename>', methods=['GET'])
def download_video(person_id, filename):
    """Download a specific generated video"""
    try:
        video_path = OUTPUT_PATH / f"person_{person_id}" / filename
        if not video_path.exists():
            return jsonify({'error': 'Video not found'}), 404
        
        print(f"[DOWNLOAD] Serving video: {video_path}")
        
        return send_file(
            video_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"[ERROR] Download error: {e}")
        return jsonify({'error': str(e)}), 500