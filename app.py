import os
import glob
import time
import json
import shutil
import hashlib
import tempfile
import re
import sys
import subprocess
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
AUDIO_DIR = os.path.join(STATIC_DIR, 'audio')
MODELS_DIR = os.path.join(BASE_DIR, 'models')
PROGRESS_FILE = os.path.join(BASE_DIR, 'progress.json')

CACHE_TTL_SECONDS = 600  # 10 минут кэша

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
    """Remove generated audio cache files older than 10 minutes (600s)."""
    now = time.time()
    for ext in ('*.mp3', '*.wav'):
        for f in glob.glob(os.path.join(AUDIO_DIR, ext)):
            try:
                if os.stat(f).st_mtime < (now - CACHE_TTL_SECONDS):
                    os.remove(f)
            except Exception:
                pass

def split_into_chunks(text: str, max_chars: int = 300, min_chars: int = 20) -> list[str]:
    """
    Надежное разбиение текста на 1-2 предложения с защитой сокращений,
    инициалов и чисел с плавающей точкой без хрупких lookbehind.
    """
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return []

    # Список частых сокращений для маскировки
    abbreviations = [
        "т.е.", "т.к.", "т.д.", "т.п.", "и т.д.", "и т.п.",
        "г-н.", "г-жа.", "д-р.", "проф.", "акад.", "доц.",
        "руб.", "коп.", "Mr.", "Mrs.", "Ms.", "Dr.", "e.g.", "i.e.", "etc."
    ]

    working_text = cleaned
    replacements = {}
    
    # 1. Защита чисел с плавающей точкой (3.14 -> 3@@DOT@@14)
    working_text = re.sub(r'(\d+)\.(\d+)', r'\1@@DOT@@\2', working_text)

    # 2. Защита инициалов (А.С. Пушкин или J. K. Rowling)
    working_text = re.sub(r'\b([A-ZА-ЯЁ])\.\s*([A-ZА-ЯЁ])\.', r'\1@@DOT@@\2@@DOT@@', working_text)
    working_text = re.sub(r'\b([A-ZА-ЯЁ])\.\s+(?=[A-ZА-ЯЁ])', r'\1@@DOT@@ ', working_text)

    # 3. Защита стандартных сокращений через словарь оригиналов
    for idx, abbr in enumerate(abbreviations):
        # Ищем без учета регистра, сохраняя оригинальное вхождение
        matches = list(re.finditer(re.escape(abbr), working_text, flags=re.IGNORECASE))
        for m in reversed(matches):
            matched_str = m.group(0)
            token = f"@@ABBR_{idx}_{m.start()}@@"
            replacements[token] = matched_str
            working_text = working_text[:m.start()] + token + working_text[m.end():]

    # 4. Деление по знакам завершения (. ! ?)
    raw_sentences = re.split(r'(?<=[\.\?!])\s+(?=[A-ZА-ЯЁ\d«"\(])', working_text)

    # 5. Точное восстановление оригиналов из словаря
    restored_sentences = []
    for s in raw_sentences:
        s_restored = s.replace('@@DOT@@', '.')
        for token, original in replacements.items():
            if token in s_restored:
                s_restored = s_restored.replace(token, original)
        s_restored = s_restored.strip()
        if s_restored:
            restored_sentences.append(s_restored)

    # 6. Дробление сверхдлинных предложений (> max_chars)
    sub_divided = []
    for sent in restored_sentences:
        if len(sent) > max_chars:
            clauses = re.split(r'(?<=[\,\;\:\—])\s+', sent)
            curr = ""
            for cl in clauses:
                if len(curr) + len(cl) + 1 <= max_chars:
                    curr = f"{curr} {cl}".strip()
                else:
                    if curr:
                        sub_divided.append(curr)
                    curr = cl
            if curr:
                sub_divided.append(curr)
        else:
            sub_divided.append(sent)

    # 7. Сборка по 1-2 предложения (до max_chars)
    chunks = []
    buffer = ""
    for s in sub_divided:
        if not buffer:
            buffer = s
        elif len(buffer) + len(s) + 1 <= max_chars:
            buffer = f"{buffer} {s}"
            chunks.append(buffer)
            buffer = ""
        else:
            chunks.append(buffer)
            buffer = s

    if buffer:
        chunks.append(buffer)

    # 8. Слияние коротких сегментов (< min_chars)
    merged = []
    for chunk in chunks:
        if merged and (len(chunk) < min_chars or len(merged[-1]) < min_chars):
            merged[-1] = f"{merged[-1]} {chunk}".strip()
        else:
            merged.append(chunk)

    return merged

def run_edge_tts_cli(text: str, voice: str, output_path: str, timeout_sec: int = 40):
    """
    Запуск edge-tts через subprocess CLI с передачей текста через временный файл (-f).
    Работает надёжно в Windows и Termux без проблем с кавычками и WebSocket.
    """
    temp_txt = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
            temp_txt = f.name
            f.write(text)

        cmd = [
            sys.executable,
            "-m",
            "edge_tts",
            "--voice", voice,
            "-f", temp_txt,
            "--write-media", output_path
        ]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=timeout_sec,
            env=env
        )

        if result.returncode != 0:
            err = result.stderr.strip() or f"CLI returned code {result.returncode}"
            raise RuntimeError(err)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise FileNotFoundError("Edge TTS output file was not created or is empty.")

    finally:
        if temp_txt and os.path.exists(temp_txt):
            try:
                os.remove(temp_txt)
            except OSError:
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

@app.route('/api/split', methods=['POST'])
def api_split():
    """Разбивка массива абзацев или одного абзаца на 1-2 предложения."""
    data = request.get_json(silent=True) or {}
    
    # Поддержка пакетного запроса сразу для всей книги
    if 'paragraphs' in data and isinstance(data['paragraphs'], list):
        results = [split_into_chunks(p) for p in data['paragraphs']]
        return jsonify({'results': results})

    text = data.get('text', '')
    if not text:
        return jsonify({'chunks': []})
    return jsonify({'chunks': split_into_chunks(text)})

@app.route('/synthesize', methods=['POST'])
def synthesize():
    text = (request.form.get('text') or (request.json or {}).get('text') or '').strip()
    voice = (request.form.get('voice') or (request.json or {}).get('voice') or 'en-US-JennyNeural').strip()

    if not text:
        return jsonify({'success': False, 'error': 'Text is empty'})

    cleanup_old_audio()

    # Генерация детерминированного имени файла на основе текста и голоса (MD5)
    hash_seed = f"{text}_{voice}".encode('utf-8')
    cache_hash = hashlib.md5(hash_seed).hexdigest()

    try:
        if voice in MODELS:
            model_name = MODELS[voice]
            model_path = os.path.join(MODELS_DIR, model_name)
            
            if not os.path.exists(model_path):
                return jsonify({
                    'success': False, 
                    'error': f'Model {model_name} not found in models/ folder!'
                })

            filename = f"speech_{cache_hash}.wav"
            filepath = os.path.join(AUDIO_DIR, filename)

            # Проверка кэша Piper (моложе 10 минут)
            if os.path.exists(filepath) and (time.time() - os.path.getmtime(filepath) < CACHE_TTL_SECONDS):
                return jsonify({'success': True, 'audio_url': f'/static/audio/{filename}', 'engine': 'piper', 'cached': True})

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
                
            return jsonify({'success': True, 'audio_url': f'/static/audio/{filename}', 'engine': 'piper', 'cached': False})
            
        else:
            filename = f"speech_{cache_hash}.mp3"
            filepath = os.path.join(AUDIO_DIR, filename)

            # Проверка кэша Edge TTS (моложе 10 минут)
            if os.path.exists(filepath) and (time.time() - os.path.getmtime(filepath) < CACHE_TTL_SECONDS):
                return jsonify({'success': True, 'audio_url': f'/static/audio/{filename}', 'engine': 'edge', 'cached': True})

            # CLI-оркестрация без asyncio
            run_edge_tts_cli(text=text, voice=voice, output_path=filepath, timeout_sec=40)
            return jsonify({'success': True, 'audio_url': f'/static/audio/{filename}', 'engine': 'edge', 'cached': False})

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Audio generation timed out.'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        cleanup_old_audio()
        
    print("\n" + "=" * 55)
    print("📖 Aura Read TTS Server Started")
    print(f"📍 Piper Binary Path: {PIPER_CMD}")
    print("📍 Local UI:           http://127.0.0.1:5001")
    print("=" * 55 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)