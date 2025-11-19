import sys
import threading
import math
import os
import subprocess
import platform
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
    QCheckBox, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont
from pytubefix import YouTube


# Signal emitter for thread-safe UI updates
class DownloadSignals(QObject):
    progress_update = Signal(int, str)
    status_update = Signal(str)
    enable_buttons = Signal(bool, bool, bool)
    resolutions_fetched = Signal(list, dict)


class YouTubeDownloaderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader")
        self.setMinimumSize(800, 400)
        
        # Signals for thread communication
        self.signals = DownloadSignals()
        self.signals.progress_update.connect(self.update_progress)
        self.signals.status_update.connect(self.update_status)
        self.signals.enable_buttons.connect(self.set_buttons_state)
        self.signals.resolutions_fetched.connect(self.populate_resolutions)
        
        # Storage
        self.available_streams = {}
        self.current_yt = None
        self.download_dir = os.path.expanduser("~/Downloads")
        
        # Detect FFmpeg and GPU
        self.ffmpeg_path = self.find_ffmpeg()
        self.gpu_info = self.detect_gpu_encoder()
        self.ffmpeg_available = self.test_ffmpeg()
        
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
        self.url_input.setPlaceholderText("Enter YouTube URL")
        self.url_input.setMinimumHeight(35)
        url_layout.addWidget(self.url_input)
        
        self.fetch_button = QPushButton("Fetch Resolutions")
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
        
        # FFmpeg status
        encoder_icon = "🎮" if self.gpu_info['codec'] != 'libx264' else "💻"
        if self.ffmpeg_available:
            ffmpeg_text = f"✅ FFmpeg ready | {encoder_icon} {self.gpu_info['name']}"
            color = "green"
        else:
            ffmpeg_text = "⚠️ FFmpeg not found - install: pip install imageio-ffmpeg"
            color = "orange"
        
        self.ffmpeg_label = QLabel(ffmpeg_text)
        self.ffmpeg_label.setStyleSheet(f"color: {color}; font-size: 10pt;")
        main_layout.addWidget(self.ffmpeg_label)
        
        # Add stretch to push everything to the top
        main_layout.addStretch()
    
    def find_ffmpeg(self):
        """Find FFmpeg with GPU support"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("Using system FFmpeg (may have GPU support)")
                return 'ffmpeg'
        except:
            pass
        
        try:
            import imageio_ffmpeg
            print("Using imageio-ffmpeg (no GPU support)")
            return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass
        
        return 'ffmpeg'
    
    def detect_gpu_encoder(self):
        """Detect available GPU encoder"""
        try:
            result = subprocess.run([self.ffmpeg_path, '-hide_banner', '-encoders'], 
                                   capture_output=True, text=True, timeout=5)
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
    
    def test_ffmpeg(self):
        """Test if FFmpeg is working"""
        try:
            result = subprocess.run([self.ffmpeg_path, '-version'], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ FFmpeg found at: {self.ffmpeg_path}")
                print(f"   Encoder: {self.gpu_info['name']} ({self.gpu_info['codec']})")
                return True
            return False
        except Exception as e:
            print(f"❌ FFmpeg not working: {e}")
            return False
    
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
            self.signals.status_update.emit(f"Downloading... {percent}%")
        except Exception as ex:
            self.signals.status_update.emit(f"Progress update error: {ex}")
    
    def fetch_resolutions_clicked(self):
        """Handle fetch button click"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a YouTube URL.")
            return
        
        self.signals.enable_buttons.emit(False, False, False)
        self.resolution_combo.clear()
        self.signals.status_update.emit("Fetching video information...")
        self.signals.progress_update.emit(0, "0%")
        
        thread = threading.Thread(target=self.fetch_resolutions, args=(url,), daemon=True)
        thread.start()
    
    def fetch_resolutions(self, url):
        """Fetch available resolutions (runs in thread)"""
        try:
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
            
            self.signals.resolutions_fetched.emit(options, available_streams)
            self.signals.status_update.emit(
                f"Found {len(available_streams)} resolutions. Green ✅ = audio included, others need FFmpeg."
            )
            
        except Exception as ex:
            self.signals.status_update.emit(f"Error fetching resolutions: {ex}")
            self.signals.enable_buttons.emit(True, False, False)
    
    def download_clicked(self):
        """Handle download button click"""
        selected = self.resolution_combo.currentText()
        
        if not selected:
            QMessageBox.warning(self, "Error", "Please select a resolution.")
            return
        
        if not self.current_yt:
            QMessageBox.warning(self, "Error", "Please fetch resolutions first.")
            return
        
        self.signals.enable_buttons.emit(False, False, True)
        self.signals.status_update.emit("Preparing download...")
        self.signals.progress_update.emit(0, "0%")
        
        thread = threading.Thread(target=self.do_download, args=(selected,), daemon=True)
        thread.start()
    
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
                self.signals.status_update.emit("Downloading audio...")
                self.signals.progress_update.emit(0, "0%")
                
                audio_stream = self.current_yt.streams.filter(only_audio=True).order_by("abr").desc().first()
                
                if not audio_stream:
                    self.signals.status_update.emit("⚠️ No audio found. Video saved without audio.")
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
                
                if not os.path.exists(video_file) or not os.path.exists(audio_file):
                    self.signals.status_update.emit("❌ Error: Download files missing!")
                    self.signals.enable_buttons.emit(True, True, True)
                    return
                
                # Merge with FFmpeg
                self.merge_video_audio(video_file, audio_file)
                
        except Exception as ex:
            self.signals.status_update.emit(f"❌ Download error: {ex}")
        finally:
            self.signals.enable_buttons.emit(True, True, True)
    
    def merge_video_audio(self, video_file, audio_file):
        """Merge video and audio with FFmpeg"""
        try:
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
            
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
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
                    self.signals.progress_update.emit(100, "100%")
                else:
                    self.signals.status_update.emit("❌ Output file is empty. Check FFmpeg.")
            else:
                error = result.stderr[:200] if result.stderr else "Unknown error"
                self.signals.status_update.emit(f"❌ FFmpeg failed: {error}")
                print(f"FFmpeg error: {result.stderr}")
                
        except FileNotFoundError:
            self.signals.status_update.emit("❌ FFmpeg not found! Install: pip install imageio-ffmpeg")
        except Exception as e:
            self.signals.status_update.emit(f"❌ Merge error: {str(e)}")
            print(f"Error details: {e}")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern cross-platform style
    
    window = YouTubeDownloaderWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()