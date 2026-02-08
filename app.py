import streamlit as st
import subprocess
import threading
import time
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# --- PAGE CONFIG ---
st.set_page_config(page_title="YouTube Live Simple Streamer", layout="wide")

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
def run_ffmpeg(video_path, audio_path, stream_key, session_id):
    output_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
    
    # FFmpeg command with automatic looping
    cmd = [
        "ffmpeg", "-re",
        "-stream_loop", "-1", "-i", video_path,
        "-stream_loop", "-1", "-i", audio_path,
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4500k",
        "-maxrate", "4500k", "-bufsize", "9000k",
        "-pix_fmt", "yuv420p", "-g", "60",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-map", "0:v:0", "-map", "1:a:0",
        "-f", "flv", output_url
    ]
    
    log_to_database(session_id, "INFO", f"🚀 Starting Stream: {output_url}")
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        st.session_state['ffmpeg_process'] = process
        
        for line in process.stdout:
            # We don't want to spam the DB with every FFmpeg line, but let's log key info
            if "Error" in line or "bitrate" in line:
                log_to_database(session_id, "FFMPEG", line.strip())
        
        process.wait()
    except Exception as e:
        log_to_database(session_id, "ERROR", f"❌ FFmpeg Error: {e}")
    finally:
        log_to_database(session_id, "INFO", "⏹️ Streaming session ended")
        st.session_state['streaming'] = False

# --- UI ---
def main():
    st.title("📺 YouTube Live Simple Streamer")
    st.info("ℹ️ Notes: Video & Audio akan di-looping otomatis secara mandiri.")
    
    init_database()
    
    if 'session_id' not in st.session_state:
        st.session_state['session_id'] = f"session_{int(time.time())}"
    if 'streaming' not in st.session_state:
        st.session_state['streaming'] = False

    # 1. Setup Media
    st.header("1. Setup Media")
    col1, col2 = st.columns(2)
    
    with col1:
        video_file = st.file_uploader("Upload Video Target", type=['mp4', 'mkv', 'mov', 'avi', 'mpeg4'], help="Limit 200MB per file")
    
    with col2:
        audio_file = st.file_uploader("Upload Audio Target", type=['mp3', 'wav', 'm4a'], help="Limit 200MB per file")

    # 2. Target Stream
    st.header("2. Target Stream")
    stream_key = st.text_input("Input Stream Key YouTube", type="password")

    # Streaming Controls
    st.markdown("---")
    
    col_start, col_stop = st.columns(2)
    
    with col_start:
        if st.button("▶️ Start Streaming", type="primary", use_container_width=True, disabled=st.session_state['streaming']):
            if not video_file or not audio_file or not stream_key:
                st.error("⚠️ Please provide Video, Audio, and Stream Key!")
            else:
                # Save uploaded files temporarily
                temp_video = Path(f"temp_video_{st.session_state['session_id']}.mp4")
                temp_audio = Path(f"temp_audio_{st.session_state['session_id']}.mp3")
                
                with open(temp_video, "wb") as f:
                    f.write(video_file.getbuffer())
                with open(temp_audio, "wb") as f:
                    f.write(audio_file.getbuffer())
                
                st.session_state['streaming'] = True
                st.session_state['video_path'] = str(temp_video)
                st.session_state['audio_path'] = str(temp_audio)
                st.session_state['stream_key'] = stream_key
                
                # Start FFmpeg in a background thread
                thread = threading.Thread(
                    target=run_ffmpeg, 
                    args=(str(temp_video), str(temp_audio), stream_key, st.session_state['session_id']),
                    daemon=True
                )
                thread.start()
                st.success("Streaming started!")
                st.rerun()
                
    with col_stop:
        if st.button("⏹️ Stop Streaming", type="secondary", use_container_width=True, disabled=not st.session_state['streaming']):
            if 'ffmpeg_process' in st.session_state:
                st.session_state['ffmpeg_process'].terminate()
                # Also try to kill any orphaned ffmpeg
                os.system("pkill ffmpeg")
            
            st.session_state['streaming'] = False
            st.warning("Streaming stopped.")
            st.rerun()

    # Status & Logs
    if st.session_state['streaming']:
        st.error("🔴 STATUS: LIVE")
        with st.expander("📝 Live Logs", expanded=True):
            conn = sqlite3.connect("streaming_logs.db")
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp, message FROM streaming_logs WHERE session_id = ? ORDER BY timestamp DESC LIMIT 50", (st.session_state['session_id'],))
            logs = cursor.fetchall()
            conn.close()
            if logs:
                for ts, msg in logs:
                    st.text(f"[{ts}] {msg}")
        
        # Auto-refresh when live
        time.sleep(2)
        st.rerun()

if __name__ == "__main__":
    main()
