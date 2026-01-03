import sys
import threading
import math
import os
import subprocess
import platform
import shutil
import certifi

# Fix SSL certificate verification for PyInstaller
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    os.environ['SSL_CERT_FILE'] = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
    os.environ['REQUESTS_CA_BUNDLE'] = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
else:
    # Running as script
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()


from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QComboBox, QLabel, QProgressBar,
    QCheckBox, QFileDialog, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont
from pytubefix import YouTube, Playlist


# Signal emitter for thread-safe UI updates
class DownloadSignals(QObject):
    progress_update = Signal(int, str)
    status_update = Signal(str)
    enable_buttons = Signal(bool, bool, bool)
    resolutions_fetched = Signal(list, dict)
    playlist_progress = Signal(int, int, str)  # current, total, video_title
    log_message = Signal(str)


class YouTubeDownloaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader")
        self.setMinimumSize(900, 550)

        # Signals for thread communication
        self.signals = DownloadSignals()
        self.signals.progress_update.connect(self.update_progress)
        self.signals.status_update.connect(self.update_status)
        self.signals.enable_buttons.connect(self.set_buttons_state)
        self.signals.resolutions_fetched.connect(self.populate_resolutions)
        self.signals.playlist_progress.connect(self.update_playlist_progress)
        self.signals.log_message.connect(self.add_log_message)

        # Storage
        self.available_streams = {}
        self.current_yt = None
        self.current_playlist = None
        self.is_playlist = False
        self.download_dir = os.path.expanduser("~/Downloads")

        # Detect FFmpeg and GPU
        self.ffmpeg_path = self.find_ffmpeg()
        self.ffmpeg_available = self.test_ffmpeg()
        self.gpu_info = self.detect_gpu_encoder() if self.ffmpeg_available else {'name': 'FFmpeg Not Found', 'codec': 'libx264', 'preset': 'medium'}

        self.init_ui()

    def init_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # URL input row
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube URL or Playlist URL")
        self.url_input.setMinimumHeight(35)
        url_layout.addWidget(self.url_input)

        self.fetch_button = QPushButton("Fetch Info")
        self.fetch_button.setMinimumWidth(150)
        self.fetch_button.clicked.connect(self.fetch_resolutions_clicked)
        url_layout.addWidget(self.fetch_button)

        main_layout.addLayout(url_layout)

        # Download directory row
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Save to:")
        dir_layout.addWidget(dir_label)

        self.dir_input = QLineEdit()
        self.dir_input.setText(self.download_dir)
        self.dir_input.setReadOnly(True)
        dir_layout.addWidget(self.dir_input)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.setMinimumWidth(100)
        self.browse_button.clicked.connect(self.browse_directory)
        dir_layout.addWidget(self.browse_button)

        main_layout.addLayout(dir_layout)

        # Show all formats checkbox
        self.show_all_checkbox = QCheckBox("Show all formats (MP4 only - audio included)")
        main_layout.addWidget(self.show_all_checkbox)

        # Resolution selection row
        resolution_layout = QHBoxLayout()
        self.resolution_combo = QComboBox()
        self.resolution_combo.setMinimumHeight(35)
        self.resolution_combo.setEnabled(False)
        resolution_layout.addWidget(self.resolution_combo)

        self.download_button = QPushButton("Download")
        self.download_button.setMinimumWidth(150)
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download_clicked)
        resolution_layout.addWidget(self.download_button)

        main_layout.addLayout(resolution_layout)

        # Playlist progress label
        self.playlist_label = QLabel("")
        self.playlist_label.setVisible(False)
        self.playlist_label.setStyleSheet("color: blue; font-weight: bold;")
        main_layout.addWidget(self.playlist_label)

        # Progress bar and percentage
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("0%")
        self.progress_label.setMinimumWidth(50)
        progress_layout.addWidget(self.progress_label)

        main_layout.addLayout(progress_layout)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        # Log text area
        log_label = QLabel("Download Log:")
        main_layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        self.log_text.setStyleSheet("background-color: #f5f5f5; font-family: monospace; font-size: 9pt;")
        main_layout.addWidget(self.log_text)

        # FFmpeg status
        encoder_icon = "🎮" if self.gpu_info['codec'] != 'libx264' else "💻"
        if self.ffmpeg_available:
            ffmpeg_text = f"✅ FFmpeg ready ({self.ffmpeg_path}) | {encoder_icon} {self.gpu_info['name']}"
            color = "green"
        else:
            ffmpeg_text = f"⚠️ FFmpeg not found - install FFmpeg or: pip install imageio-ffmpeg"
            color = "orange"

        self.ffmpeg_label = QLabel(ffmpeg_text)
        self.ffmpeg_label.setStyleSheet(f"color: {color}; font-size: 10pt;")
        main_layout.addWidget(self.ffmpeg_label)

        # Add stretch to push everything to the top
        main_layout.addStretch()

    def add_log_message(self, message):
        """Add message to log"""
        self.log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def update_playlist_progress(self, current, total, title):
        """Update playlist progress"""
        self.playlist_label.setText(f"Playlist: Downloading {current}/{total} - {title}")
        self.playlist_label.setVisible(True)

    def find_ffmpeg(self):
        """Find FFmpeg - prioritize bundled FFmpeg, then system FFmpeg"""
        # Method 1: Check for bundled FFmpeg (PyInstaller)
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            bundle_dir = sys._MEIPASS
            bundled_ffmpeg = os.path.join(bundle_dir, 'ffmpeg.exe' if platform.system() == 'Windows' else 'ffmpeg')
            if os.path.isfile(bundled_ffmpeg):
                print(f"✅ Found bundled FFmpeg at: {bundled_ffmpeg}")
                return bundled_ffmpeg

        # Method 2: Check if 'ffmpeg' is in system PATH
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            print(f"✅ Found system FFmpeg at: {ffmpeg_path}")
            return ffmpeg_path

        # Method 3: Try common installation paths
        common_paths = []
        if platform.system() == 'Windows':
            common_paths = [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
            ]
        elif platform.system() == 'Darwin':  # macOS
            common_paths = [
                '/usr/local/bin/ffmpeg',
                '/opt/homebrew/bin/ffmpeg',
                '/opt/local/bin/ffmpeg',
            ]
        else:  # Linux
            common_paths = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/snap/bin/ffmpeg',
            ]

        for path in common_paths:
            if os.path.isfile(path):
                print(f"✅ Found system FFmpeg at: {path}")
                return path

        # Method 4: Fall back to imageio-ffmpeg
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            print(f"ℹ️ Using imageio-ffmpeg (no GPU support): {ffmpeg_path}")
            return ffmpeg_path
        except ImportError:
            print("❌ imageio-ffmpeg not installed")

        # Method 5: Return 'ffmpeg' and hope it's in PATH
        print("⚠️ FFmpeg not found, will attempt to use 'ffmpeg' command")
        return 'ffmpeg'

    def test_ffmpeg(self):
        """Test if FFmpeg is working"""
        if not self.ffmpeg_path:
            return False

        try:
            # Use a short timeout and suppress output
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            result = subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=creationflags
            )

            if result.returncode == 0:
                print(f"✅ FFmpeg is working!")
                print(f"   Path: {self.ffmpeg_path}")
                # Print first line of version info
                if result.stdout:
                    first_line = result.stdout.split('\n')[0]
                    print(f"   Version: {first_line}")
                return True
            else:
                print(f"❌ FFmpeg returned error code: {result.returncode}")
                return False

        except FileNotFoundError:
            print(f"❌ FFmpeg not found at: {self.ffmpeg_path}")
            return False
        except subprocess.TimeoutExpired:
            print(f"⚠️ FFmpeg test timed out")
            return False
        except Exception as e:
            print(f"❌ FFmpeg test failed: {e}")
            return False

    def detect_gpu_encoder(self):
        """Detect available GPU encoder"""
        if not self.ffmpeg_available:
            return {'name': 'FFmpeg Not Found', 'codec': 'libx264', 'preset': 'medium'}

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            result = subprocess.run(
                [self.ffmpeg_path, '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=creationflags
            )
            encoders = result.stdout.lower()

            if 'h264_nvenc' in encoders:
                print("🎮 Detected: NVIDIA NVENC GPU encoder")
                return {'name': 'NVIDIA NVENC', 'codec': 'h264_nvenc', 'preset': 'p4'}
            elif 'h264_qsv' in encoders:
                print("🎮 Detected: Intel Quick Sync GPU encoder")
                return {'name': 'Intel Quick Sync', 'codec': 'h264_qsv', 'preset': 'medium'}
            elif 'h264_amf' in encoders:
                print("🎮 Detected: AMD AMF GPU encoder")
                return {'name': 'AMD AMF', 'codec': 'h264_amf', 'preset': 'balanced'}
            elif 'h264_vaapi' in encoders:
                print("🎮 Detected: VAAPI hardware encoder (Intel/AMD)")
                return {'name': 'VAAPI (Hardware)', 'codec': 'h264_vaapi', 'preset': None}
            elif 'h264_videotoolbox' in encoders and platform.system() == 'Darwin':
                print("🎮 Detected: Apple VideoToolbox encoder")
                return {'name': 'Apple VideoToolbox', 'codec': 'h264_videotoolbox', 'preset': None}
            else:
                print("💻 No GPU encoder found, using CPU (libx264)")
                return {'name': 'CPU (Software)', 'codec': 'libx264', 'preset': 'medium'}
        except Exception as e:
            print(f"GPU detection error: {e}")
            return {'name': 'CPU (Software)', 'codec': 'libx264', 'preset': 'medium'}

    def browse_directory(self):
        """Open directory browser"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Download Directory",
            self.download_dir
        )
        if directory:
            self.download_dir = directory
            self.dir_input.setText(directory)

    def update_progress(self, percent, text):
        """Update progress bar and label"""
        self.progress_bar.setValue(percent)
        self.progress_label.setText(text)

    def update_status(self, message):
        """Update status label"""
        self.status_label.setText(message)

    def set_buttons_state(self, fetch_enabled, download_enabled, combo_enabled):
        """Enable/disable buttons"""
        self.fetch_button.setEnabled(fetch_enabled)
        self.download_button.setEnabled(download_enabled)
        self.resolution_combo.setEnabled(combo_enabled)

    def populate_resolutions(self, options, streams):
        """Populate resolution combo box"""
        self.resolution_combo.clear()
        self.available_streams = streams
        for option in options:
            self.resolution_combo.addItem(option)

        if options:
            self.resolution_combo.setCurrentIndex(0)
            self.signals.enable_buttons.emit(True, True, True)

    def on_progress(self, stream, chunk, bytes_remaining):
        """Progress callback for pytube"""
        try:
            total = stream.filesize or 0
            downloaded = total - bytes_remaining
            percent = 0
            if total:
                percent = math.floor(downloaded / total * 100)

            self.signals.progress_update.emit(percent, f"{percent}%")
        except Exception as ex:
            pass

    def fetch_resolutions_clicked(self):
        """Handle fetch button click"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a YouTube URL.")
            return

        self.signals.enable_buttons.emit(False, False, False)
        self.resolution_combo.clear()
        self.playlist_label.setVisible(False)
        self.log_text.clear()
        self.signals.status_update.emit("Fetching information...")
        self.signals.progress_update.emit(0, "0%")

        thread = threading.Thread(target=self.fetch_resolutions, args=(url,), daemon=True)
        thread.start()

    def fetch_resolutions(self, url):
        """Fetch available resolutions (runs in thread)"""
        try:
            # Check if URL is a playlist
            if 'list=' in url or '/playlist' in url:
                self.is_playlist = True
                self.signals.log_message.emit("📋 Detected playlist URL")
                self.signals.status_update.emit("Loading playlist...")

                playlist = Playlist(url)
                self.current_playlist = playlist

                video_count = len(playlist.video_urls)
                self.signals.log_message.emit(f"📋 Found {video_count} videos in playlist: {playlist.title}")
                self.signals.status_update.emit(f"Playlist ready: {video_count} videos")

                # Enhanced playlist options with audio-only
                options = [
                    "--- Video Options ---",
                    "1080p - Best Quality (adaptive)",
                    "720p - High Quality (adaptive)",
                    "480p - Medium Quality (adaptive)",
                    "360p - Low Quality (adaptive)",
                    "Best Available Progressive (video+audio)",
                    "--- Audio Only Options ---",
                    "🎵 Audio - Best Quality (convert to MP3)",
                    "🎵 Audio - High Quality 192k (convert to MP3)",
                    "🎵 Audio - Medium Quality 128k (convert to MP3)",
                    "🎵 Audio - Low Quality 64k (convert to MP3)",
                ]

                self.available_streams = {}
                for opt in options:
                    self.available_streams[opt] = {'type': 'playlist_option', 'option': opt}

                self.signals.resolutions_fetched.emit(options, self.available_streams)
                self.signals.status_update.emit(
                    f"✅ Playlist loaded: {video_count} videos. Select quality and click Download."
                )

            else:
                # Single video
                self.is_playlist = False
                self.current_playlist = None

                yt = YouTube(url, on_progress_callback=self.on_progress)
                self.current_yt = yt

                progressive_streams = yt.streams.filter(progressive=True, file_extension="mp4")
                adaptive_streams_mp4 = yt.streams.filter(adaptive=True, type="video", file_extension="mp4")
                adaptive_streams_webm = yt.streams.filter(adaptive=True, type="video", file_extension="webm")

                adaptive_streams = list(adaptive_streams_mp4) + list(adaptive_streams_webm)

                if not progressive_streams and not adaptive_streams:
                    self.signals.status_update.emit("No suitable streams found.")
                    self.signals.enable_buttons.emit(True, False, False)
                    return

                available_streams = {}
                added_resolutions = set()
                show_duplicates = self.show_all_checkbox.isChecked()

                # Sort adaptive streams
                adaptive_streams.sort(key=lambda s: (
                    -int(s.resolution.replace('p', '')) if s.resolution else 0,
                    0 if 'mp4' in s.mime_type else 1
                ))

                options = []

                # Add adaptive streams
                for stream in adaptive_streams:
                    resolution = stream.resolution
                    if resolution:
                        filesize_mb = stream.filesize / (1024 * 1024) if stream.filesize else 0
                        fps = stream.fps if hasattr(stream, 'fps') else 30
                        file_ext = stream.mime_type.split('/')[-1].split(';')[0]

                        if not show_duplicates and resolution in added_resolutions:
                            continue

                        if show_duplicates:
                            label = f"{resolution} {fps}fps - {filesize_mb:.1f} MB [{file_ext}] (itag: {stream.itag})"
                        else:
                            label = f"{resolution} {fps}fps - {filesize_mb:.1f} MB (requires audio merge)"

                        available_streams[label] = {
                            'type': 'adaptive',
                            'video_stream': stream,
                            'resolution': resolution,
                            'format': file_ext
                        }
                        options.append(label)
                        added_resolutions.add(resolution)

                # Add progressive streams
                for stream in progressive_streams:
                    resolution = stream.resolution
                    if resolution:
                        filesize_mb = stream.filesize / (1024 * 1024) if stream.filesize else 0

                        if not show_duplicates and resolution in added_resolutions:
                            continue

                        if show_duplicates:
                            label = f"{resolution} - {filesize_mb:.1f} MB [mp4] (itag: {stream.itag})"
                        else:
                            label = f"{resolution} - {filesize_mb:.1f} MB ✅ (video + audio)"

                        available_streams[label] = {
                            'type': 'progressive',
                            'stream': stream
                        }
                        options.append(label)
                        added_resolutions.add(resolution)

                # Add audio-only streams
                audio_streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
                if audio_streams:
                    options.append("--- Audio Only ---")
                    for audio_stream in audio_streams[:4]:  # Top 4 audio qualities
                        abr = audio_stream.abr if audio_stream.abr else "Unknown"
                        filesize_mb = audio_stream.filesize / (1024 * 1024) if audio_stream.filesize else 0
                        file_ext = audio_stream.mime_type.split('/')[-1].split(';')[0]

                        label = f"🎵 Audio Only - {abr} - {filesize_mb:.1f} MB [{file_ext}]"
                        available_streams[label] = {
                            'type': 'audio_only',
                            'stream': audio_stream
                        }
                        options.append(label)

                self.signals.resolutions_fetched.emit(options, available_streams)
                self.signals.status_update.emit(
                    f"Found {len(available_streams)} options. ✅ = video+audio, 🎵 = audio only, others need FFmpeg merge."
                )
                self.signals.log_message.emit(f"✅ Video info fetched: {yt.title}")

        except Exception as ex:
            self.signals.status_update.emit(f"Error fetching information: {ex}")
            self.signals.log_message.emit(f"❌ Error: {ex}")
            self.signals.enable_buttons.emit(True, False, False)

    def download_clicked(self):
        """Handle download button click"""
        selected = self.resolution_combo.currentText()

        if not selected:
            QMessageBox.warning(self, "Error", "Please select a resolution.")
            return

        if not self.is_playlist and not self.current_yt:
            QMessageBox.warning(self, "Error", "Please fetch information first.")
            return

        if self.is_playlist and not self.current_playlist:
            QMessageBox.warning(self, "Error", "Please fetch playlist first.")
            return

        self.signals.enable_buttons.emit(False, False, True)
        self.signals.status_update.emit("Preparing download...")
        self.signals.progress_update.emit(0, "0%")

        if self.is_playlist:
            thread = threading.Thread(target=self.download_playlist, args=(selected,), daemon=True)
        else:
            thread = threading.Thread(target=self.do_download, args=(selected,), daemon=True)

        thread.start()

    def sanitize_filename(self, filename):
        """Remove invalid characters from filename"""
        import re
        # Remove invalid characters for filesystem
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace multiple spaces with single space
        filename = re.sub(r'\s+', ' ', filename)
        # Trim spaces and limit length
        filename = filename.strip()[:100]
        return filename if filename else "YouTube_Playlist"

    def download_playlist(self, quality_option):
        """Download entire playlist"""
        try:
            video_urls = self.current_playlist.video_urls
            total_videos = len(video_urls)

            # Determine if audio-only mode
            is_audio_only = "🎵 Audio" in quality_option

            self.signals.log_message.emit(f"\n{'='*50}")
            if is_audio_only:
                self.signals.log_message.emit(f"🎵 Starting playlist AUDIO download: {total_videos} videos")
            else:
                self.signals.log_message.emit(f"📋 Starting playlist download: {total_videos} videos")
            self.signals.log_message.emit(f"{'='*50}\n")

            successful = 0
            failed = 0

            for idx, video_url in enumerate(video_urls, 1):
                try:
                    # Create YouTube object for this video
                    yt = YouTube(video_url, on_progress_callback=self.on_progress)
                    self.current_yt = yt

                    title = yt.title[:50]  # Truncate long titles
                    self.signals.playlist_progress.emit(idx, total_videos, title)
                    self.signals.log_message.emit(f"\n[{idx}/{total_videos}] {'🎵' if is_audio_only else '📹'} {title}")
                    self.signals.status_update.emit(f"Downloading {idx}/{total_videos}: {title}")

                    if is_audio_only:
                        # Download audio only
                        audio_stream = None

                        # Select audio quality based on option
                        if "Best Quality" in quality_option:
                            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                        elif "192k" in quality_option:
                            audio_stream = yt.streams.filter(only_audio=True, abr="192kbps").first()
                            if not audio_stream:
                                audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
                        elif "128k" in quality_option:
                            audio_stream = yt.streams.filter(only_audio=True, abr="128kbps").first()
                            if not audio_stream:
                                streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
                                audio_stream = streams[1] if len(streams) > 1 else streams.first()
                        elif "64k" in quality_option:
                            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').asc().first()
                        else:
                            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()

                        if not audio_stream:
                            self.signals.log_message.emit(f"   ❌ No audio stream found")
                            failed += 1
                            continue

                        audio_file = audio_stream.download(output_path=self.download_dir)

                        # Convert to MP3 if FFmpeg is available
                        if self.ffmpeg_available:
                            base_name = os.path.splitext(audio_file)[0]
                            mp3_file = base_name + '.mp3'

                            if self.convert_to_mp3(audio_file, mp3_file):
                                self.signals.log_message.emit(f"   ✅ Downloaded & converted to MP3")
                            else:
                                self.signals.log_message.emit(f"   ✅ Downloaded audio (conversion failed)")
                        else:
                            self.signals.log_message.emit(f"   ✅ Downloaded audio (no FFmpeg for MP3)")
                        successful += 1

                    else:
                        # Video download logic
                        stream = None
                        stream_type = 'progressive'

                        if 'Progressive' in quality_option:
                            # Best progressive stream
                            stream = yt.streams.filter(progressive=True, file_extension="mp4").order_by('resolution').desc().first()
                            stream_type = 'progressive'
                        else:
                            # Extract resolution from option
                            resolution = quality_option.split('p')[0] + 'p'

                            # Try to get adaptive stream
                            stream = yt.streams.filter(
                                adaptive=True,
                                type="video",
                                resolution=resolution
                            ).first()

                            if not stream:
                                # Fall back to closest resolution
                                stream = yt.streams.filter(adaptive=True, type="video").order_by('resolution').desc().first()

                            stream_type = 'adaptive'

                        if not stream:
                            self.signals.log_message.emit(f"   ❌ No suitable stream found")
                            failed += 1
                            continue

                        if stream_type == 'progressive':
                            video_file = stream.download(output_path=self.download_dir)
                            self.signals.log_message.emit(f"   ✅ Downloaded (progressive)")
                            successful += 1
                        else:
                            # Download video
                            video_file = stream.download(
                                output_path=self.download_dir,
                                filename_prefix=f"video_{idx}_"
                            )

                            # Download audio
                            audio_stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
                            if audio_stream:
                                audio_file = audio_stream.download(
                                    output_path=self.download_dir,
                                    filename_prefix=f"audio_{idx}_"
                                )

                                # Merge
                                self.merge_video_audio_silent(video_file, audio_file, idx)
                                self.signals.log_message.emit(f"   ✅ Downloaded & merged")
                                successful += 1
                            else:
                                self.signals.log_message.emit(f"   ⚠️ Downloaded (no audio available)")
                                successful += 1

                    self.signals.progress_update.emit(0, "0%")

                except Exception as e:
                    self.signals.log_message.emit(f"   ❌ Failed: {str(e)[:100]}")
                    failed += 1
                    continue

            # Summary
            self.signals.log_message.emit(f"\n{'='*50}")
            self.signals.log_message.emit(f"✅ Playlist download complete!")
            self.signals.log_message.emit(f"   Successful: {successful}/{total_videos}")
            if failed > 0:
                self.signals.log_message.emit(f"   Failed: {failed}/{total_videos}")
            self.signals.log_message.emit(f"{'='*50}")

            self.signals.status_update.emit(
                f"✅ Playlist complete: {successful} downloaded, {failed} failed"
            )
            self.signals.progress_update.emit(100, "100%")
            self.playlist_label.setVisible(False)

        except Exception as ex:
            self.signals.log_message.emit(f"❌ Playlist download error: {ex}")
            self.signals.status_update.emit(f"❌ Playlist error: {ex}")
        finally:
            self.signals.enable_buttons.emit(True, True, True)

    def convert_to_mp3_verbose(self, input_file, output_file):
        """Convert audio file to MP3 with verbose logging"""
        if not self.ffmpeg_available:
            return False

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            ffmpeg_cmd = [
                self.ffmpeg_path, '-i', input_file,
                '-vn',  # No video
                '-ar', '44100',  # Sample rate
                '-ac', '2',  # Stereo
                '-b:a', '192k',  # Bitrate
                output_file, '-y', '-hide_banner', '-loglevel', 'error'
            ]

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, creationflags=creationflags)

            if result.returncode == 0 and os.path.exists(output_file):
                # Remove original file
                try:
                    os.remove(input_file)
                except:
                    pass
                return True
            else:
                self.signals.log_message.emit(f"⚠️ MP3 conversion failed: {result.stderr[:100]}")
                return False
        except Exception as e:
            self.signals.log_message.emit(f"⚠️ MP3 conversion error: {str(e)[:50]}")
            return False

    def convert_to_mp3(self, input_file, output_file):
        """Convert audio file to MP3"""
        if not self.ffmpeg_available:
            return False

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            ffmpeg_cmd = [
                self.ffmpeg_path, '-i', input_file,
                '-vn',  # No video
                '-ar', '44100',  # Sample rate
                '-ac', '2',  # Stereo
                '-b:a', '192k',  # Bitrate
                output_file, '-y', '-hide_banner', '-loglevel', 'error'
            ]

            result = subprocess.run(ffmpeg_cmd, capture_output=True, creationflags=creationflags)

            if result.returncode == 0 and os.path.exists(output_file):
                # Remove original file
                try:
                    os.remove(input_file)
                except:
                    pass
                return True
            return False
        except Exception as e:
            self.signals.log_message.emit(f"   ⚠️ MP3 conversion failed: {str(e)[:50]}")
            return False

    def merge_video_audio_silent(self, video_file, audio_file, idx):
        """Merge video and audio without detailed status updates (for playlist)"""
        if not self.ffmpeg_available:
            return

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            base_name = os.path.splitext(os.path.basename(video_file))[0].replace(f"video_{idx}_", "")
            output_file = os.path.join(self.download_dir, f"{base_name}.mp4")

            video_ext = os.path.splitext(video_file)[1].lower()

            if video_ext == '.webm':
                ffmpeg_cmd = [self.ffmpeg_path, '-i', video_file, '-i', audio_file]

                if self.gpu_info['codec'] == 'h264_nvenc':
                    ffmpeg_cmd.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '23', '-rc', 'vbr'])
                elif self.gpu_info['codec'] == 'h264_qsv':
                    ffmpeg_cmd.extend(['-c:v', 'h264_qsv', '-preset', 'medium', '-global_quality', '23'])
                elif self.gpu_info['codec'] == 'h264_amf':
                    ffmpeg_cmd.extend(['-c:v', 'h264_amf', '-quality', 'balanced', '-rc', 'vbr_latency', '-qp_i', '23', '-qp_p', '23'])
                elif self.gpu_info['codec'] == 'h264_videotoolbox':
                    ffmpeg_cmd.extend(['-c:v', 'h264_videotoolbox', '-b:v', '5M'])
                else:
                    ffmpeg_cmd.extend(['-c:v', 'libx264', '-preset', 'medium', '-crf', '23'])

                ffmpeg_cmd.extend(['-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                                 output_file, '-y', '-hide_banner', '-loglevel', 'error'])
            else:
                ffmpeg_cmd = [
                    self.ffmpeg_path, '-i', video_file, '-i', audio_file,
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    output_file, '-y', '-hide_banner', '-loglevel', 'error'
                ]

            subprocess.run(ffmpeg_cmd, capture_output=True, creationflags=creationflags)

            # Clean up temp files
            try:
                os.remove(video_file)
                os.remove(audio_file)
            except:
                pass

        except Exception as e:
            self.signals.log_message.emit(f"   ⚠️ Merge failed: {str(e)[:50]}")

    def do_download(self, selected_resolution):
        """Download selected resolution (runs in thread)"""
        try:
            self.signals.status_update.emit("Starting download...")
            self.signals.progress_update.emit(0, "0%")

            stream_info = self.available_streams.get(selected_resolution)

            if not stream_info:
                self.signals.status_update.emit("Invalid resolution selected.")
                self.signals.enable_buttons.emit(True, True, True)
                return

            if stream_info['type'] == 'progressive':
                # Simple download
                self.signals.status_update.emit("Downloading (video + audio included)...")

                video = stream_info['stream']
                output_file = video.download(output_path=self.download_dir)

                self.signals.status_update.emit(
                    f"✅ Download complete! Saved as: {os.path.basename(output_file)}"
                )
                self.signals.log_message.emit(f"✅ Downloaded: {os.path.basename(output_file)}")
                self.signals.progress_update.emit(100, "100%")

            elif stream_info['type'] == 'audio_only':
                # Audio-only download
                self.signals.status_update.emit("Downloading audio...")

                audio_stream = stream_info['stream']
                audio_file = audio_stream.download(output_path=self.download_dir)

                self.signals.status_update.emit(f"✓ Audio saved: {os.path.basename(audio_file)}")
                self.signals.log_message.emit(f"✓ Audio downloaded: {os.path.basename(audio_file)}")

                # Convert to MP3 if FFmpeg is available
                if self.ffmpeg_available:
                    self.signals.status_update.emit("Converting to MP3...")
                    mp3_file = os.path.splitext(audio_file)[0] + '.mp3'

                    if self.convert_to_mp3_verbose(audio_file, mp3_file):
                        self.signals.status_update.emit(
                            f"✅ Audio download complete! Saved as: {os.path.basename(mp3_file)}"
                        )
                        self.signals.log_message.emit(f"✅ Converted to MP3: {os.path.basename(mp3_file)}")
                    else:
                        self.signals.status_update.emit(
                            f"✅ Audio downloaded! Saved as: {os.path.basename(audio_file)}"
                        )
                        self.signals.log_message.emit(f"✅ Audio saved: {os.path.basename(audio_file)}")
                else:
                    self.signals.status_update.emit(
                        f"✅ Audio downloaded! Saved as: {os.path.basename(audio_file)}"
                    )
                    self.signals.log_message.emit(f"✅ Audio saved (FFmpeg not available for MP3 conversion)")

                self.signals.progress_update.emit(100, "100%")

            else:
                # Download video and audio separately
                self.signals.status_update.emit("Downloading video (no audio yet)...")

                video_stream = stream_info['video_stream']
                video_file = video_stream.download(
                    output_path=self.download_dir,
                    filename_prefix="video_"
                )

                self.signals.status_update.emit(f"✓ Video saved: {os.path.basename(video_file)}")
                self.signals.log_message.emit(f"✓ Video downloaded: {os.path.basename(video_file)}")
                self.signals.status_update.emit("Downloading audio...")
                self.signals.progress_update.emit(0, "0%")

                audio_stream = self.current_yt.streams.filter(only_audio=True).order_by("abr").desc().first()

                if not audio_stream:
                    self.signals.status_update.emit("⚠️ No audio found. Video saved without audio.")
                    self.signals.log_message.emit("⚠️ No audio stream available")
                    final_file = video_file.replace("video_", "NO_AUDIO_")
                    if video_file != final_file:
                        os.rename(video_file, final_file)
                    self.signals.enable_buttons.emit(True, True, True)
                    return

                audio_file = audio_stream.download(
                    output_path=self.download_dir,
                    filename_prefix="audio_"
                )

                self.signals.status_update.emit(f"✓ Audio saved: {os.path.basename(audio_file)}")
                self.signals.log_message.emit(f"✓ Audio downloaded: {os.path.basename(audio_file)}")

                if not os.path.exists(video_file) or not os.path.exists(audio_file):
                    self.signals.status_update.emit("❌ Error: Download files missing!")
                    self.signals.log_message.emit("❌ Error: Download files missing!")
                    self.signals.enable_buttons.emit(True, True, True)
                    return

                # Merge with FFmpeg
                self.merge_video_audio(video_file, audio_file)

        except Exception as ex:
            self.signals.status_update.emit(f"❌ Download error: {ex}")
            self.signals.log_message.emit(f"❌ Error: {ex}")
        finally:
            self.signals.enable_buttons.emit(True, True, True)

    def merge_video_audio(self, video_file, audio_file):
        """Merge video and audio with FFmpeg"""
        if not self.ffmpeg_available:
            self.signals.status_update.emit("❌ FFmpeg not available! Cannot merge audio and video.")
            self.signals.log_message.emit("❌ FFmpeg not available for merging")
            return

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            encoder_name = self.gpu_info['name']
            is_gpu = self.gpu_info['codec'] != 'libx264'

            if is_gpu:
                self.signals.status_update.emit(f"🎮 Merging with {encoder_name} (GPU-accelerated)...")
            else:
                self.signals.status_update.emit("🔄 Merging video + audio with FFmpeg...")

            base_name = os.path.splitext(os.path.basename(video_file))[0].replace("video_", "")
            output_file = os.path.join(self.download_dir, f"{base_name}.mp4")

            video_ext = os.path.splitext(video_file)[1].lower()

            if video_ext == '.webm':
                self.signals.status_update.emit(f"🔄 Converting WebM to MP4 with {encoder_name}...")
                self.signals.log_message.emit(f"🔄 Converting WebM to MP4...")

                ffmpeg_cmd = [self.ffmpeg_path, '-i', video_file, '-i', audio_file]

                # Add GPU-specific encoding parameters
                if self.gpu_info['codec'] == 'h264_nvenc':
                    ffmpeg_cmd.extend([
                        '-c:v', 'h264_nvenc', '-preset', 'p4',
                        '-cq', '23', '-rc', 'vbr',
                    ])
                elif self.gpu_info['codec'] == 'h264_qsv':
                    ffmpeg_cmd.extend([
                        '-c:v', 'h264_qsv', '-preset', 'medium',
                        '-global_quality', '23',
                    ])
                elif self.gpu_info['codec'] == 'h264_amf':
                    ffmpeg_cmd.extend([
                        '-c:v', 'h264_amf', '-quality', 'balanced',
                        '-rc', 'vbr_latency', '-qp_i', '23', '-qp_p', '23',
                    ])
                elif self.gpu_info['codec'] == 'h264_videotoolbox':
                    ffmpeg_cmd.extend([
                        '-c:v', 'h264_videotoolbox', '-b:v', '5M',
                    ])
                else:
                    ffmpeg_cmd.extend([
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                    ])

                ffmpeg_cmd.extend([
                    '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart',
                    output_file, '-y', '-hide_banner', '-loglevel', 'error'
                ])
            else:
                # MP4 - just copy
                ffmpeg_cmd = [
                    self.ffmpeg_path, '-i', video_file, '-i', audio_file,
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    output_file, '-y', '-hide_banner', '-loglevel', 'error'
                ]

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, creationflags=creationflags)

            if result.returncode == 0 and os.path.exists(output_file):
                if os.path.getsize(output_file) > 1000:
                    # Clean up temp files
                    try:
                        os.remove(video_file)
                        os.remove(audio_file)
                    except:
                        pass

                    encoder_emoji = "🎮" if is_gpu else "✅"
                    status = f"{encoder_emoji} Download complete! Saved as: {os.path.basename(output_file)}"
                    if is_gpu:
                        status += f" (Encoded with {encoder_name})"
                    self.signals.status_update.emit(status)
                    self.signals.log_message.emit(f"✅ Merged and saved: {os.path.basename(output_file)}")
                    self.signals.progress_update.emit(100, "100%")
                else:
                    self.signals.status_update.emit("❌ Output file is empty. Check FFmpeg.")
                    self.signals.log_message.emit("❌ Output file is empty")
            else:
                error = result.stderr[:200] if result.stderr else "Unknown error"
                self.signals.status_update.emit(f"❌ FFmpeg failed: {error}")
                self.signals.log_message.emit(f"❌ FFmpeg failed: {error}")
                print(f"FFmpeg error: {result.stderr}")

        except FileNotFoundError:
            self.signals.status_update.emit("❌ FFmpeg not found! Install: pip install imageio-ffmpeg")
            self.signals.log_message.emit("❌ FFmpeg not found")
        except Exception as e:
            self.signals.status_update.emit(f"❌ Merge error: {str(e)}")
            self.signals.log_message.emit(f"❌ Merge error: {str(e)}")
            print(f"Error details: {e}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern cross-platform style

    window = YouTubeDownloaderWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
