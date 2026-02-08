import PyInstaller.__main__
import os
import shutil

# Define paths
base_path = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(base_path, "src")
templates_path = os.path.join(src_path, "web", "templates")
static_path = os.path.join(src_path, "web", "static")

# Ensure paths exist
if not os.path.exists(templates_path):
    print(f"Error: {templates_path} not found")
    exit(1)

# PyInstaller arguments
args = [
    "main.py",
    "--name=StaggsHecticTrader",
    "--onefile",
    "--noconsole",  # Hide console on Windows (use --console for debug)
    # Add data files (Source;Dest)
    # On Windows separator is ;, on Linux :
    f"--add-data={templates_path}{os.pathsep}src/web/templates",
    f"--add-data={static_path}{os.pathsep}src/web/static",
    f"--add-data=app_icon.png{os.pathsep}.",  # Add icon to root of bundle for pywebview

    "--icon=app_icon.ico",

    # Collect all google.genai data and modules
    "--collect-all=google.genai",

    # Hidden imports often missed by analysis
    "--hidden-import=uvicorn.logging",
    "--hidden-import=uvicorn.loops",
    "--hidden-import=uvicorn.loops.auto",
    "--hidden-import=uvicorn.protocols",
    "--hidden-import=uvicorn.protocols.http",
    "--hidden-import=uvicorn.protocols.http.auto",
    "--hidden-import=uvicorn.protocols.websockets",
    "--hidden-import=uvicorn.protocols.websockets.auto",
    "--hidden-import=uvicorn.lifespan.on",
    "--hidden-import=sqlalchemy.sql.default_comparator",
    "--hidden-import=sklearn.utils._typedefs",
    "--hidden-import=sklearn.neighbors._partition_nodes",
    "--hidden-import=sklearn.tree._utils",
    "--hidden-import=scipy.special.cython_special",
    "--hidden-import=engineio.async_drivers.threading",
    "--hidden-import=passlib.handlers.bcrypt",
    "--hidden-import=bcrypt",
    "--hidden-import=uvicorn.logging",
    "--hidden-import=pystray.backends.win32",
    "--hidden-import=pystray.backends.xorg",
    "--hidden-import=pystray.backends.gtk",
    "--hidden-import=pyarrow",
    "--hidden-import=yfinance",  # Ensure yfinance is included if available

    "--clean",
]

print("Building executable...")
PyInstaller.__main__.run(args)
print("Build complete. Executable is in the 'dist' folder.")
