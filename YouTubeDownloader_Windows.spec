# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['youtube_downloader.py'],
    pathex=[],
    binaries=[('ffmpeg_bin/ffmpeg.exe', '.')],
    datas=[],
    hiddenimports=['pytubefix', 'flet'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YouTubeDownloader',
    debug=False,
    strip=False,
    upx=True,
    console=False,
)