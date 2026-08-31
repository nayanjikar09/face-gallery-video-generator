@echo off
echo ========================================
echo Setting up Virtual Environment
echo ========================================

cd /d E:\00000\Rahstaa\My_gallery_2

echo.
echo Step 1: Deleting old virtual environment...
if exist venv (
    rmdir /s venv
    echo Old venv deleted.
) else (
    echo No venv found in current location.
)

echo.
echo Step 2: Creating new virtual environment...
python -m venv venv
echo Virtual environment created.

echo.
echo Step 3: Activating virtual environment...
call venv\Scripts\activate

echo.
echo Step 4: Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Step 5: Installing dependencies...
pip install moviepy opencv-python pillow numpy flask flask-cors

echo.
echo Step 6: Verifying installation...
python -c "import moviepy; print('[OK] moviepy installed')"
python -c "import cv2; print('[OK] opencv installed')"
python -c "import PIL; print('[OK] pillow installed')"
python -c "import numpy; print('[OK] numpy installed')"

echo.
echo ========================================
echo Setup complete! 
echo Virtual environment is at: E:\00000\Rahstaa\My_gallery_2\venv
echo ========================================
echo.
echo To start the app:
echo   cd E:\00000\Rahstaa\My_gallery_2
echo   venv\Scripts\activate
echo   python app.py
echo.

pause