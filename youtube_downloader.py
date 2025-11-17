import threading
import math
import flet as ft
from flet import ControlEvent, TextField, Dropdown
from pytubefix import YouTube
import os
import subprocess
import platform

# Prefer system FFmpeg (has GPU support) over imageio-ffmpeg (static build without GPU)
def find_ffmpeg():
    """Find FFmpeg with GPU support"""
    # First try system FFmpeg (most likely to have GPU encoders)
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("Using system FFmpeg (may have GPU support)")
            return 'ffmpeg'
    except:
        pass
    
    # Fallback to imageio-ffmpeg (no GPU support, but guaranteed to work)
    try:
        import imageio_ffmpeg
        print("Using imageio-ffmpeg (no GPU support)")
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    
    # Last resort
    return 'ffmpeg'

FFMPEG_PATH = find_ffmpeg()

def detect_gpu_encoder():
    """Detect available GPU encoder and return appropriate codec settings"""
    try:
        # Check for available encoders
        result = subprocess.run([FFMPEG_PATH, '-hide_banner', '-encoders'], 
                               capture_output=True, text=True, timeout=5)
        encoders = result.stdout.lower()  # Convert to lowercase for reliable matching
        
        # Priority order: h264_nvenc (NVIDIA) > h264_qsv (Intel) > h264_amf (AMD) > h264_vaapi (Linux) > h264_videotoolbox (Apple)
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

def main(page: ft.Page):
    page.title = "YouTube Downloader"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.theme_mode = "dark"
    
    # Detect GPU encoder
    gpu_info = detect_gpu_encoder()
    
    # Test FFmpeg on startup
    def test_ffmpeg():
        try:
            result = subprocess.run([FFMPEG_PATH, '-version'], 
                                   capture_output=True, 
                                   text=True, 
                                   timeout=5)
            if result.returncode == 0:
                print(f"✅ FFmpeg found at: {FFMPEG_PATH}")
                # print(f"   Version: {result.stdout.split('\\n')[0]}")
                print(f"   Encoder: {gpu_info['name']} ({gpu_info['codec']})")
                return True
            else:
                print(f"❌ FFmpeg test failed")
                return False
        except Exception as e:
            print(f"❌ FFmpeg not working: {e}")
            return False
    
    # Run test
    ffmpeg_available = test_ffmpeg()

    text_field: TextField = TextField(
        value="",
        text_align=ft.TextAlign.LEFT,
        width=500,
        hint_text="Enter YouTube URL"
    )

    # Dropdown for resolution selection
    resolution_dropdown: Dropdown = Dropdown(
        width=350,
        label="Select Resolution",
        hint_text="Fetch resolutions first",
        disabled=True
    )

    # Checkbox to show all formats
    show_all_formats = ft.Checkbox(
        label="Show all formats (MP4 only - audio included)",
        value=False
    )

    status = ft.Text("")
    progress_text = ft.Text("")
    progress_bar = ft.ProgressBar(width=300)
    
    # Show FFmpeg and GPU status
    encoder_icon = "🎮" if gpu_info['codec'] != 'libx264' else "💻"
    ffmpeg_status = ft.Text(
        f"✅ FFmpeg ready | {encoder_icon} {gpu_info['name']}" if ffmpeg_available 
        else "⚠️ FFmpeg not found - install: pip install imageio-ffmpeg",
        size=10,
        color="green" if ffmpeg_available else "orange"
    )

    # Store available streams
    available_streams = {}
    current_yt = None

    # Buttons
    fetch_button = ft.ElevatedButton("Fetch Resolutions", disabled=False)
    download_button = ft.ElevatedButton("Download", disabled=True)

    # Progress callback
    def on_progress(stream, chunk, bytes_remaining):
        try:
            total = stream.filesize or 0
            downloaded = total - bytes_remaining
            percent = 0
            if total:
                percent = math.floor(downloaded / total * 100)
            status.value = f"Downloading... {percent}%"
            progress_text.value = f"{percent}%"
            progress_bar.value = percent / 100.0
            page.update()
        except Exception as ex:
            status.value = f"Progress update error: {ex}"
            page.update()

    # Fetch available resolutions
    def fetch_resolutions(url: str):
        nonlocal current_yt
        try:
            status.value = "Fetching video information..."
            progress_bar.value = 0
            progress_text.value = ""
            page.update()

            yt = YouTube(url, on_progress_callback=on_progress)
            current_yt = yt

            # Get all video streams (progressive and adaptive)
            progressive_streams = yt.streams.filter(progressive=True, file_extension="mp4")
            adaptive_streams_mp4 = yt.streams.filter(adaptive=True, type="video", file_extension="mp4")
            adaptive_streams_webm = yt.streams.filter(adaptive=True, type="video", file_extension="webm")

            # Combine all adaptive streams
            adaptive_streams = list(adaptive_streams_mp4) + list(adaptive_streams_webm)

            if not progressive_streams and not adaptive_streams:
                status.value = "No suitable streams found."
                fetch_button.disabled = False
                page.update()
                return

            # Clear previous data
            available_streams.clear()
            resolution_dropdown.options.clear()

            # Track which resolutions we've added
            added_resolutions = set()
            show_duplicates = show_all_formats.value

            # Sort by resolution (highest first) and prefer MP4
            adaptive_streams.sort(key=lambda s: (
                -int(s.resolution.replace('p', '')) if s.resolution else 0,
                0 if 'mp4' in s.mime_type else 1
            ))

            # Add adaptive (high quality) streams
            for stream in adaptive_streams:
                resolution = stream.resolution
                if resolution:
                    filesize_mb = stream.filesize / (1024 * 1024) if stream.filesize else 0
                    fps = stream.fps if hasattr(stream, 'fps') else 30
                    file_ext = stream.mime_type.split('/')[-1].split(';')[0]

                    # Skip duplicates unless showing all
                    if not show_duplicates and resolution in added_resolutions:
                        continue

                    # Create label
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
                    resolution_dropdown.options.append(ft.dropdown.Option(label))
                    added_resolutions.add(resolution)

            # Add progressive streams (video+audio already merged)
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
                    resolution_dropdown.options.append(ft.dropdown.Option(label))
                    added_resolutions.add(resolution)

            # Enable dropdown and download button
            resolution_dropdown.disabled = False
            resolution_dropdown.value = resolution_dropdown.options[0].key if resolution_dropdown.options else None
            download_button.disabled = False

            status.value = f"Found {len(available_streams)} resolutions. Green ✅ = audio included, others need FFmpeg."

        except Exception as ex:
            status.value = f"Error fetching resolutions: {ex}"
            resolution_dropdown.disabled = True
            download_button.disabled = True
        finally:
            fetch_button.disabled = False
            page.update()

    # Download selected resolution
    def do_download(selected_resolution: str):
        nonlocal current_yt
        try:
            status.value = "Starting download..."
            progress_bar.value = 0
            progress_text.value = ""
            page.update()

            stream_info = available_streams.get(selected_resolution)

            if not stream_info:
                status.value = "Invalid resolution selected."
                download_button.disabled = False
                page.update()
                return

            if stream_info['type'] == 'progressive':
                # Simple download for progressive streams (already has audio)
                status.value = "Downloading (video + audio included)..."
                page.update()

                video = stream_info['stream']
                output_file = video.download()

                status.value = f"✅ Download complete! Saved as: {os.path.basename(output_file)}"
                progress_text.value = "100%"
                progress_bar.value = 1.0

            else:
                # Download video and audio separately for high-res
                status.value = "Downloading video (no audio yet)..."
                page.update()

                video_stream = stream_info['video_stream']
                video_file = video_stream.download(filename_prefix="video_")
                
                status.value = f"✓ Video saved: {os.path.basename(video_file)}"
                page.update()

                status.value = "Downloading audio..."
                progress_bar.value = 0
                page.update()

                # Get best audio stream
                audio_stream = current_yt.streams.filter(only_audio=True).order_by("abr").desc().first()

                if not audio_stream:
                    status.value = "⚠️ No audio found. Video saved without audio."
                    final_file = video_file.replace("video_", "NO_AUDIO_")
                    if video_file != final_file:
                        os.rename(video_file, final_file)
                    download_button.disabled = False
                    page.update()
                    return

                audio_file = audio_stream.download(filename_prefix="audio_")
                status.value = f"✓ Audio saved: {os.path.basename(audio_file)}"
                page.update()

                # Verify files exist
                if not os.path.exists(video_file) or not os.path.exists(audio_file):
                    status.value = "❌ Error: Download files missing!"
                    download_button.disabled = False
                    page.update()
                    return

                # Merge with FFmpeg (GPU-accelerated if available)
                try:
                    encoder_name = gpu_info['name']
                    is_gpu = gpu_info['codec'] != 'libx264'
                    
                    if is_gpu:
                        status.value = f"🎮 Merging with {encoder_name} (GPU-accelerated)..."
                    else:
                        status.value = "🔄 Merging video + audio with FFmpeg..."
                    page.update()

                    # Always output as MP4
                    base_name = os.path.splitext(os.path.basename(video_file))[0].replace("video_", "")
                    output_file = os.path.join(os.path.dirname(video_file), f"{base_name}.mp4")

                    # Check if video is WebM (needs re-encoding)
                    video_ext = os.path.splitext(video_file)[1].lower()
                    
                    if video_ext == '.webm':
                        status.value = f"🔄 Converting WebM to MP4 with {encoder_name}..."
                        page.update()
                        
                        # Build FFmpeg command with GPU encoder
                        ffmpeg_cmd = [FFMPEG_PATH, '-i', video_file, '-i', audio_file]
                        
                        # Add GPU-specific encoding parameters
                        if gpu_info['codec'] == 'h264_nvenc':
                            # NVIDIA NVENC
                            ffmpeg_cmd.extend([
                                '-c:v', 'h264_nvenc',
                                '-preset', 'p4',  # Balanced preset
                                '-cq', '23',      # Quality level (lower = better)
                                '-rc', 'vbr',     # Variable bitrate
                            ])
                        elif gpu_info['codec'] == 'h264_qsv':
                            # Intel Quick Sync
                            ffmpeg_cmd.extend([
                                '-c:v', 'h264_qsv',
                                '-preset', 'medium',
                                '-global_quality', '23',
                            ])
                        elif gpu_info['codec'] == 'h264_amf':
                            # AMD AMF
                            ffmpeg_cmd.extend([
                                '-c:v', 'h264_amf',
                                '-quality', 'balanced',
                                '-rc', 'vbr_latency',
                                '-qp_i', '23',
                                '-qp_p', '23',
                            ])
                        elif gpu_info['codec'] == 'h264_videotoolbox':
                            # Apple VideoToolbox
                            ffmpeg_cmd.extend([
                                '-c:v', 'h264_videotoolbox',
                                '-b:v', '5M',
                            ])
                        else:
                            # CPU fallback
                            ffmpeg_cmd.extend([
                                '-c:v', 'libx264',
                                '-preset', 'medium',
                                '-crf', '23',
                            ])
                        
                        # Add audio and output settings
                        ffmpeg_cmd.extend([
                            '-c:a', 'aac', '-b:a', '192k',
                            '-movflags', '+faststart',
                            output_file, '-y', '-hide_banner', '-loglevel', 'error'
                        ])
                    else:
                        # MP4 video - just copy (fast, no GPU needed)
                        ffmpeg_cmd = [
                            FFMPEG_PATH, '-i', video_file, '-i', audio_file,
                            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                            output_file, '-y', '-hide_banner', '-loglevel', 'error'
                        ]

                    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

                    if result.returncode == 0 and os.path.exists(output_file):
                        # Verify file has content
                        if os.path.getsize(output_file) > 1000:
                            # Success - clean up temp files
                            try:
                                os.remove(video_file)
                                os.remove(audio_file)
                            except:
                                pass
                            
                            encoder_emoji = "🎮" if is_gpu else "✅"
                            status.value = f"{encoder_emoji} Download complete! Saved as: {os.path.basename(output_file)}"
                            if is_gpu:
                                status.value += f" (Encoded with {encoder_name})"
                            progress_text.value = "100%"
                            progress_bar.value = 1.0
                        else:
                            status.value = "❌ Output file is empty. Check FFmpeg."
                    else:
                        error = result.stderr[:200] if result.stderr else "Unknown error"
                        status.value = f"❌ FFmpeg failed: {error}"
                        print(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
                        print(f"FFmpeg error: {result.stderr}")

                except FileNotFoundError:
                    status.value = "❌ FFmpeg not found! Install: pip install imageio-ffmpeg"
                    status.value += f"\nTemp files kept: {os.path.basename(video_file)}, {os.path.basename(audio_file)}"
                except Exception as e:
                    status.value = f"❌ Merge error: {str(e)}"
                    print(f"Error details: {e}")

        except Exception as ex:
            status.value = f"❌ Download error: {ex}"
        finally:
            download_button.disabled = False
            fetch_button.disabled = False
            page.update()

    # Fetch button click handler
    def fetch_clicked(e: ControlEvent):
        url = text_field.value.strip()
        if not url:
            status.value = "Please enter a YouTube URL."
            page.update()
            return

        fetch_button.disabled = True
        download_button.disabled = True
        resolution_dropdown.disabled = True
        resolution_dropdown.options.clear()
        page.update()

        t = threading.Thread(target=fetch_resolutions, args=(url,), daemon=True)
        t.start()

    # Download button click handler
    def download_clicked(e: ControlEvent):
        selected = resolution_dropdown.value

        if not selected:
            status.value = "Please select a resolution."
            page.update()
            return

        if not current_yt:
            status.value = "Please fetch resolutions first."
            page.update()
            return

        download_button.disabled = True
        fetch_button.disabled = True
        status.value = "Preparing download..."
        progress_bar.value = 0
        progress_text.value = ""
        page.update()

        t = threading.Thread(target=do_download, args=(selected,), daemon=True)
        t.start()

    # Attach handlers
    fetch_button.on_click = fetch_clicked
    download_button.on_click = download_clicked

    # Build UI
    page.add(
        ft.Column(
            [
                ft.Row(
                    [text_field, fetch_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [show_all_formats],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [resolution_dropdown, download_button],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [progress_bar, progress_text],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=10
                ),
                status,
                ffmpeg_status,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20
        )
    )

if __name__ == "__main__":
    ft.app(target=main)