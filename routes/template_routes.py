# E:\00000\Rahstaa\My_gallery_2\routes\template_routes.py
"""
Template Routes - Handle video template management
"""

import os
import shutil
import re
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, send_file, flash, redirect, url_for, current_app
from werkzeug.utils import secure_filename

template_bp = Blueprint('template', __name__, url_prefix='/template')

# ============================================================
# PATHS
# ============================================================
BASE_PATH = Path(r'E:\00000\Rahstaa\My_gallery_2')
ASSETS_PATH = BASE_PATH / 'assets'
OUTPUT_PATH = BASE_PATH / 'output'

# Ensure directories exist
for path in [ASSETS_PATH, OUTPUT_PATH]:
    path.mkdir(parents=True, exist_ok=True)

# Allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac'}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_templates():
    """Get all template folders in assets"""
    templates = []
    if ASSETS_PATH.exists():
        for folder in ASSETS_PATH.iterdir():
            if folder.is_dir():
                template_data = {
                    'name': folder.name,
                    'path': folder,
                    'has_starting': any(f.name.startswith('starting') for f in folder.iterdir() if f.is_file()),
                    'has_ending': any(f.name.startswith('ending') for f in folder.iterdir() if f.is_file()),
                    'has_music': any(f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS for f in folder.iterdir() if f.is_file()),
                    'has_captions': (folder / 'Captions.txt').exists(),
                    'created': datetime.fromtimestamp(folder.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                }
                templates.append(template_data)
    return sorted(templates, key=lambda x: x['created'], reverse=True)

def get_template_assets(template_name):
    """Get all assets for a specific template"""
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
    
    # Get fixed assets
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
    
    # Get extra assets from folders
    extra_images_path = template_path / 'extra_images'
    if extra_images_path.exists():
        assets['extra_images'] = [f for f in extra_images_path.iterdir() if f.is_file() and f.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS]
    
    extra_videos_path = template_path / 'extra_videos'
    if extra_videos_path.exists():
        assets['extra_videos'] = [f for f in extra_videos_path.iterdir() if f.is_file() and f.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS]
    
    # Also check root folder for extra assets (excluding fixed)
    for f in template_path.iterdir():
        if f.is_file():
            if f.name.startswith('starting') or f.name.startswith('ending'):
                continue
            if f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS:
                continue
            if f.name == 'Captions.txt':
                continue
            if f.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
                if f not in assets['extra_images']:
                    assets['extra_images'].append(f)
            elif f.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS:
                if f not in assets['extra_videos']:
                    assets['extra_videos'].append(f)
    
    return assets

def get_output_videos(template_name):
    """Get generated videos for a template"""
    output_dir = OUTPUT_PATH / template_name
    if not output_dir.exists():
        return []
    
    videos = []
    for file in output_dir.glob('*.mp4'):
        videos.append({
            'name': file.name,
            'path': file,
            'size': f"{file.stat().st_size / (1024 * 1024):.2f} MB",
            'created': datetime.fromtimestamp(file.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')
        })
    return sorted(videos, key=lambda x: x['created'], reverse=True)

def template_exists(template_name):
    """Check if template exists"""
    return (ASSETS_PATH / template_name).exists()

def validate_template_name(name):
    """Validate template name"""
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', name))

# ============================================================
# ROUTES
# ============================================================

@template_bp.route('/')
def templates():
    """Templates management page"""
    templates = get_templates()
    return render_template('templates.html', 
                         templates=templates,
                         active_page='templates')

@template_bp.route('/create', methods=['GET', 'POST'])
def create_template():
    """Create a new template"""
    if request.method == 'POST':
        print("=" * 60)
        print("📝 CREATE TEMPLATE - POST REQUEST RECEIVED")
        print("=" * 60)
        
        template_name = request.form.get('template_name', '').strip()
        print(f"📌 Template Name: {template_name}")
        
        if not template_name:
            flash('Template name is required', 'error')
            return render_template('template_create.html')
        
        if not validate_template_name(template_name):
            flash('Template name can only contain letters, numbers, underscores, and hyphens', 'error')
            return render_template('template_create.html')
        
        template_path = ASSETS_PATH / template_name
        
        if template_path.exists():
            flash('Template already exists', 'error')
            return render_template('template_create.html')
        
        try:
            template_path.mkdir(parents=True)
            (template_path / 'extra_images').mkdir(exist_ok=True)
            (template_path / 'extra_videos').mkdir(exist_ok=True)
            print(f"✅ Template folder created: {template_path}")
            
            # Upload starting asset
            if 'starting_asset' in request.files:
                file = request.files['starting_asset']
                if file.filename:
                    ext = Path(secure_filename(file.filename)).suffix
                    file.save(template_path / f"starting{ext}")
                    print(f"✅ Starting asset saved: starting{ext}")
            
            # Upload ending asset
            if 'ending_asset' in request.files:
                file = request.files['ending_asset']
                if file.filename:
                    ext = Path(secure_filename(file.filename)).suffix
                    file.save(template_path / f"ending{ext}")
                    print(f"✅ Ending asset saved: ending{ext}")
            
            # Upload music
            if 'music_file' in request.files:
                file = request.files['music_file']
                if file.filename:
                    filename = secure_filename(file.filename)
                    file.save(template_path / filename)
                    print(f"✅ Music saved: {filename}")
            
            # Upload captions
            if 'captions_file' in request.files:
                file = request.files['captions_file']
                if file.filename:
                    file.save(template_path / 'Captions.txt')
                    print(f"✅ Captions saved: Captions.txt")
            
            # Upload extra images
            if 'extra_images' in request.files:
                extra_images_path = template_path / 'extra_images'
                for file in request.files.getlist('extra_images'):
                    if file.filename:
                        filename = secure_filename(file.filename)
                        counter = 1
                        dst_path = extra_images_path / filename
                        while dst_path.exists():
                            name, ext = os.path.splitext(filename)
                            new_name = f"{name}_{counter}{ext}"
                            dst_path = extra_images_path / new_name
                            counter += 1
                        file.save(dst_path)
                        print(f"✅ Extra image saved: {dst_path.name}")
            
            # Upload extra videos
            if 'extra_videos' in request.files:
                extra_videos_path = template_path / 'extra_videos'
                for file in request.files.getlist('extra_videos'):
                    if file.filename:
                        filename = secure_filename(file.filename)
                        counter = 1
                        dst_path = extra_videos_path / filename
                        while dst_path.exists():
                            name, ext = os.path.splitext(filename)
                            new_name = f"{name}_{counter}{ext}"
                            dst_path = extra_videos_path / new_name
                            counter += 1
                        file.save(dst_path)
                        print(f"✅ Extra video saved: {dst_path.name}")
            
            flash(f'Template "{template_name}" created successfully!', 'success')
            print("=" * 60)
            return redirect(url_for('template.view_template', template_name=template_name))
            
        except Exception as e:
            flash(f'Error creating template: {str(e)}', 'error')
            print(f"❌ Error creating template: {e}")
            import traceback
            traceback.print_exc()
            return render_template('template_create.html')
    
    # GET request - show the form
    return render_template('template_create.html')

@template_bp.route('/<template_name>')
def view_template(template_name):
    """View template details"""
    if not template_exists(template_name):
        flash('Template not found', 'error')
        return redirect(url_for('template.templates'))
    
    assets = get_template_assets(template_name)
    output_videos = get_output_videos(template_name)
    
    return render_template('template_view.html',
                         template_name=template_name,
                         assets=assets,
                         output_videos=output_videos,
                         active_page='templates')

@template_bp.route('/<template_name>/edit', methods=['GET', 'POST'])
def edit_template(template_name):
    """Edit template assets"""
    if not template_exists(template_name):
        flash('Template not found', 'error')
        return redirect(url_for('template.templates'))
    
    template_path = ASSETS_PATH / template_name
    
    if request.method == 'POST':
        try:
            # Upload starting asset
            if 'starting_asset' in request.files:
                file = request.files['starting_asset']
                if file.filename:
                    # Remove old starting asset
                    for f in template_path.iterdir():
                        if f.name.startswith('starting'):
                            f.unlink()
                    ext = Path(secure_filename(file.filename)).suffix
                    file.save(template_path / f"starting{ext}")
                    print(f"✅ Starting asset updated: starting{ext}")
            
            # Upload ending asset
            if 'ending_asset' in request.files:
                file = request.files['ending_asset']
                if file.filename:
                    # Remove old ending asset
                    for f in template_path.iterdir():
                        if f.name.startswith('ending'):
                            f.unlink()
                    ext = Path(secure_filename(file.filename)).suffix
                    file.save(template_path / f"ending{ext}")
                    print(f"✅ Ending asset updated: ending{ext}")
            
            # Upload music
            if 'music_file' in request.files:
                file = request.files['music_file']
                if file.filename:
                    # Remove old music
                    for f in template_path.iterdir():
                        if f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS:
                            f.unlink()
                    filename = secure_filename(file.filename)
                    file.save(template_path / filename)
                    print(f"✅ Music updated: {filename}")
            
            # Upload captions
            if 'captions_file' in request.files:
                file = request.files['captions_file']
                if file.filename:
                    file.save(template_path / 'Captions.txt')
                    print(f"✅ Captions updated: Captions.txt")
            
            # Upload extra images
            if 'extra_images' in request.files:
                extra_images_path = template_path / 'extra_images'
                extra_images_path.mkdir(exist_ok=True)
                for file in request.files.getlist('extra_images'):
                    if file.filename:
                        filename = secure_filename(file.filename)
                        counter = 1
                        dst_path = extra_images_path / filename
                        while dst_path.exists():
                            name, ext = os.path.splitext(filename)
                            new_name = f"{name}_{counter}{ext}"
                            dst_path = extra_images_path / new_name
                            counter += 1
                        file.save(dst_path)
                        print(f"✅ Extra image added: {dst_path.name}")
            
            # Upload extra videos
            if 'extra_videos' in request.files:
                extra_videos_path = template_path / 'extra_videos'
                extra_videos_path.mkdir(exist_ok=True)
                for file in request.files.getlist('extra_videos'):
                    if file.filename:
                        filename = secure_filename(file.filename)
                        counter = 1
                        dst_path = extra_videos_path / filename
                        while dst_path.exists():
                            name, ext = os.path.splitext(filename)
                            new_name = f"{name}_{counter}{ext}"
                            dst_path = extra_videos_path / new_name
                            counter += 1
                        file.save(dst_path)
                        print(f"✅ Extra video added: {dst_path.name}")
            
            flash('Template updated successfully!', 'success')
            return redirect(url_for('template.view_template', template_name=template_name))
            
        except Exception as e:
            flash(f'Error updating template: {str(e)}', 'error')
            print(f"❌ Error updating template: {e}")
    
    assets = get_template_assets(template_name)
    return render_template('template_edit.html',
                         template_name=template_name,
                         assets=assets,
                         active_page='templates')

@template_bp.route('/<template_name>/delete', methods=['POST'])
def delete_template(template_name):
    """Delete a template"""
    template_path = ASSETS_PATH / template_name
    if template_path.exists():
        try:
            shutil.rmtree(template_path)
            # Also remove output directory if exists
            output_dir = OUTPUT_PATH / template_name
            if output_dir.exists():
                shutil.rmtree(output_dir)
            flash(f'Template "{template_name}" deleted successfully', 'success')
        except Exception as e:
            flash(f'Error deleting template: {str(e)}', 'error')
    else:
        flash('Template not found', 'error')
    return redirect(url_for('template.templates'))

@template_bp.route('/<template_name>/asset/delete', methods=['POST'])
def delete_asset(template_name):
    """Delete an asset from template"""
    template_path = ASSETS_PATH / template_name
    if not template_path.exists():
        return jsonify({'error': 'Template not found'}), 404
    
    asset_type = request.form.get('asset_type')
    filename = request.form.get('filename', '')
    
    if asset_type == 'starting':
        for f in template_path.iterdir():
            if f.name.startswith('starting'):
                f.unlink()
        return jsonify({'success': True})
        
    elif asset_type == 'ending':
        for f in template_path.iterdir():
            if f.name.startswith('ending'):
                f.unlink()
        return jsonify({'success': True})
        
    elif asset_type == 'music':
        for f in template_path.iterdir():
            if f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS:
                f.unlink()
        return jsonify({'success': True})
        
    elif asset_type == 'captions':
        captions_file = template_path / 'Captions.txt'
        if captions_file.exists():
            captions_file.unlink()
        return jsonify({'success': True})
        
    elif asset_type == 'extra_image':
        file_path = template_path / 'extra_images' / filename
        if file_path.exists():
            file_path.unlink()
        return jsonify({'success': True})
        
    elif asset_type == 'extra_video':
        file_path = template_path / 'extra_videos' / filename
        if file_path.exists():
            file_path.unlink()
        return jsonify({'success': True})
        
    elif asset_type == 'extra':
        # Delete from root
        file_path = template_path / filename
        if file_path.exists():
            file_path.unlink()
        return jsonify({'success': True})
    
    return jsonify({'error': 'Invalid asset type'}), 400

@template_bp.route('/<template_name>/generate', methods=['POST'])
def generate_video(template_name):
    """Generate video using the template"""
    if not template_exists(template_name):
        flash('Template not found', 'error')
        return redirect(url_for('template.templates'))
    
    try:
        # Get parameters from form
        max_duration = request.form.get('max_duration', 175)
        fps = request.form.get('fps', 30)
        resolution = request.form.get('resolution', '1920x1080')
        max_extra = request.form.get('max_extra', 20)
        
        # Import and run the video generator
        import subprocess
        import sys
        
        cmd = [
            sys.executable,
            str(BASE_PATH / 'short_film.py'),
            '--template', template_name,
            '--max-duration', str(max_duration),
            '--fps', str(fps),
            '--resolution', resolution,
            '--max-extra', str(max_extra)
        ]
        
        print(f"🎬 Generating video with command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            flash(f'Video generated successfully for template "{template_name}"!', 'success')
            print(f"✅ Video generated successfully for {template_name}")
        else:
            flash(f'Error generating video: {result.stderr}', 'error')
            print(f"❌ Video generation error: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        flash('Video generation timed out. The video might be too long.', 'error')
        print("❌ Video generation timed out")
    except Exception as e:
        flash(f'Error generating video: {str(e)}', 'error')
        print(f"❌ Video generation error: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('template.view_template', template_name=template_name))

# ============================================================
# API ENDPOINTS
# ============================================================

@template_bp.route('/api/templates')
def api_templates():
    """Get all templates"""
    return jsonify({'templates': get_templates()})

@template_bp.route('/api/template/<template_name>/assets')
def api_template_assets(template_name):
    """Get template assets"""
    if not template_exists(template_name):
        return jsonify({'error': 'Template not found'}), 404
    
    assets = get_template_assets(template_name)
    if assets:
        return jsonify({
            'starting': assets['starting'].name if assets['starting'] else None,
            'ending': assets['ending'].name if assets['ending'] else None,
            'music': assets['music'].name if assets['music'] else None,
            'captions': assets['captions'] is not None,
            'extra_images': [img.name for img in assets['extra_images']],
            'extra_videos': [vid.name for vid in assets['extra_videos']]
        })
    return jsonify({'error': 'Template not found'}), 404

@template_bp.route('/api/template/<template_name>/output')
def api_template_output(template_name):
    """Get output videos for a template"""
    if not template_exists(template_name):
        return jsonify({'error': 'Template not found'}), 404
    
    return jsonify({'videos': get_output_videos(template_name)})

# ============================================================
# STATIC FILE SERVING
# ============================================================

@template_bp.route('/asset/<template_name>/<path:filename>')
def serve_asset(template_name, filename):
    """Serve template assets"""
    template_path = ASSETS_PATH / template_name
    if not template_path.exists():
        return jsonify({'error': 'Template not found'}), 404
    
    # Check in root
    file_path = template_path / filename
    if file_path.exists():
        return send_file(file_path)
    
    # Check in extra_images
    file_path = template_path / 'extra_images' / filename
    if file_path.exists():
        return send_file(file_path)
    
    # Check in extra_videos
    file_path = template_path / 'extra_videos' / filename
    if file_path.exists():
        return send_file(file_path)
    
    return jsonify({'error': 'File not found'}), 404

@template_bp.route('/output/<template_name>/<path:filename>')
def serve_output(template_name, filename):
    """Serve generated output videos"""
    file_path = OUTPUT_PATH / template_name / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path)