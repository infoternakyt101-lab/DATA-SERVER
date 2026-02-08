import streamlit as st
import subprocess
import threading
import time
import os
import sqlite3
import random
from datetime import datetime
from pathlib import Path

# --- PAGE CONFIG ---
st.set_page_config(page_title="YouTube Live Multi-Media Streamer", layout="wide")

# --- DIRECTORIES ---
VIDEO_DIR = Path("media/videos")
AUDIO_DIR = Path("media/audios")
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# --- DATABASE SETUP ---
def init_database():
    try:
        db_path = Path("streaming_logs.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS streaming_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                log_type TEXT NOT NULL,
                message TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Database error: {e}")

def log_to_database(session_id, log_type, message):
    try:
        conn = sqlite3.connect("streaming_logs.db")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO streaming_logs (timestamp, session_id, log_type, message)
            VALUES (?, ?, ?, ?)
        ''', (datetime.now().isoformat(), session_id, log_type, message))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error logging: {e}")

# --- STREAMING CORE ---
def run_ffmpeg(stream_key, session_id):
    output_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
    
    # To achieve seamless random play without disconnects, 
    # we use a concat demuxer with a generated list.
    
    def get_random_playlist():
        vids = list(VIDEO_DIR.glob("*"))
        auds = list(AUDIO_DIR.glob("*"))
        return vids, auds

    vids, auds = get_random_playlist()
    if not vids:
        log_to_database(session_id, "ERROR", "No video files found in media/videos")
        return

    video_list_path = Path(f"videos_{session_id}.txt")
    audio_list_path = Path(f"audios_{session_id}.txt")
    
    def update_lists():
        v, a = get_random_playlist()
        if v:
            with open(video_list_path, "w") as f:
                # Shuffle before creating the list for true randomness
                v_shuffled = list(v)
                random.shuffle(v_shuffled)
                for _ in range(100): # Create a long enough list
                    f.write(f"file '{random.choice(v_shuffled).absolute()}'\n")
        
        if a:
            with open(audio_list_path, "w") as f:
                a_shuffled = list(a)
                random.shuffle(a_shuffled)
                for _ in range(100):
                    f.write(f"file '{random.choice(a_shuffled).absolute()}'\n")

    update_lists()

    cmd = [
        "ffmpeg", "-re",
        "-f", "concat", "-safe", "0", "-i", str(video_list_path),
    ]
    
    if AUDIO_DIR.glob("*"):
        cmd += ["-f", "concat", "-safe", "0", "-i", str(audio_list_path)]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k",
            "-maxrate", "4500k", "-bufsize", "9000k",
            "-pix_fmt", "yuv420p", "-g", "60",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-map", "0:v:0", "-map", "1:a:0",
        ]
    else:
        cmd += [
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k",
            "-maxrate", "4500k", "-bufsize", "9000k",
            "-pix_fmt", "yuv420p", "-g", "60",
            "-c:a", "aac", "-b:a", "128k",
            "-map", "0:v:0", "-map", "1:a:0",
        ]
    
    cmd += ["-f", "flv", output_url]
    
    log_to_database(session_id, "INFO", f"🚀 Starting Seamless Random Stream: {output_url}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        st.session_state['ffmpeg_process'] = process
        
        for line in process.stdout:
            if "Error" in line or "bitrate" in line:
                log_to_database(session_id, "FFMPEG", line.strip())
        
        process.wait()
    except Exception as e:
        log_to_database(session_id, "ERROR", f"❌ FFmpeg Error: {e}")
    finally:
        if video_list_path.exists(): video_list_path.unlink()
        if audio_list_path.exists(): audio_list_path.unlink()
        log_to_database(session_id, "INFO", "⏹️ Streaming session ended")
        st.session_state['streaming'] = False

# --- UI ---
def main():
    st.title("📺 YouTube Live Multi-Media Streamer")
    st.info("ℹ️ Info: Sistem akan memutar Video & Audio secara acak (random) dari folder media.")
    
    init_database()
    
    if 'session_id' not in st.session_state:
        st.session_state['session_id'] = f"session_{int(time.time())}"
    if 'streaming' not in st.session_state:
        st.session_state['streaming'] = False

    # 1. Manage Media
    st.header("1. Media Management")
    if st.button("🗑️ Erase All Media (Videos & Audios)", type="secondary", use_container_width=True):
        v_files = list(VIDEO_DIR.glob("*"))
        a_files = list(AUDIO_DIR.glob("*"))
        for f in v_files + a_files:
            try:
                f.unlink()
            except Exception:
                pass
        st.success("All media erased!")
        st.rerun()

    col_v, col_a = st.columns(2)
    
    with col_v:
        st.subheader("Videos")
        uploaded_videos = st.file_uploader("Upload Videos", type=['mp4', 'mkv', 'mov'], accept_multiple_files=True, help="Max 200MB per file")
        if uploaded_videos:
            for v in uploaded_videos:
                with open(VIDEO_DIR / v.name, "wb") as f:
                    f.write(v.getbuffer())
            st.success(f"Uploaded {len(uploaded_videos)} videos")
        
        v_files = list(VIDEO_DIR.glob("*"))
        if v_files:
            st.write(f"Total Videos: {len(v_files)}")
            if st.button("Clear All Videos"):
                for f in v_files:
                    try:
                        f.unlink()
                    except Exception:
                        pass
                st.rerun()

    with col_a:
        st.subheader("Audios")
        uploaded_audios = st.file_uploader("Upload Audios", type=['mp3', 'wav', 'm4a'], accept_multiple_files=True, help="Max 200MB per file")
        if uploaded_audios:
            for a in uploaded_audios:
                with open(AUDIO_DIR / a.name, "wb") as f:
                    f.write(a.getbuffer())
            st.success(f"Uploaded {len(uploaded_audios)} audios")
            
        a_files = list(AUDIO_DIR.glob("*"))
        if a_files:
            st.write(f"Total Audios: {len(a_files)}")
            if st.button("Clear All Audios"):
                for f in a_files:
                    try:
                        f.unlink()
                    except Exception:
                        pass
                st.rerun()

    # 2. Target Stream
    st.header("2. Target Stream")
    stream_key = st.text_input("Input Stream Key YouTube", type="password")

    # Streaming Controls
    st.markdown("---")
    
    col_start, col_stop = st.columns(2)
    
    with col_start:
        if st.button("▶️ Start Streaming", type="primary", use_container_width=True, disabled=st.session_state['streaming']):
            if not list(VIDEO_DIR.glob("*")) or not stream_key:
                st.error("⚠️ Please upload at least one video and provide Stream Key!")
            else:
                st.session_state['streaming'] = True
                st.session_state['stream_key'] = stream_key
                
                thread = threading.Thread(
                    target=run_ffmpeg, 
                    args=(stream_key, st.session_state['session_id']),
                    daemon=True
                )
                thread.start()
                st.success("Streaming started!")
                st.rerun()
                
    with col_stop:
        if st.button("⏹️ Stop Streaming", type="secondary", use_container_width=True, disabled=not st.session_state['streaming']):
            if 'ffmpeg_process' in st.session_state:
                st.session_state['ffmpeg_process'].terminate()
                os.system("pkill ffmpeg")
            
            st.session_state['streaming'] = False
            st.warning("Streaming stopped.")
            st.rerun()

    # Status & Logs
    if st.session_state['streaming']:
        st.error("🔴 STATUS: LIVE (Seamless Random Mode)")
        with st.expander("📝 Live Logs", expanded=True):
            conn = sqlite3.connect("streaming_logs.db")
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp, message FROM streaming_logs WHERE session_id = ? ORDER BY timestamp DESC LIMIT 50", (st.session_state['session_id'],))
            logs = cursor.fetchall()
            conn.close()
            if logs:
                for ts, msg in logs:
                    st.text(f"[{ts}] {msg}")
        
        time.sleep(2)
        st.rerun()

if __name__ == "__main__":
    main()
