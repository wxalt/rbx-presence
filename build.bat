@echo off
setlocal
cd /d "%~dp0"

rem --- Python launcher (py -3 ou python) ---
set PY=py -3
%PY% --version >nul 2>&1 || set PY=python
%PY% --version >nul 2>&1 || (echo Python 3.10+ introuvable. Installe-le depuis python.org & pause & exit /b 1)

rem --- venv propre : l'exe n'embarque QUE les dependances utiles (leger, peu de RAM) ---
if not exist .venv-build (
    %PY% -m venv .venv-build || (echo Echec creation du venv & pause & exit /b 1)
)
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || (echo Echec installation des dependances & pause & exit /b 1)

rem --- build : un seul .exe, sans console ---
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name RBXPresence ^
  --icon assets\app_icon.ico ^
  --add-data "assets\app_icon.ico;assets" ^
  --add-data "assets\logo_ui.png;assets" ^
  --exclude-module unittest --exclude-module pydoc --exclude-module doctest ^
  --exclude-module distutils --exclude-module setuptools --exclude-module pkg_resources ^
  --exclude-module numpy --exclude-module PIL --exclude-module customtkinter ^
  --exclude-module requests --exclude-module tkinter.test --exclude-module test ^
  app.py || (echo Echec du build & pause & exit /b 1)

echo.
echo OK : dist\RBXPresence.exe
pause
