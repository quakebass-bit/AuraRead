
# 📖 Aura Read

**Aura Read** is a lightweight, self-hosted web e-book reader featuring real-time, buffered Text-to-Speech (TTS) streaming. It supports both cloud neural voices (Microsoft Edge TTS) and ultra-fast, local, offline voice synthesis ([Piper TTS](https://github.com/rhasspy/piper)).

Designed to run smoothly on desktop browsers, home servers, and directly on Android smartphones via Termux.

---

## 📸 Screenshots

| Dark Mode (Default) | Light Mode |
| :---: | :---: |
| ![Aura Read Dark Theme](screenshots/back.png) | ![Aura Read Light Theme](screenshots/white.png) |

---

## ✨ Features

- **Document Support:** Client-side parsing of `.fb2`, `.txt`, `.docx`, and `.pdf` files (including embedded illustrations in FB2/DOCX).
- **Dual TTS Engine:**
  - **Edge TTS:** High-quality neural cloud voices (English, Russian, and more). No API keys required.
  - **Piper TTS:** Fully offline, fast, local neural speech synthesis via ONNX models.
- **Continuous Buffered Streaming:** Audio chunks pre-fetch ahead of time so playback transitions seamlessly across paragraphs without pauses.
- **Synchronized Visual Tracking:** Auto-scrolls and highlights the active paragraph as it is spoken.
- **Reading Deck UI:**
  - Dark and Light themes.
  - Typography customization (Lora, Georgia, Times, Modern, Monospace), font size stepper, and playback speed control.
  - **Lock Screen Mode:** Prevents accidental taps in pockets or on mobile screens during reading.
  - **MediaSession API Support:** Control playback directly from your phone's lock screen or notification center.
  - Per-book progress persistence saved automatically.

---

## 📂 Project Structure

```text
aura-read/
├── models/             # Piper ONNX models and configs (.gitignore)
├── piper/              # (Optional) Local Piper binaries (.gitignore)
├── screenshots/        # UI preview images for documentation
│   ├── back.png
│   └── white.png
├── static/
│   └── audio/          # Ephemeral synthesized audio chunks (auto-cleaned)
├── templates/
│   └── index.html      # Responsive web reader interface
├── app.py              # Flask server and TTS dispatcher
├── requirements.txt    # Python dependencies
└── README.md

```

---

## 🚀 Quick Start (Linux / macOS / Windows)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/aura-read.git
cd aura-read

```

### 2. Set up Python environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

```

### 3. Run the application

```bash
python app.py

```

Open your browser and navigate to: `http://localhost:5001`.

---

## 🎙️️ Piper TTS Setup (Offline Voices)

Piper is completely optional. If you only want Edge TTS, you can skip this step.

### 1. Install Piper

Download the appropriate release archive for your OS/architecture from [rhasspy/piper releases](https://github.com/rhasspy/piper/releases).

You can set it up in one of three easy ways:

* **Option A (Easiest — Portable):** Extract the contents of the archive directly into a `piper/` folder inside the project root (`piper/piper.exe` on Windows or `piper/piper` on Linux). The server detects it automatically.
* **Option B (System PATH):** Place the Piper binary in your system `PATH` so running `piper --version` works from any terminal.
* **Option C (Environment Variable):** Point to your binary manually:
```bash
export PIPER_CMD="/custom/path/to/piper"
# On Windows (cmd): set PIPER_CMD=C:\custom\path\piper.exe

```



### 2. Download Voice Models

Download both the `.onnx` and `.onnx.json` model files from the [Piper HuggingFace Repository](https://huggingface.co/rhasspy/piper-voices) into the `models/` directory:

* **English (US):**
* `en_US-lessac-medium.onnx` + `en_US-lessac-medium.onnx.json`
* `en_US-ryan-medium.onnx` + `en_US-ryan-medium.onnx.json`


* **Russian:**
* `ru_RU-irina-medium.onnx` + `ru_RU-irina-medium.onnx.json`
* `ru_RU-ruslan-medium.onnx` + `ru_RU-ruslan-medium.onnx.json`



---

## 📱 Running on Android (Termux + proot-distro Ubuntu)

Aura Read runs offline on Android devices inside Termux:

1. **Install proot-distro and Ubuntu in Termux:**

```bash
pkg update && pkg install proot-distro git python
proot-distro install ubuntu
proot-distro login ubuntu

```

2. **Install dependencies inside Ubuntu:**

```bash
apt update && apt install python3 python3-pip git wget tar

```

3. **Install Piper (ARM64 binary for Android):**

```bash
cd /root
wget https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
tar -xvf piper_linux_aarch64.tar.gz
# Piper binary will be located at /root/piper/piper

```

4. **Clone and run Aura Read:**

```bash
git clone https://github.com/YOUR_USERNAME/aura-read.git
cd aura-read
pip3 install -r requirements.txt
python3 app.py

```

5. Open your mobile browser and go to `[http://127.0.0.1:5001](http://127.0.0.1:5001)`.

---

## 📄 License

MIT License.

```
