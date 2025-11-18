# YouTube Downloader

A modern, cross-platform YouTube video downloader with GPU-accelerated encoding support. Built with PySide6 and pytubefix.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11+-brightgreen)

## ✨ Features

- 🎬 Download YouTube videos in multiple resolutions (up to 4K/8K)
- 🎮 **GPU-accelerated encoding** (NVIDIA NVENC, Intel QSV, AMD AMF, Apple VideoToolbox)
- 📁 **Custom download directory** selection
- 🎵 Automatic audio merging for high-quality streams
- 🖥️ Native cross-platform GUI (Windows, macOS, Linux)
- ⚡ Fast WebM to MP4 conversion
- 📊 Real-time download progress tracking
- 🎯 Progressive and adaptive stream support

## 📥 Download

Download the latest release for your platform:

**[⬇️ Download Latest Release](https://github.com//rahulbabu7/YT_downloader/releases/latest)**

| Platform | File | Notes |
|----------|------|-------|
| 🪟 Windows | `YouTubeDownloader.exe` | Portable executable |
| 🍎 macOS | `YouTubeDownloader.dmg` | Drag to Applications |
| 🐧 Linux | `YouTubeDownloader` | Make executable with `chmod +x` |

## 📋 Requirements

### FFmpeg Installation (Required)

The app requires FFmpeg for merging video and audio streams. Install it separately:

#### Windows
```bash
# Using winget (recommended)
winget install ffmpeg

# Or download from https://ffmpeg.org/download.html
```

#### macOS
```bash
# Using Homebrew
brew install ffmpeg
```

#### Linux
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Fedora
sudo dnf install ffmpeg

# Arch
sudo pacman -S ffmpeg
```

### GPU Encoding Support

For GPU-accelerated encoding, ensure you have:
- **NVIDIA**: Latest GPU drivers (NVENC support)
- **Intel**: Intel Media SDK / Quick Sync Video
- **AMD**: AMD AMF drivers
- **Apple**: macOS 10.13+ (VideoToolbox built-in)

The app automatically detects and uses available GPU encoders.

## 🚀 Usage

1. **Launch the application**
2. **Paste YouTube URL** in the input field
3. **Click "Fetch Resolutions"** to load available quality options
4. **Choose download directory** (optional - defaults to ~/Downloads)
5. **Select desired resolution** from dropdown
6. **Click "Download"** and wait for completion

### Resolution Guide

- ✅ **Progressive streams**: Video + audio already merged (fast)
- 🔄 **Adaptive streams**: Higher quality, requires FFmpeg merging
- 🎮 **GPU icon**: Video encoded with GPU acceleration

## 🛠️ Building from Source

### Prerequisites

```bash
# Clone the repository
git clone https://github.com//rahulbabu7/YT_downloader.git
cd YT_downloader

# Install dependencies
pip install PySide6 pytubefix pyinstaller
```

### Run from Source

```bash
python main.py
```

### Build Executable

#### Windows
```bash
pyinstaller YouTubeDownloader_Windows.spec
# Output: dist/YouTubeDownloader.exe
```

#### macOS
```bash
pyinstaller YouTubeDownloader_macOS.spec
# Output: dist/YouTubeDownloader.app

# Create DMG (optional)
hdiutil create -volname "YouTube Downloader" -srcfolder dist/YouTubeDownloader.app -ov -format UDZO YouTubeDownloader.dmg
```

#### Linux
```bash
pyinstaller YouTubeDownloader_Linux.spec
# Output: dist/YouTubeDownloader
chmod +x dist/YouTubeDownloader
```

## 🏗️ Project Structure

```
.
├── main.py                          # Main application file
├── YouTubeDownloader_Windows.spec   # PyInstaller spec for Windows
├── YouTubeDownloader_macOS.spec     # PyInstaller spec for macOS
├── YouTubeDownloader_Linux.spec     # PyInstaller spec for Linux
├── .github/
│   └── workflows/
│       └── build.yml                # CI/CD pipeline
└── README.md
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🐛 Known Issues

- Some videos may not be available due to YouTube restrictions
- Age-restricted videos require authentication (not yet supported)
- Very long videos (>2 hours) may take significant time to process

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This tool is for personal use only. Please respect YouTube's Terms of Service and copyright laws. Do not use this tool to download copyrighted content without permission.

## 🙏 Acknowledgments

- [pytubefix](https://github.com/JuanBindez/pytubefix) - YouTube downloading library
- [PySide6](https://wiki.qt.io/Qt_for_Python) - Qt for Python
- [FFmpeg](https://ffmpeg.org/) - Video processing

## 📧 Support

If you encounter any issues or have questions:
- 🐛 [Report a bug](https://github.com/rahulbabu7/YT_downloader/issues)
- 💡 [Request a feature](https://github.com//rahulbabu7/YT_downloader/issues)
- 📖 [View documentation](https://github.com//rahulbabu7/YT_downloader/wiki)

---

**Made with ❤️ by Rahul Babu**

⭐ Star this repo if you find it useful!