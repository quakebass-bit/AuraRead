import os
import glob
import time
import json
import uuid
import shutil
import asyncio
import subprocess
from flask import Flask, render_template, request, jsonify, send_from_directory
import edge_tts

app = Flask(__name__)

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
AUDIO_DIR = os.path.join(STATIC_DIR, 'audio')
MODELS_DIR = os.path.join(BASE_DIR, 'models')
PROGRESS_FILE = os.path.join(BASE_DIR, 'progress.json')

def find_piper_executable():
    """
    Automatically detects the Piper executable across platforms:
    1. Custom path via PIPER_CMD environment variable
    2. Local project folder (piper/piper.exe on Windows, piper/piper on Linux)
    3. Dedicated Termux / proot-distro Ubuntu path (/root/piper/piper)
    4. System PATH lookup
    5. Fallback default executable name
    """
    env_path = os.getenv("PIPER_CMD")
    if env_path:
        return env_path
    
    local_win = os.path.join(BASE_DIR, 'piper', 'piper.exe')
    local_linux = os.path.join(BASE_DIR, 'piper', 'piper')
    if os.name == 'nt' and os.path.exists(local_win):
        return local_win
    if os.path.exists(local_linux):
        return local_linux

    termux_path = "/root/piper/piper"
    if os.path.exists(termux_path):
        return termux_path

    system_piper = shutil.which("piper.exe") if os.name == 'nt' else shutil.which("piper")
    if system_piper:
        return system_piper

    return "piper.exe" if os.name == 'nt' else "piper"

PIPER_CMD = find_piper_executable()

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# Piper voice models mapping
MODELS = {
    'piper-en-lessac': 'en_US-lessac-medium.onnx',
    'piper-en-ryan': 'en_US-ryan-medium.onnx',
    'piper-ru-irina': 'ru_RU-irina-medium.onnx',
    'piper-ru-ruslan': 'ru_RU-ruslan-medium.onnx'
}

def cleanup_old_audio():
    """Remove generated audio cache files older than 5 minutes."""
    now = time.time()
    for ext in ('*.mp3', '*.wav'):
        for f in glob.glob(os.path.join(AUDIO_DIR, ext)):
            try:
                if os.stat(f).st_mtime < now - 300:
                    os.remove(f)
            except Exception:
                pass

def load_progress_data():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_progress_data(data):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

@app.route('/')
def index():
    return render_template('index.html')

# --- PWA Routes ---
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory(STATIC_DIR, 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def serve_sw():
    response = send_from_directory(STATIC_DIR, 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    return response

# --- App API Routes ---
@app.route('/save_progress', methods=['POST'])
def save_progress():
    data = request.json or {}
    book_name = data.get('book_name')
    index = data.get('index')
    
    if not book_name:
        return jsonify({'success': False, 'error': 'Missing book_name'})

    progress = load_progress_data()
    progress[book_name] = {
        'index': index,
        'updated_at': time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_progress_data(progress)
    return jsonify({'success': True})

@app.route('/load_progress', methods=['GET'])
def load_progress():
    book_name = request.args.get('book_name')
    progress = load_progress_data()
    return jsonify(progress.get(book_name, {'index': 0}))

@app.route('/synthesize', methods=['POST'])
def synthesize():
    text = request.form.get('text', '').strip()
    voice = request.form.get('voice', 'en-US-JennyNeural')

    if not text:
        return jsonify({'success': False, 'error': 'Text is empty'})

    cleanup_old_audio()

    try:
        if voice in MODELS:
            model_name = MODELS[voice]
            model_path = os.path.join(MODELS_DIR, model_name)
            
            if not os.path.exists(model_path):
                return jsonify({
                    'success': False, 
                    'error': f'Model {model_name} not found in models/ folder!'
                })

            filename = f"speech_{uuid.uuid4().hex[:8]}.wav"
            filepath = os.path.join(AUDIO_DIR, filename)

            cmd = [
                PIPER_CMD,
                '--model', model_path,
                '--output_file', filepath
            ]

            result = subprocess.run(
                cmd,
                input=text.encode('utf-8'),
                capture_output=True,
                timeout=60
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                return jsonify({'success': False, 'error': f"Piper error: {error_msg}"})
                
            return jsonify({'success': True, 'audio_url': f'/static/audio/{filename}', 'engine': 'piper'})
            
        else:
            filename = f"speech_{uuid.uuid4().hex[:8]}.mp3"
            filepath = os.path.join(AUDIO_DIR, filename)
            
            asyncio.run(generate_audio(text, voice, filepath))
            return jsonify({'success': True, 'audio_url': f'/static/audio/{filename}', 'engine': 'edge'})

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Piper generation timed out.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

async def generate_audio(text, voice, filepath):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filepath)

if __name__ == '__main__':
    with app.app_context():
        cleanup_old_audio()
        
    print("\n" + "=" * 55)
    print("📖 Aura Read TTS Server Started")
    print(f"📍 Piper Binary Path: {PIPER_CMD}")
    print("📍 Local UI:           http://127.0.0.1:5001")
    print("=" * 55 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)