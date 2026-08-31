# E:\00000\Rahstaa\My_gallery_2\routes\__init__.py
"""
Routes package initialization
"""

from routes.gallery_routes import gallery_bp
from routes.template_routes import template_bp
from routes.video_routes import video_bp

__all__ = ['gallery_bp', 'template_bp', 'video_bp']