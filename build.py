#!/usr/bin/env python3
"""
Build script to package the EPUB3 Page List Generator into a Calibre plugin ZIP.

Usage:
    python build.py [--install] [--output NAME]

Options:
    --output NAME  Write the ZIP as NAME instead of epub3_pagelist.zip
                   (for example epub3_pagelist-1.0.7.zip).
    --install    Automatically install/update the plugin in Calibre after building
                 (requires `calibre-customize` in PATH).
"""
import os
import sys
import zipfile
import subprocess
import shutil

PLUGIN_NAME = "epub3_pagelist.zip"

# Items to include in the ZIP bundle
INCLUDES = [
    "__init__.py",
    "config.py",
    "action.py",
    "fetcher.py",
    "utils.py",
    "plugin-import-name-epub3_pagelist.txt",
    "images",
    "core",
]

# Patterns or directory names to exclude
EXCLUDES = {
    "__pycache__",
    ".DS_Store",
    "Thumbs.db",
}


def build_plugin_zip(output_filename=PLUGIN_NAME):
    project_root = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(project_root, output_filename)

    if os.path.exists(output_path):
        os.remove(output_path)

    print(f"📦 Packaging Calibre plugin into '{output_filename}'...")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in INCLUDES:
            item_path = os.path.join(project_root, item)
            if not os.path.exists(item_path):
                print(f"⚠️  Warning: '{item}' not found, skipping.")
                continue

            if os.path.isdir(item_path):
                for root, dirs, files in os.walk(item_path):
                    # Filter out excluded directories in-place
                    dirs[:] = [d for d in dirs if d not in EXCLUDES and not d.startswith('.')]
                    for file in files:
                        if file in EXCLUDES or file.endswith(('.pyc', '.pyo')):
                            continue
                        full_file_path = os.path.join(root, file)
                        arcname = os.path.relpath(full_file_path, project_root)
                        zf.write(full_file_path, arcname)
                        print(f"  + {arcname}")
            else:
                zf.write(item_path, item)
                print(f"  + {item}")

    print(f"✅ Successfully built '{output_filename}' ({os.path.getsize(output_path):,} bytes).\n")
    return output_path


def install_plugin(zip_path):
    calibre_customize = shutil.which("calibre-customize")
    if not calibre_customize:
        print("❌ 'calibre-customize' command not found in PATH.")
        print("   Please install the plugin manually via Calibre GUI:")
        print("   Preferences -> Plugins -> Load plugin from file.")
        return

    print("🔌 Installing plugin into Calibre...")
    try:
        subprocess.run([calibre_customize, "-a", zip_path], check=True)
        print("✅ Plugin installed/updated successfully in Calibre.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install plugin into Calibre: {e}")


def main():
    output = PLUGIN_NAME
    if "--output" in sys.argv:
        output = sys.argv[sys.argv.index("--output") + 1]
    zip_path = build_plugin_zip(output)
    if "--install" in sys.argv:
        install_plugin(zip_path)


if __name__ == "__main__":
    main()

