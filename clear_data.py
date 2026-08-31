"""
Clear All Data Script for Face Gallery
WARNING: This will delete all uploaded images, videos, and gallery data!
"""

import os
import shutil
import sys

print("=" * 70)
print("⚠️  WARNING: DATA CLEAR SCRIPT")
print("=" * 70)
print("\nThis script will permanently delete:")
print("  📸 All uploaded images in 'images/' folder")
print("  🎬 All uploaded videos in 'videos/' folder")
print("  📊 All gallery data in 'gallery_data/' folder")
print("  📁 All upload temp files in 'uploads/' folder")
print("\n⚠️  THIS ACTION CANNOT BE UNDONE!")
print("=" * 70)

# Confirm with user
confirm = input("\nType 'YES' to confirm deletion: ")

if confirm != "YES":
    print("\n❌ Deletion cancelled.")
    sys.exit(0)

print("\n🗑️  Starting cleanup...")

# ==================== Directories to clear ====================

directories = [
    ('images', '📸 Images'),
    ('videos', '🎬 Videos'),
    ('gallery_data', '📊 Gallery Data'),
    ('uploads', '📁 Uploads'),
]

for dir_name, label in directories:
    if os.path.exists(dir_name):
        try:
            # Remove all contents but keep the directory
            for item in os.listdir(dir_name):
                item_path = os.path.join(dir_name, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                    print(f"  ✅ Deleted file: {item_path}")
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"  ✅ Deleted folder: {item_path}")
            print(f"  ✅ Cleared {label} folder")
        except Exception as e:
            print(f"  ❌ Error clearing {label}: {e}")
    else:
        os.makedirs(dir_name, exist_ok=True)
        print(f"  ✅ Created empty {label} folder")

# ==================== Clear specific files ====================

# Clear processed.json
processed_file = os.path.join('gallery_data', 'processed.json')
if os.path.exists(processed_file):
    try:
        os.remove(processed_file)
        print(f"  ✅ Deleted: {processed_file}")
    except:
        pass

# Clear gallery_data.json
gallery_file = os.path.join('gallery_data', 'gallery_data.json')
if os.path.exists(gallery_file):
    try:
        os.remove(gallery_file)
        print(f"  ✅ Deleted: {gallery_file}")
    except:
        pass

# Clear summary.txt
summary_file = os.path.join('gallery_data', 'summary.txt')
if os.path.exists(summary_file):
    try:
        os.remove(summary_file)
        print(f"  ✅ Deleted: {summary_file}")
    except:
        pass

# Clear thumbnails folder contents
thumbnails_folder = os.path.join('gallery_data', 'thumbnails')
if os.path.exists(thumbnails_folder):
    try:
        for item in os.listdir(thumbnails_folder):
            item_path = os.path.join(thumbnails_folder, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
        print(f"  ✅ Cleared thumbnails folder")
    except:
        pass

# Clear video_previews folder contents
previews_folder = os.path.join('gallery_data', 'video_previews')
if os.path.exists(previews_folder):
    try:
        for item in os.listdir(previews_folder):
            item_path = os.path.join(previews_folder, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
        print(f"  ✅ Cleared video_previews folder")
    except:
        pass

# ==================== Recreate necessary subdirectories ====================

# Recreate needed subdirectories
subdirs = [
    os.path.join('gallery_data', 'thumbnails'),
    os.path.join('gallery_data', 'video_previews'),
]

for subdir in subdirs:
    os.makedirs(subdir, exist_ok=True)

print("\n" + "=" * 70)
print("✅ CLEANUP COMPLETE!")
print("=" * 70)
print("\n📊 All data has been cleared.")
print("📁 Empty folders have been recreated.")
print("\n💡 You can now restart the app with a fresh database.")
print("=" * 70)