"""Shared PyInstaller settings, imported by the platform .spec files."""
import os
import sys

import certifi
import nodejs_wheel
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

IS_WINDOWS = sys.platform == 'win32'
HERE = os.path.dirname(os.path.abspath(__file__))

# pytubefix >= 11 runs JavaScript (signature solving + poToken/botGuard) with
# the node binary shipped by nodejs-wheel-binaries. Both the .js files and the
# node binary must be bundled or YouTube requests fail in the frozen app.
_node_root = os.path.dirname(nodejs_wheel.__file__)
if IS_WINDOWS:
    _node_bin = (os.path.join(_node_root, 'node.exe'), 'nodejs_wheel')
else:
    _node_bin = (os.path.join(_node_root, 'bin', 'node'), 'nodejs_wheel/bin')

binaries = [_node_bin]

# FFmpeg: bundled automatically if CI (or you) placed it in ffmpeg_bundle/
_ffmpeg = os.path.join(HERE, 'ffmpeg_bundle', 'ffmpeg.exe' if IS_WINDOWS else 'ffmpeg')
if os.path.isfile(_ffmpeg):
    binaries.append((_ffmpeg, '.'))
    print(f'[spec] bundling FFmpeg: {_ffmpeg}')
else:
    print('[spec] ffmpeg_bundle/ not found - building without bundled FFmpeg')

datas = [(certifi.where(), 'certifi')] + collect_data_files('pytubefix')

hiddenimports = (
    ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'certifi', 'nodejs_wheel.executable']
    + collect_submodules('pytubefix')
)

# UPX-compressing node/ffmpeg can corrupt them; never compress these.
upx_exclude = ['node', 'node.exe', 'ffmpeg', 'ffmpeg.exe']
