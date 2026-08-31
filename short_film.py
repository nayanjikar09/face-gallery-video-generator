#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
short_film.py - Video Generator Script
Generates a video from images and videos using a template.

Follows the same logic as short_film_2.ipynb with all features:
- Chronological sorting by capture time
- Image animations (zoom, pan)
- Fade transitions
- Captions with PIL
- Music integration
- Extra assets random placement
- Time limit enforcement

Usage:
    python short_film.py --template TEMPLATE_NAME --person-id PERSON_ID --output OUTPUT_PATH
                         [--images-list IMG1,IMG2,...] [--videos-list VID1,VID2,...]
                         [--resolution WxH] [--max-duration SECONDS]

Environment Variables:
    TEMPLATE_PATH - Path to template folder (overrides --template)
"""

import os
import sys
import re
import random
import shutil
import subprocess
import json
import argparse
import gc
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import warnings
warnings.filterwarnings('ignore')

# Image processing
from PIL import Image
from PIL.ExifTags import TAGS
import numpy as np

# Video processing
import cv2

# MoviePy for video editing
from moviepy.editor import (
    VideoFileClip, 
    ImageClip, 
    AudioFileClip, 
    CompositeVideoClip,
    concatenate_videoclips, 
    TextClip, 
    ColorClip, 
    vfx, 
    afx
)
from moviepy.video.fx import fadein, fadeout
import moviepy.video.fx.all as vfx_all

print("="*60)
print("🎬 SHORT FILM GENERATOR")
print("="*60)

# ============================================================
# CONFIGURATION
# ============================================================

# Supported formats
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac'}

# Default output size
DEFAULT_RESOLUTION = (1920, 1080)

# ============================================================
# ARGUMENT PARSING
# ============================================================

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Generate short film from media')
    parser.add_argument('--template', type=str, required=True, help='Template name')
    parser.add_argument('--person-id', type=str, required=True, help='Person ID')
    parser.add_argument('--output', type=str, required=True, help='Output file path')
    parser.add_argument('--resolution', type=str, default='1280x720', help='Resolution (WxH)')
    parser.add_argument('--max-duration', type=int, default=175, help='Maximum duration in seconds')
    parser.add_argument('--images-list', type=str, default='', help='Comma-separated list of images')
    parser.add_argument('--videos-list', type=str, default='', help='Comma-separated list of videos')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second')
    parser.add_argument('--max-extra', type=int, default=10, help='Maximum extra assets to include')
    return parser.parse_args()

# ============================================================
# PATH RESOLUTION
# ============================================================

def get_base_path():
    """Get the base path dynamically"""
    # Try environment variable first
    env_path = os.environ.get('GALLERY_BASE_PATH')
    if env_path:
        return Path(env_path)
    
    # Try current directory
    current_dir = Path(__file__).parent
    if (current_dir / 'assets').exists() and (current_dir / 'images').exists():
        return current_dir
    
    # Try parent directory
    parent_dir = current_dir.parent
    if (parent_dir / 'assets').exists() and (parent_dir / 'images').exists():
        return parent_dir
    
    # Default fallback
    return Path(r'E:\00000\Rahstaa\My_gallery_2')

BASE_PATH = get_base_path()
print(f"📁 Base Path: {BASE_PATH}")

# ============================================================
# HELPER FUNCTIONS - EXACTLY AS IN NOTEBOOK
# ============================================================

def make_timezone_naive(dt):
    """Convert timezone-aware datetime to timezone-naive"""
    if dt is not None and hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def extract_capture_time(file_path):
    """Extract capture time from file metadata - from notebook BLOCK 08"""
    try:
        # For images
        if file_path.suffix.lower() in IMAGE_EXTENSIONS:
            try:
                img = Image.open(file_path)
                exif = img._getexif()
                if exif:
                    for tag_id, value in exif.items():
                        tag_name = TAGS.get(tag_id, tag_id)
                        if tag_name in ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']:
                            try:
                                dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                                img.close()
                                return dt
                            except:
                                continue
                img.close()
            except:
                pass
        
        # For videos - try ffprobe
        if file_path.suffix.lower() in VIDEO_EXTENSIONS:
            try:
                cmd = [
                    'ffprobe', '-v', 'quiet', '-print_format', 'json',
                    '-show_format', str(file_path)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    if 'format' in data and 'tags' in data['format']:
                        tags = data['format']['tags']
                        for key in ['creation_time', 'date', 'com.apple.quicktime.creationdate']:
                            if key in tags:
                                try:
                                    dt_str = tags[key]
                                    if 'T' in dt_str:
                                        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                                    else:
                                        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                                    return dt
                                except:
                                    continue
            except:
                pass
        
        # Fallback: file creation time
        creation_time = os.path.getctime(file_path)
        return datetime.fromtimestamp(creation_time)
        
    except Exception as e:
        # Final fallback: file modification time
        try:
            mod_time = os.path.getmtime(file_path)
            return datetime.fromtimestamp(mod_time)
        except:
            return datetime.now()

def get_capture_time(file_path):
    """Wrapper for extraction with fallback - from notebook BLOCK 08"""
    try:
        dt = extract_capture_time(file_path)
        return dt
    except Exception as e:
        return datetime.now()

def load_captions(captions_file):
    """Load captions from text file - from notebook BLOCK 04"""
    try:
        with open(captions_file, 'r', encoding='utf-8') as f:
            captions = [line.strip() for line in f.readlines() if line.strip()]
        print(f"📝 Loaded {len(captions)} captions from {captions_file.name}")
        return captions
    except Exception as e:
        print(f"⚠️ Error loading captions: {e}")
        # Return default captions
        default_captions = [
            "A beautiful beginning",
            "Memories with family",
            "A day to remember",
            "Beautiful moments together",
            "The journey continues",
            "Forever in our hearts"
        ]
        print(f"ℹ️ Using {len(default_captions)} default captions instead")
        return default_captions

def prepare_image_clip(image_path, duration=3.0, target_size=(1920, 1080)):
    """Prepare an image as a video clip - from notebook BLOCK 11"""
    try:
        img_clip = ImageClip(str(image_path)).set_duration(duration)
        
        # Resize to target resolution
        if img_clip.size != target_size:
            try:
                img_clip = img_clip.resize(newsize=target_size)
            except TypeError:
                img_clip = img_clip.resize(target_size)
        
        return img_clip
    except Exception as e:
        print(f"  ❌ Error preparing {image_path.name}: {e}")
        fallback = ColorClip(size=target_size, color=(50, 50, 50), duration=duration)
        return fallback

def trim_video_clip(video_path, duration=4.0, target_size=(1920, 1080)):
    """Extract a 3-4 second segment from a video - from notebook BLOCK 12"""
    try:
        clip = VideoFileClip(str(video_path))
        
        # Resize to target
        clip = clip.resize(target_size)
        
        # If video is short, use it entirely
        if clip.duration <= duration:
            print(f"  🎬 Using full {video_path.name} ({clip.duration:.1f}s)")
            return clip
        
        # Select a reasonable section (avoid first 3 seconds, prefer middle)
        start_time = random.uniform(3.0, max(3.0, clip.duration - duration - 1.0))
        start_time = min(start_time, clip.duration - duration)
        end_time = start_time + duration
        
        # Extract the segment
        subclip = clip.subclip(start_time, end_time)
        
        print(f"  🎬 Trimmed {video_path.name}: {start_time:.1f}s → {end_time:.1f}s ({duration:.1f}s)")
        return subclip
    except Exception as e:
        print(f"  ❌ Error trimming {video_path.name}: {e}")
        fallback = ColorClip(size=target_size, color=(50, 50, 50), duration=duration)
        return fallback

def create_text_image(text, fontsize=48, color='white', bg_color=(0, 0, 0, 180)):
    """Create a text image using PIL - from notebook BLOCK 20"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a temporary image to measure text
        temp_img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(temp_img)
        
        # Try to load a font
        try:
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/calibri.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/System/Library/Fonts/Helvetica.ttc"
            ]
            font = None
            for path in font_paths:
                if os.path.exists(path):
                    font = ImageFont.truetype(path, fontsize)
                    break
            if font is None:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
        
        # Measure text
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # Add padding
        padding = 30
        img_width = text_width + padding * 2
        img_height = text_height + padding * 2
        
        # Create image with transparent background
        img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw rounded rectangle background
        draw.rectangle([0, 0, img_width, img_height], fill=bg_color)
        
        # Draw text
        draw.text((padding, padding), text, font=font, fill=color)
        
        # Convert to numpy array for MoviePy
        img_array = np.array(img)
        return img_array
    except Exception as e:
        print(f"  ⚠️ Error creating text image: {e}")
        return np.zeros((100, 400, 4), dtype=np.uint8)

def add_image_animations(clip, duration, animation_type=None):
    """Add subtle animations to an image clip - from notebook BLOCK 17"""
    if animation_type is None:
        animation_type = random.choice(['zoom_in', 'zoom_out', 'pan_left', 'pan_right'])
    
    try:
        if animation_type == 'zoom_in':
            return clip.resize(lambda t: 1 + 0.02 * (t / duration if duration > 0 else 1))
        elif animation_type == 'zoom_out':
            return clip.resize(lambda t: 1.02 - 0.02 * (t / duration if duration > 0 else 1))
        elif animation_type == 'pan_left':
            clip = clip.resize(width=clip.w * 1.05)
            return clip.set_position(lambda t: (-5 * t, 0))
        elif animation_type == 'pan_right':
            clip = clip.resize(width=clip.w * 1.05)
            return clip.set_position(lambda t: (5 * t, 0))
    except Exception as e:
        pass
    return clip

def add_transitions(clips, transition_duration=0.3):
    """Add smooth transitions between clips - from notebook BLOCK 18"""
    if len(clips) <= 1:
        return clips
    
    try:
        final_clips = []
        for i, clip in enumerate(clips):
            if i > 0:
                clip = fadein.fadein(clip, transition_duration)
            if i < len(clips) - 1:
                clip = fadeout.fadeout(clip, transition_duration)
            final_clips.append(clip)
        
        return final_clips
    except Exception as e:
        print(f"⚠️ Error adding transitions: {e}")
        return clips

def calculate_caption_timing(timeline, captions, total_duration):
    """Calculate when each caption should appear - from notebook BLOCK 19"""
    if not captions:
        return []
    
    caption_intervals = []
    num_captions = len(captions)
    
    # Get segment boundaries
    segment_boundaries = []
    cumulative_time = 0
    for seg in timeline:
        segment_boundaries.append(cumulative_time)
        seg_duration = seg.get('duration', 3.0)
        cumulative_time += seg_duration
    segment_boundaries.append(cumulative_time)
    
    actual_duration = cumulative_time
    
    # Distribute captions evenly across timeline
    for i, caption in enumerate(captions):
        position = (i + 0.5) / num_captions * actual_duration
        
        # Find which segment this position falls in
        segment_index = 0
        for j, boundary in enumerate(segment_boundaries):
            if position < boundary:
                segment_index = max(0, j - 1)
                break
        
        # Adjust position to segment start if needed
        if segment_index < len(timeline):
            seg_start = segment_boundaries[segment_index]
            seg_end = segment_boundaries[segment_index + 1]
            position = max(seg_start + 0.5, min(position, seg_end - 0.5))
        
        # Calculate duration for this caption
        if i < num_captions - 1:
            next_position = (i + 1.5) / num_captions * actual_duration
            duration = min(next_position - position, 8.0)
        else:
            duration = min(actual_duration - position, 8.0)
        
        duration = max(duration, 2.0)
        
        caption_intervals.append({
            'caption': caption,
            'start_time': position,
            'duration': duration,
            'end_time': position + duration
        })
    
    return caption_intervals

def add_captions_to_clips(caption_timing, target_size=(1920, 1080)):
    """Create caption overlays for the video using PIL - from notebook BLOCK 20"""
    if not caption_timing:
        return []
    
    caption_overlays = []
    
    for timing in caption_timing:
        try:
            text_array = create_text_image(
                timing['caption'],
                fontsize=48,
                color='white',
                bg_color=(0, 0, 0, 180)
            )
            txt_clip = ImageClip(text_array, transparent=True)
            txt_clip = txt_clip.set_duration(timing['duration'])
            txt_clip = txt_clip.set_start(timing['start_time'])
            txt_clip = txt_clip.set_position(('center', 'bottom'))
            caption_overlays.append(txt_clip)
        except Exception as e:
            print(f"  ⚠️ Error creating caption: {e}")
            continue
    
    return caption_overlays

def enforce_time_limit(clips, clip_info, max_duration=175):
    """Enforce that the total duration is under max_duration - from notebook BLOCK 15-16"""
    total_duration = sum(clip.duration for clip in clips)
    print(f"\n⏱️ Initial total duration: {total_duration:.1f}s")
    
    if total_duration <= max_duration:
        print(f"✅ Duration is already under {max_duration}s")
        return clips, clip_info
    
    print(f"⚠️ Duration exceeds {max_duration}s - optimizing...")
    
    optimized_clips = [clips[0]]
    optimized_info = [clip_info[0]]
    
    middle_clips = clips[1:-1]
    middle_info = clip_info[1:-1]
    kept_clips = []
    kept_info = []
    current_duration = clips[0].duration + clips[-1].duration
    
    for clip, info in zip(middle_clips, middle_info):
        is_extra = info.get('is_extra', False)
        
        if is_extra and current_duration + clip.duration > max_duration:
            print(f"   Skipping extra asset: {info.get('name', 'unknown')}")
            continue
        
        kept_clips.append(clip)
        kept_info.append(info)
        current_duration += clip.duration
    
    optimized_clips = [clips[0]] + kept_clips + [clips[-1]]
    optimized_info = [clip_info[0]] + kept_info + [clip_info[-1]]
    
    print(f"✅ Optimized duration: {current_duration:.1f}s")
    return optimized_clips, optimized_info

# ============================================================
# MAIN VIDEO GENERATION FUNCTION
# ============================================================

def generate_video(args):
    """Main video generation function - follows notebook logic"""
    
    print("\n" + "="*60)
    print("🎬 GENERATING VIDEO")
    print("="*60)
    print(f"📌 Template: {args.template}")
    print(f"📌 Person ID: {args.person_id}")
    print(f"📌 Output: {args.output}")
    print(f"📌 Resolution: {args.resolution}")
    print(f"📌 Max Duration: {args.max_duration}s")
    print("="*60 + "\n")
    
    # Parse resolution
    try:
        width, height = map(int, args.resolution.split('x'))
        target_size = (width, height)
    except:
        target_size = DEFAULT_RESOLUTION
        print(f"⚠️ Invalid resolution, using default: {DEFAULT_RESOLUTION}")
    
    # Get template path
    template_name = args.template
    
    # Try environment variable first
    template_path_env = os.environ.get('TEMPLATE_PATH')
    if template_path_env:
        template_path = Path(template_path_env)
        print(f"📁 Using template from environment: {template_path}")
    else:
        template_path = BASE_PATH / 'assets' / template_name
        print(f"📁 Using template from assets: {template_path}")
    
    if not template_path.exists():
        print(f"❌ Template not found: {template_path}")
        alt_paths = [
            BASE_PATH / 'assets' / template_name,
            Path.cwd() / 'assets' / template_name,
            Path(__file__).parent / 'assets' / template_name
        ]
        for alt in alt_paths:
            if alt.exists():
                template_path = alt
                print(f"✅ Found template at: {template_path}")
                break
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_name}")
    
    # Load template assets - from notebook BLOCK 13-14
    print("\n📂 Loading template assets...")
    
    # Find starting video
    starting_video = None
    for f in template_path.iterdir():
        if f.is_file() and f.name.startswith('starting'):
            starting_video = f
            break
    if not starting_video:
        print("⚠️ No starting video found, using fallback")
    
    # Find ending image
    ending_image = None
    for f in template_path.iterdir():
        if f.is_file() and f.name.startswith('ending'):
            ending_image = f
            break
    if not ending_image:
        print("⚠️ No ending image found, using fallback")
    
    # Find music
    music_file = None
    for f in template_path.iterdir():
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            music_file = f
            break
    if not music_file:
        print("⚠️ No music file found, continuing without music")
    
    # Find captions
    captions_file = template_path / 'Captions.txt'
    if not captions_file.exists():
        captions_file = None
        print("⚠️ No captions file found, using default captions")
    
    # Load captions - from notebook BLOCK 04
    captions = load_captions(captions_file) if captions_file else load_captions(Path(__file__).parent / 'assets' / 'default_captions.txt')
    
    # Get extra assets from template - SCAN ALL LOCATIONS - from notebook BLOCK 03
    extra_images = []
    extra_videos = []
    
    # 1. Check extra_images folder
    extra_images_path = template_path / 'extra_images'
    if extra_images_path.exists():
        for f in extra_images_path.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                extra_images.append(f)
                print(f"   📸 Found extra image: {f.name}")
    
    # 2. Check extra_videos folder
    extra_videos_path = template_path / 'extra_videos'
    if extra_videos_path.exists():
        for f in extra_videos_path.iterdir():
            if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
                extra_videos.append(f)
                print(f"   🎬 Found extra video: {f.name}")
    
    # 3. Also check root folder for extra assets (excluding fixed assets)
    for f in template_path.iterdir():
        if f.is_file():
            if f.name.startswith('starting') or f.name.startswith('ending'):
                continue
            if f.suffix.lower() in AUDIO_EXTENSIONS:
                continue
            if f.name == 'Captions.txt':
                continue
            if f.suffix.lower() in IMAGE_EXTENSIONS:
                if f not in extra_images:
                    extra_images.append(f)
                    print(f"   📸 Found extra image in root: {f.name}")
            elif f.suffix.lower() in VIDEO_EXTENSIONS:
                if f not in extra_videos:
                    extra_videos.append(f)
                    print(f"   🎬 Found extra video in root: {f.name}")
    
    print(f"\n📸 Total extra images: {len(extra_images)}")
    print(f"🎬 Total extra videos: {len(extra_videos)}")
    
    # Get person's media from arguments - from notebook BLOCK 05-06
    person_images = []
    person_videos = []
    
    if args.images_list:
        image_names = [name.strip() for name in args.images_list.split(',') if name.strip()]
        for name in image_names:
            possible_paths = [
                BASE_PATH / 'images' / name,
                Path.cwd() / 'images' / name,
                template_path / 'extra_images' / name,
                extra_images_path / name
            ]
            found = False
            for path in possible_paths:
                if path.exists():
                    person_images.append(path)
                    found = True
                    break
            if not found:
                print(f"   ⚠️ Image not found: {name}")
    
    if args.videos_list:
        video_names = [name.strip() for name in args.videos_list.split(',') if name.strip()]
        for name in video_names:
            possible_paths = [
                BASE_PATH / 'videos' / name,
                Path.cwd() / 'videos' / name,
                template_path / 'extra_videos' / name,
                extra_videos_path / name
            ]
            found = False
            for path in possible_paths:
                if path.exists():
                    person_videos.append(path)
                    found = True
                    break
            if not found:
                print(f"   ⚠️ Video not found: {name}")
    
    print(f"\n👤 Person images: {len(person_images)}")
    print(f"👤 Person videos: {len(person_videos)}")
    
    # Combine all media with capture times - from notebook BLOCK 07, 09
    all_media = []
    
    # Add person images with capture times
    for img_path in person_images:
        capture_time = extract_capture_time(img_path)
        capture_time = make_timezone_naive(capture_time)
        all_media.append({
            'path': img_path,
            'name': img_path.name,
            'type': 'image',
            'time': capture_time,
            'source': 'person'
        })
    
    # Add person videos with capture times
    for vid_path in person_videos:
        capture_time = extract_capture_time(vid_path)
        capture_time = make_timezone_naive(capture_time)
        all_media.append({
            'path': vid_path,
            'name': vid_path.name,
            'type': 'video',
            'time': capture_time,
            'source': 'person'
        })
    
    # Add extra assets (random placement) - from notebook BLOCK 10
    all_extra = extra_images + extra_videos
    extra_count = min(len(all_extra), args.max_extra)
    
    if extra_count > 0:
        random.shuffle(all_extra)
        selected_extra = all_extra[:extra_count]
        
        for extra_path in selected_extra:
            media_type = 'image' if extra_path.suffix.lower() in IMAGE_EXTENSIONS else 'video'
            if all_media:
                random_time = random.choice(all_media)['time']
            else:
                random_time = datetime.now()
            all_media.append({
                'path': extra_path,
                'name': extra_path.name,
                'type': media_type,
                'time': random_time,
                'source': 'extra',
                'is_extra': True
            })
        
        print(f"\n🎲 Added {len(selected_extra)} extra assets from template")
        for extra in selected_extra[:5]:
            print(f"   - {extra.name}")
        if len(selected_extra) > 5:
            print(f"   ... and {len(selected_extra) - 5} more")
    
    # Sort by time
    all_media.sort(key=lambda x: x['time'])
    
    print(f"\n📊 Total media: {len(all_media)} items")
    print(f"   Images: {sum(1 for m in all_media if m['type'] == 'image')}")
    print(f"   Videos: {sum(1 for m in all_media if m['type'] == 'video')}")
    print(f"   Extra: {sum(1 for m in all_media if m.get('is_extra', False))}")
    
    # Build timeline - from notebook BLOCK 15
    print("\n🔄 Building timeline...")
    timeline_clips = []
    clip_info = []
    
    # 1. Starting video - from notebook BLOCK 13
    if starting_video:
        try:
            start_clip = VideoFileClip(str(starting_video))
            start_clip = start_clip.resize(target_size)
            timeline_clips.append(start_clip)
            clip_info.append({'type': 'starting', 'name': starting_video.name, 'duration': start_clip.duration})
            print(f"  ✅ Starting video: {starting_video.name} ({start_clip.duration:.1f}s)")
        except Exception as e:
            print(f"  ❌ Error loading starting video: {e}")
            fallback = ColorClip(size=target_size, color=(0, 0, 50), duration=3.0)
            timeline_clips.append(fallback)
            clip_info.append({'type': 'starting', 'name': 'fallback', 'duration': 3.0})
    else:
        fallback = ColorClip(size=target_size, color=(0, 0, 50), duration=3.0)
        timeline_clips.append(fallback)
        clip_info.append({'type': 'starting', 'name': 'fallback', 'duration': 3.0})
    
    # 2. Main media - from notebook BLOCK 11-12
    for i, item in enumerate(all_media):
        try:
            if item['type'] == 'image':
                duration = random.uniform(3.0, 4.0)
                clip = prepare_image_clip(item['path'], duration, target_size)
                # Add animation - from notebook BLOCK 17
                clip = add_image_animations(clip, duration)
                clip_info.append({'type': 'image', 'name': item['name'], 'duration': duration, 'is_extra': item.get('is_extra', False)})
            else:
                duration = random.uniform(3.0, 4.0)
                clip = trim_video_clip(item['path'], duration, target_size)
                clip_info.append({'type': 'video', 'name': item['name'], 'duration': clip.duration, 'is_extra': item.get('is_extra', False)})
            
            if clip is not None:
                timeline_clips.append(clip)
                if i < 5:
                    extra_tag = " [EXTRA]" if item.get('is_extra', False) else ""
                    print(f"  ✅ Added {item['type']}{extra_tag}: {item['name']} ({clip.duration:.1f}s)")
        except Exception as e:
            print(f"  ❌ Error processing {item.get('name', 'unknown')}: {e}")
            continue
    
    # 3. Ending image - from notebook BLOCK 14
    if ending_image:
        try:
            duration = random.uniform(3.0, 5.0)
            end_clip = ImageClip(str(ending_image)).set_duration(duration)
            end_clip = end_clip.resize(target_size)
            # Add zoom effect
            def resize_with_zoom(t):
                zoom = 1 + 0.03 * (t / duration if duration > 0 else 1)
                return (target_size[0] * zoom, target_size[1] * zoom)
            try:
                end_clip = end_clip.resize(resize_with_zoom)
            except:
                pass
            timeline_clips.append(end_clip)
            clip_info.append({'type': 'ending', 'name': ending_image.name, 'duration': duration})
            print(f"  ✅ Ending image: {ending_image.name} ({duration:.1f}s)")
        except Exception as e:
            print(f"  ❌ Error loading ending image: {e}")
            fallback = ColorClip(size=target_size, color=(50, 0, 50), duration=4.0)
            timeline_clips.append(fallback)
            clip_info.append({'type': 'ending', 'name': 'fallback', 'duration': 4.0})
    else:
        fallback = ColorClip(size=target_size, color=(50, 0, 50), duration=4.0)
        timeline_clips.append(fallback)
        clip_info.append({'type': 'ending', 'name': 'fallback', 'duration': 4.0})
    
    # Add transitions - from notebook BLOCK 18
    print("\n🔄 Adding transitions...")
    timeline_clips = add_transitions(timeline_clips)
    
    # Enforce time limit - from notebook BLOCK 15-16
    timeline_clips, clip_info = enforce_time_limit(timeline_clips, clip_info, args.max_duration)
    
    # Concatenate video
    print("\n🎬 Concatenating video...")
    try:
        final_video = concatenate_videoclips(timeline_clips, method="chain")
        video_duration = final_video.duration
        print(f"  ✅ Video duration: {video_duration:.1f}s")
    except Exception as e:
        print(f"  ❌ Error concatenating: {e}")
        final_video = timeline_clips[0]
        video_duration = final_video.duration
    
    # Add captions - from notebook BLOCK 19-20
    print("\n📝 Adding captions...")
    caption_overlays = []
    
    if captions and video_duration > 10:
        # Build timeline for caption calculation
        timeline_for_captions = []
        for clip, info in zip(timeline_clips, clip_info):
            timeline_for_captions.append({
                'duration': clip.duration,
                'type': info.get('type', 'unknown')
            })
        
        caption_timing = calculate_caption_timing(timeline_for_captions, captions, video_duration)
        caption_overlays = add_captions_to_clips(caption_timing, target_size)
        print(f"  ✅ Added {len(caption_overlays)} captions")
    
    if caption_overlays:
        final_video = CompositeVideoClip([final_video] + caption_overlays)
    
    # Add music
    print("\n🎵 Adding music...")
    if music_file:
        try:
            music_clip = AudioFileClip(str(music_file))
            print(f"  ✅ Music loaded: {music_clip.duration:.1f}s")
            
            if music_clip.duration > video_duration:
                music_clip = music_clip.subclip(0, video_duration)
                print(f"  🔄 Music trimmed to {video_duration:.1f}s")
            else:
                from moviepy.audio.AudioClip import concatenate_audioclips
                loops_needed = int(video_duration / music_clip.duration) + 1
                audio_clips = [music_clip] * loops_needed
                music_clip = concatenate_audioclips(audio_clips)
                if music_clip.duration > video_duration:
                    music_clip = music_clip.subclip(0, video_duration)
                print(f"  🔄 Music looped to {video_duration:.1f}s")
            
            final_video = final_video.set_audio(music_clip)
            print("  ✅ Music added")
        except Exception as e:
            print(f"  ⚠️ Could not add music: {e}")
    
    # Export video
    print(f"\n💾 Exporting video to: {args.output}")
    print("   ⏱️ This may take a few minutes...")
    
    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        start_export = time.time()
        
        final_video.write_videofile(
            str(args.output),
            fps=args.fps,
            codec='libx264',
            audio_codec='aac',
            threads=4,
            preset='fast',
            verbose=False,
            logger=None
        )
        
        export_time = time.time() - start_export
        
        # Get file size
        file_size_mb = Path(args.output).stat().st_size / (1024 * 1024)
        
        print("\n" + "="*60)
        print("✅ VIDEO EXPORTED SUCCESSFULLY!")
        print("="*60)
        print(f"📁 File: {args.output}")
        print(f"📊 Size: {file_size_mb:.2f} MB")
        print(f"⏱️ Duration: {video_duration:.1f}s ({video_duration/60:.2f} minutes)")
        print(f"📊 Segments: {len(timeline_clips)}")
        print(f"📝 Captions: {len(caption_overlays)}")
        print(f"⏱️ Export time: {export_time:.2f} seconds")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    """Main entry point"""
    try:
        args = parse_arguments()
        success = generate_video(args)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()