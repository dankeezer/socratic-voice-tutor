#!/usr/bin/env python3
import os
import sys
import json
import base64
import wave
import subprocess
import urllib.request
import urllib.error
import ssl
import threading
import time
import re
import html

class AnimatedLoader:
    def __init__(self, message="Thinking"):
        self.message = message
        self.is_running = False
        self._thread = None

    def _animate(self):
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        while self.is_running:
            sys.stdout.write(f"\r\033[90m{frames[idx]} {self.message}...\033[0m")
            sys.stdout.flush()
            idx = (idx + 1) % len(frames)
            time.sleep(0.08)

    def start(self):
        if not self.is_running:
            self.is_running = True
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()

    def stop(self):
        if self.is_running:
            self.is_running = False
            if self._thread:
                self._thread.join(timeout=1.0)
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

# Config files
KEY_FILE = ".tutor_key"
WAV_OUTPUT_FILE = "tutor_response.wav"
TUTOR_CONFIG_FILE = ".tutor_config"

def load_tutor_config():
    config = {
        "voice_speed": 1.1,
        "voice_name": "Aoede"
    }
    if os.path.exists(TUTOR_CONFIG_FILE):
        try:
            with open(TUTOR_CONFIG_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    config[k] = v
        except Exception:
            pass
    return config

def save_tutor_config(config):
    try:
        existing = {}
        if os.path.exists(TUTOR_CONFIG_FILE):
            with open(TUTOR_CONFIG_FILE, "r") as f:
                existing = json.load(f)
        for k, v in config.items():
            existing[k] = v
        with open(TUTOR_CONFIG_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass

def get_obfuscated_key():
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "r") as f:
                obfuscated = f.read().strip()
                return base64.b64decode(obfuscated).decode('utf-8')
        except Exception:
            pass
    return ""

def save_obfuscated_key(key):
    try:
        obfuscated = base64.b64encode(key.encode('utf-8')).decode('utf-8')
        with open(KEY_FILE, "w") as f:
            f.write(obfuscated)
        return True
    except Exception as e:
        print(f"Error saving API Key: {e}")
        return False



def scrape_url(url):
    try:
        # Add basic User-Agent to prevent 403 Forbidden on standard websites
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        ssl_context = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ssl_context, timeout=10) as response:
            raw_html = response.read().decode('utf-8', errors='ignore')
            
            # Strip style & script tags entirely
            clean_html = re.sub(r'<(script|style|noscript)[^>]*?>.*?</\1>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
            # Strip HTML tags
            text = re.sub(r'<[^>]*?>', ' ', clean_html)
            # Decode basic HTML entities
            text = html.unescape(text)
            # Collapse whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            return text
    except Exception as e:
        print(f"\033[31mError scraping URL: {e}\033[0m")
        return ""

def scan_directory(root_path):
    allowed_extensions = {
        '.txt', '.md', '.py', '.js', '.json', '.ts', '.html', '.css', 
        '.go', '.java', '.cpp', '.c', '.h', '.sh', '.yml', '.yaml', 
        '.rst', '.csv', '.sql'
    }
    ignored_dirs = {
        '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', 
        '.env', '.sass-cache', 'dist', 'build', 'target', '.idea', 
        '.vscode', 'out', '.gemini', 'scratch'
    }
    
    file_tree = {} # RelPath -> FullPath
    for root, dirs, files in os.walk(root_path):
        # Modify dirs in-place to prevent traversing ignored directories
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in allowed_extensions:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_path)
                file_tree[rel_path] = full_path
    return file_tree

def build_curriculum_from_folder(root_path):
    ignored_dirs = {
        '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', 
        '.env', '.sass-cache', 'dist', 'build', 'target', '.idea', 
        '.vscode', 'out', '.gemini', 'scratch'
    }
    
    # Identify first-level subdirectories to see if it is a structured curriculum
    subdirs = sorted([d for d in os.listdir(root_path) if os.path.isdir(os.path.join(root_path, d)) and d not in ignored_dirs])
    
    curriculum = {}
    
    if subdirs:
        # Structured Directory: Renders tracks based on first-level folders
        for track in subdirs:
            track_path = os.path.join(root_path, track)
            second_level_items = sorted(os.listdir(track_path))
            track_modules = {}
            
            for item in second_level_items:
                item_path = os.path.join(track_path, item)
                if item.startswith('.') or item in ignored_dirs:
                    continue
                    
                # If it is a directory, gather all text files inside it recursively
                if os.path.isdir(item_path):
                    content_parts = []
                    for r, ds, fs in os.walk(item_path):
                        ds[:] = [d for d in ds if d not in ignored_dirs]
                        for f in sorted(fs):
                            if os.path.splitext(f)[1].lower() in {'.txt', '.md', '.py', '.js', '.json', '.ts', '.html', '.css', '.go', '.java', '.cpp', '.c', '.h', '.sh', '.yml', '.yaml', '.rst', '.csv', '.sql'}:
                                try:
                                    with open(os.path.join(r, f), 'r', encoding='utf-8', errors='ignore') as file_obj:
                                        content_parts.append(f"\n--- FILE: {f} ---\n" + file_obj.read())
                                except Exception:
                                    pass
                    if content_parts:
                        track_modules[item] = "\n".join(content_parts)
                        
                # If it is a file, read it directly
                elif os.path.isfile(item_path) and os.path.splitext(item)[1].lower() in {'.txt', '.md', '.py', '.js', '.json', '.ts', '.html', '.css', '.go', '.java', '.cpp', '.c', '.h', '.sh', '.yml', '.yaml', '.rst', '.csv', '.sql'}:
                    try:
                        with open(item_path, 'r', encoding='utf-8', errors='ignore') as file_obj:
                            track_modules[os.path.splitext(item)[0]] = file_obj.read()
                    except Exception:
                        pass
            if track_modules:
                curriculum[track] = track_modules
                
    # If no subdirs, or if we want flat directory handling:
    if not curriculum:
        file_tree = scan_directory(root_path)
        if not file_tree:
            return {}
            
        print("\n\033[93mSELECT FILES TO INCLUDE IN STUDY SESSION:\033[0m")
        keys = sorted(list(file_tree.keys()))
        selected_flags = {k: True for k in keys} # Default to all selected
        
        while True:
            print("\nActive Checklist of Study Materials:")
            for idx, key in enumerate(keys, 1):
                status = "[x]" if selected_flags[key] else "[ ]"
                print(f"[{idx}] {status} {key}")
            print("\nCommands: 'all' to select all, 'none' to unselect all, <number> to toggle, 'done' to begin session.")
            cmd = input("Command: ").strip().lower()
            if cmd == 'done':
                break
            elif cmd == 'all':
                selected_flags = {k: True for k in keys}
            elif cmd == 'none':
                selected_flags = {k: False for k in keys}
            else:
                try:
                    idx = int(cmd) - 1
                    if 0 <= idx < len(keys):
                        target_key = keys[idx]
                        selected_flags[target_key] = not selected_flags[target_key]
                    else:
                        print("Invalid file number.")
                except Exception:
                    print("Invalid command.")
        
        # Aggregate contents of selected files
        content_parts = []
        selected_names = []
        for key in keys:
            if selected_flags[key]:
                selected_names.append(key)
                try:
                    with open(file_tree[key], 'r', encoding='utf-8', errors='ignore') as file_obj:
                        content_parts.append(f"\n--- FILE: {key} ---\n" + file_obj.read())
                except Exception:
                    pass
        if content_parts:
            curriculum["Custom Directory"] = {
                "Selected Files": "\n".join(content_parts),
                "_selected_paths_list": selected_names
            }
            
    return curriculum

def play_pcm_audio(audio_base64, sample_rate=24000, play_rate=1.1):
    try:
        pcm_bytes = base64.b64decode(audio_base64)
        
        # Write PCM bytes as a standard WAV file (mono, 16-bit = 2 bytes per sample, 24kHz)
        with wave.open(WAV_OUTPUT_FILE, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
            
        # Play natively on macOS via afplay (built-in command-line audio player)
        # Play at the configured playback rate with high-quality pitch preservation (-q 1)
        subprocess.run(["afplay", "-r", str(play_rate), "-q", "1", WAV_OUTPUT_FILE])
        
        # Clean up temporary audio file
        if os.path.exists(WAV_OUTPUT_FILE):
            os.remove(WAV_OUTPUT_FILE)
            
        return True
    except Exception as e:
        print(f"\n[Audio Playback Warning] Failed to play neural audio: {e}")
        return False

def query_gemini(api_key, model, system_instruction, prompt_text, chat_history, voice_name="Aoede", audio_input_path=None):
    is_tts_model = "tts" in model.lower()
    
    # We use gemini-3.5-flash-lite for the Socratic reasoning because of its ultra-low latency,
    # stability, high-quota, and lack of thinking tokens overhead.
    if is_tts_model:
        reasoning_model = "gemini-3.5-flash-lite"
    else:
        reasoning_model = model

    api_version = "v1beta" if (reasoning_model.startswith("gemini-2") or reasoning_model.startswith("gemini-3")) else "v1"
    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{reasoning_model}:generateContent?key={api_key}"
    
    # Format dialogue history
    formatted_history = []
    for turn in chat_history:
        formatted_history.append(f"{'Student' if turn['role'] == 'user' else 'Tutor'}: {turn['text']}")
    history_str = "\n".join(formatted_history)
    
    parts_list = []
    if audio_input_path and os.path.exists(audio_input_path):
        try:
            with open(audio_input_path, "rb") as af:
                audio_data = af.read()
            b64_audio = base64.b64encode(audio_data).decode('utf-8')
            parts_list.append({
                "inlineData": {
                    "mimeType": "audio/wav",
                    "data": b64_audio
                }
            })
            parts_list.append({
                "text": f"Here is the context history:\n{history_str}\n\nPlease listen to this audio representing my spoken response and reply in a Socratic fashion."
            })
        except Exception as e:
            print(f"\033[33mWarning: Failed to load audio file, falling back to text: {e}\033[0m")
            prompt_payload = f"Here is the current conversation state and history:\n{history_str}\n\nStudent's Answer/Command: {prompt_text}\n\nGenerate your next Socratic question or response now."
            parts_list.append({"text": prompt_payload})
    else:
        prompt_payload = f"Here is the current conversation state and history:\n{history_str}\n\nStudent's Answer/Command: {prompt_text}\n\nGenerate your next Socratic question or response now."
        parts_list.append({"text": prompt_payload})
        
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": parts_list
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    import time
    max_retries = 3
    ai_text = None
    
    # Stage 1: Dialogue Reasoning (via high-quota, low-latency gemini-3.5-flash-lite)
    for attempt in range(1, max_retries + 1):
        try:
            import ssl
            ssl_context = ssl._create_unverified_context()
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode('utf-8'), 
                headers=headers, 
                method='POST'
            )
            with urllib.request.urlopen(req, context=ssl_context) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                parts = res_data['candidates'][0]['content']['parts']
                ai_text_list = [part['text'] for part in parts if 'text' in part]
                ai_text = "".join(ai_text_list).strip()
                break
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            try:
                err_json = json.loads(error_body)
                error_msg = err_json['error']['message']
            except Exception:
                error_msg = error_body
                
            if e.code in [429, 500, 502, 503, 504]:
                if attempt < max_retries:
                    sleep_time = attempt * 2.0
                    print(f"\033[33m\n[Warning] Gemini server busy/rate-limited (HTTP {e.code}). Retrying in {sleep_time}s (Attempt {attempt}/{max_retries})...\033[0m")
                    time.sleep(sleep_time)
                    continue
            raise Exception(f"{error_msg} (HTTP {e.code})")
        except Exception as e:
            if attempt < max_retries:
                sleep_time = attempt * 2.0
                print(f"\033[33m\n[Warning] Connection error ({e}). Retrying in {sleep_time}s (Attempt {attempt}/{max_retries})...\033[0m")
                time.sleep(sleep_time)
                continue
            raise Exception(str(e))
            
    if not ai_text:
        ai_text = "I didn't catch that concept clearly. Could you expand on it?"
        
    # Clear the "Thinking..." line and flush
    print("\r\033[K", end="")
    sys.stdout.flush()
        
    audio_base64 = None
    
    # Stage 2: Light-weight Audio Synthesis (via specialized TTS model)
    if is_tts_model and ai_text:
        tts_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        clean_voice_text = ai_text.replace("*", "").replace("#", "").replace("-", "").strip()
        
        tts_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": clean_voice_text
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1024,
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }
        
        for attempt in range(1, max_retries + 1):
            try:
                import ssl
                ssl_context = ssl._create_unverified_context()
                req = urllib.request.Request(
                    tts_url, 
                    data=json.dumps(tts_payload).encode('utf-8'), 
                    headers=headers, 
                    method='POST'
                )
                with urllib.request.urlopen(req, context=ssl_context) as response:
                    res_data = json.loads(response.read().decode('utf-8'))
                    parts = res_data['candidates'][0]['content']['parts']
                    audio_bytes_list = []
                    for part in parts:
                        if 'inlineData' in part and 'data' in part['inlineData']:
                            raw_audio = base64.b64decode(part['inlineData']['data'])
                            audio_bytes_list.append(raw_audio)
                    if audio_bytes_list:
                        combined_audio = b"".join(audio_bytes_list)
                        audio_base64 = base64.b64encode(combined_audio).decode('utf-8')
                    break
            except Exception as e:
                if attempt == max_retries:
                    print(f"\033[33m\n[Warning] Neural synthesis failed, using local fallback TTS: {e}\033[0m")
                else:
                    time.sleep(1.0)
                    
    return ai_text, audio_base64
def get_available_models(api_key):
    import ssl
    ssl_context = ssl._create_unverified_context()
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, context=ssl_context) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            model_names = [m['name'].split('/')[-1] for m in res_data.get('models', [])]
            return model_names
    except Exception as e:
        print(f"\033[33mWarning: Failed to fetch available models: {e}\033[0m")
    return []

def record_voice(output_file="student_input.wav"):
    # Clear any previous audio file
    if os.path.exists(output_file):
        try:
            os.remove(output_file)
        except Exception:
            pass
            
    # Check if ffmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("\n\033[31mError: ffmpeg is not installed on your system.\033[0m")
        print("To enable hands-free voice input, please run:")
        print("   \033[96mbrew install ffmpeg\033[0m")
        print("And make sure to grant your Terminal/IDE permission to access the Microphone.\n")
        return False

    print("\n\033[30;42m 🎙️  [RECORDING ACTIVE - SPEAK NOW] \033[0m")
    print("\033[32m -> Press [ENTER] when you are finished speaking to stop recording...\033[0m")
    
    # Start ffmpeg capture using native macOS AVFoundation device layer
    # -f avfoundation: capture framework
    # -i ":default": default system microphone input
    # -ar 16000: sample rate
    # -ac 1: mono channel
    # -y: overwrite existing file
    cmd = [
        "ffmpeg", "-f", "avfoundation",
        "-i", ":default",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        "-loglevel", "quiet",
        output_file
    ]
    
    try:
        # Launch ffmpeg background capture
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Block until the student hits enter to stop
        input()
        
        # Stop ffmpeg cleanly
        process.terminate()
        process.wait()
        
        if os.path.exists(output_file) and os.path.getsize(output_file) > 1000:
            print("\033[92m✔ Voice input captured.\033[0m")
            return True
        else:
            print("\033[31m⚠ Voice capture empty or failed. Check microphone permissions in System Settings.\033[0m")
            return False
    except Exception as e:
        print(f"\033[31mError during voice recording: {e}\033[0m")
        return False

def transcribe_audio_gemini(api_key, model, audio_path):
    # Use gemini-3.5-flash-lite for transcription because specialized TTS models do not support audio-to-text input,
    # and flash-lite has an incredible 0.7s turnaround time.
    transcribe_model = "gemini-3.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{transcribe_model}:generateContent?key={api_key}"
    
    try:
        with open(audio_path, "rb") as af:
            audio_data = af.read()
        b64_audio = base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        return f"[Transcription failed to read file: {e}]"
        
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "audio/wav",
                            "data": b64_audio
                        }
                    },
                    {
                        "text": "Transcribe this audio precisely. Write ONLY the exact spoken English text. Do not add metadata, correction notes, greetings, or conversational filler."
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,  # absolute greedy decoding for precision transcription
            "maxOutputTokens": 300
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        import ssl
        ssl_context = ssl._create_unverified_context()
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers=headers, 
            method='POST'
        )
        with urllib.request.urlopen(req, context=ssl_context) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            parts = res_data['candidates'][0]['content']['parts']
            text_parts = [part['text'] for part in parts if 'text' in part]
            return "".join(text_parts).strip()
    except Exception as e:
        return f"[Transcription service offline: {e}]"

def summarize_content(api_key, raw_content):
    # Try gemini-3.5-flash-lite first (extremely fast, high quota, no thinking tokens truncation, under 2s latency)
    # Then try gemini-3.5-flash with larger maxOutputTokens (4096) to accommodate thinking tokens
    # Then try gemini-1.5-flash
    models_to_try = [
        ("gemini-3.5-flash-lite", 1536),
        ("gemini-3.5-flash", 4096),
        ("gemini-1.5-flash", 1536)
    ]
    
    for model_name, max_tokens in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "You are an expert curriculum summarizer. Read the following course study material and produce "
                                "a highly dense, high-fidelity study guide of key concepts, technical terms, specific commands, "
                                "framework details, and core principles. This summary will be used as a context reference for a "
                                "verbal Socratic quiz. Keep it concise, extremely packed with facts, and limit the total length to "
                                "under 600 words.\n\nRaw Study Material:\n" + raw_content
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_tokens
            }
        }
        
        headers = {"Content-Type": "application/json"}
        ssl_context = ssl._create_unverified_context()
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers=headers, 
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, context=ssl_context) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                parts = res_data['candidates'][0]['content']['parts']
                text_parts = [part['text'] for part in parts if 'text' in part]
                summary_text = "".join(text_parts).strip()
                if len(summary_text) > 200: # Ensure we got a valid, complete summary
                    return summary_text, model_name
        except Exception:
            continue
            
    # Fallback to returning truncated raw content if summarization fails
    return raw_content[:4000], "local fallback raw truncation"

def check_system_dependencies():
    import sys
    print("\n\033[94m🔍 Running system capability checks...\033[0m")
    
    # 1. Check Python version
    py_version = sys.version_info
    print(f"  ✔ Python Version: {py_version.major}.{py_version.minor}.{py_version.micro}")
    
    # 2. Check for ffmpeg (required for audio capture)
    ffmpeg_found = False
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ffmpeg_found = True
        print("  ✔ Voice Recorder: \033[92mffmpeg operational\033[0m")
    except FileNotFoundError:
        print("  ❌ Voice Recorder: \033[31mffmpeg NOT found\033[0m")
        print("     \033[33mTo enable voice input, please install: 'brew install ffmpeg'\033[0m")
        
    # 3. Check for afplay (macOS native player)
    try:
        subprocess.run(["which", "afplay"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  ✔ Neural Player: \033[92mafplay operational\033[0m")
    except Exception:
        print("  ❌ Neural Player: \033[31mafplay NOT found\033[0m (Non-macOS target)")
        
    # 4. Check for say (macOS native fallback)
    try:
        subprocess.run(["which", "say"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  ✔ Fallback Speaker: \033[92msay operational\033[0m")
    except Exception:
        print("  ❌ Fallback Speaker: \033[31msay NOT found\033[0m")
        
    print("\033[94m" + "-"*60 + "\033[0m")
    return ffmpeg_found

def main():
    print("\033[94m" + "="*60 + "\033[0m")
    print("\033[93m" + "     GOOGLE CLOUD SOCRATIC VOICE TUTOR (DESKTOP CLI)" + "\033[0m")
    print("\033[94m" + "="*60 + "\033[0m")
    
    # Run System Dependency Scan
    ffmpeg_available = check_system_dependencies()
    
    # 1. API Key Setup
    api_key = get_obfuscated_key()
    if not api_key:
        print("\nEnter your Gemini API Key to authorize the learning connection.")
        api_key = input("API Key: ").strip()
        if not api_key:
            print("Error: API Key is required to start the Socratic Tutor.")
            return
        save_obfuscated_key(api_key)
        print("\033[92m✔ API Key saved and obfuscated locally.\033[0m")
    else:
        print("\033[92m✔ API Key loaded successfully from secure local vault.\033[0m")
        
    # 2. Select Model and Voice (and Playback Configuration)
    tutor_config = load_tutor_config()
    voice_speed = tutor_config.get("voice_speed", 1.1)
    voice_name = tutor_config.get("voice_name", "Aoede")
    
    # Save back to ensure keys exist in .tutor_config for easy user editing
    tutor_config["voice_speed"] = voice_speed
    tutor_config["voice_name"] = voice_name
    save_tutor_config(tutor_config)
    
    print("\nDetecting models supported by your API Key...")
    available_models = get_available_models(api_key)
    
    # Sort models. Models with 'tts' in their name support native high-fidelity audio perfectly.
    # We penalize models like gemini-3.5-flash and gemini-1.5-flash since they do not natively support AUDIO response modality.
    def score_model(m_name):
        score = 0
        if "tts" in m_name:
            score += 100
        if "3.1" in m_name:
            score += 20
        elif "2.5" in m_name:
            score += 10
        elif "2.0" in m_name:
            score += 5
            
        # Penalize models that don't support audio output
        if "3.5" in m_name or "1.5" in m_name or m_name == "gemini-3.1-pro-preview" or "lite" in m_name:
            score -= 80
        return score

    candidates = [m for m in available_models if "gemini" in m]
    if candidates:
        active_candidates = sorted(candidates, key=score_model, reverse=True)
    else:
        active_candidates = [
            'gemini-3.1-flash-tts-preview',
            'gemini-2.5-flash-preview-tts',
            'gemini-2.5-pro-preview-tts',
            'gemini-2.0-flash-exp'
        ]
        
    selected_model = active_candidates[0]
    
    print(f"Primary Socratic Engine: \033[92m{selected_model}\033[0m")
    print(f"Selected Gemini Neural Voice: \033[95m{voice_name}\033[0m")
    
    # 3. Load and Select Module
    # 3. Load and Select Module
    last_type = tutor_config.get("last_type")
    last_path = tutor_config.get("last_path")
    last_name = tutor_config.get("last_name")
    
    curriculum = None
    selected_path = None
    selected_module = None
    
    # Check if memory exists and is valid
    can_resume = False
    if last_type and last_path:
        if last_type == "url":
            can_resume = True
        elif os.path.exists(last_path):
            can_resume = True
            
    if can_resume:
        print("\n\033[93mRESUME STUDY SESSION:\033[0m")
        print(f"[1] 🔄 Continue learning with: {last_name}")
        print("[2] 🚀 Start a new study session")
        choice = input("\nEnter Choice (1-2): ").strip()
        if choice == "1":
            print(f"\n\033[94m🔄 Restoring session content from {last_type} source...\033[0m")
            if last_type == "file":
                try:
                    with open(last_path, 'r', encoding='utf-8', errors='ignore') as f:
                        file_text = f.read()
                    curriculum = { "Single Files": { last_name: file_text } }
                    selected_path = "Single Files"
                    selected_module = last_name
                except Exception as e:
                    print(f"Error restoring file: {e}")
            elif last_type == "url":
                print(f"⚙ Re-scraping URL: {last_path}...")
                scraped_text = scrape_url(last_path)
                if scraped_text:
                    curriculum = { "Web Resources": { last_name: scraped_text } }
                    selected_path = "Web Resources"
                    selected_module = last_name
                else:
                    print("Error: Could not re-scrape URL.")
            elif last_type in ["directory", "directory_structured", "directory_flat"]:
                # Try to load pre-selected files directly from the config first for instantaneous seamless restore
                selected_files = tutor_config.get("selected_files", [])
                if selected_files:
                    content_parts = []
                    loaded_names = []
                    for f_path in selected_files:
                        options_to_try = [f_path, os.path.join(last_path, f_path)]
                        for opt in options_to_try:
                            if os.path.exists(opt) and os.path.isfile(opt):
                                try:
                                    with open(opt, 'r', encoding='utf-8', errors='ignore') as file_obj:
                                        rel_display = os.path.relpath(opt, last_path) if last_path else os.path.basename(opt)
                                        content_parts.append(f"\n--- FILE: {rel_display} ---\n" + file_obj.read())
                                        loaded_names.append(rel_display)
                                    break
                                except Exception:
                                    pass
                    if content_parts:
                        curriculum = { "Custom Directory": { "Selected Files": "\n".join(content_parts) } }
                        selected_path = "Custom Directory"
                        selected_module = "Selected Files"
                        print(f"\033[92m✔ Restored previous session files: {', '.join(loaded_names[:3])}{'...' if len(loaded_names) > 3 else ''}\033[0m")
                
                # If we couldn't load via selected_files, rebuild the structured/flat directory curriculum
                if not curriculum:
                    curriculum = build_curriculum_from_folder(last_path)
                    selected_path = tutor_config.get("last_track")
                    selected_module = tutor_config.get("last_module")
                    
    if not curriculum:
        print("\n\033[93mSELECT YOUR STUDY SOURCE:\033[0m")
        options = [
            ("Load a custom directory (flat or recursive mapping)", "directory"),
            ("Load a custom single file", "file"),
            ("Ingest a web URL", "url")
        ]
        
        for idx, (label, _) in enumerate(options, 1):
            print(f"[{idx}] {label}")
            
        try:
            source_choice = int(input("\nEnter Choice Number: ").strip()) - 1
            if source_choice < 0 or source_choice >= len(options):
                raise ValueError
            selected_source_type = options[source_choice][1]
        except Exception:
            selected_source_type = "directory"
            
        if selected_source_type == "file":
            file_path = input("\nEnter full path to single file: ").strip()
            file_path = os.path.expanduser(file_path)
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                print("\033[31mFile not found.\033[0m")
                sys.exit(1)
            else:
                filename = os.path.basename(file_path)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        file_text = f.read()
                    curriculum = { "Single Files": { filename: file_text } }
                    selected_path = "Single Files"
                    selected_module = filename
                    
                    tutor_config["last_type"] = "file"
                    tutor_config["last_path"] = os.path.abspath(file_path)
                    tutor_config["last_name"] = filename
                    tutor_config["selected_files"] = []
                    save_tutor_config(tutor_config)
                except Exception as e:
                    print(f"Error reading file: {e}")
                    sys.exit(1)
                    
        elif selected_source_type == "url":
            url = input("\nEnter web URL: ").strip()
            print(f"⚙ Fetching and cleaning web page content...")
            scraped_text = scrape_url(url)
            if not scraped_text:
                print("\033[31mFailed to scrape URL.\033[0m")
                sys.exit(1)
            else:
                curriculum = { "Web Resources": { url: scraped_text } }
                selected_path = "Web Resources"
                selected_module = url
                
                tutor_config["last_type"] = "url"
                tutor_config["last_path"] = url
                tutor_config["last_name"] = url
                tutor_config["selected_files"] = []
                save_tutor_config(tutor_config)
                
        elif selected_source_type == "directory":
            dir_path = input("\nEnter full directory path (or '.' for current folder): ").strip()
            dir_path = os.path.expanduser(dir_path)
            if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
                print("\033[31mDirectory not found.\033[0m")
                sys.exit(1)
            else:
                curriculum = build_curriculum_from_folder(dir_path)
                if not curriculum:
                    print("\033[31mNo supported text files found in folder. Exiting...\033[0m")
                    sys.exit(1)
                
                is_flat = "Custom Directory" in curriculum
                tutor_config["last_type"] = "directory_flat" if is_flat else "directory_structured"
                tutor_config["last_path"] = os.path.abspath(dir_path)
                tutor_config["last_name"] = os.path.basename(os.path.abspath(dir_path))
                if is_flat:
                    selected_path = "Custom Directory"
                    selected_module = "Selected Files"
                    tutor_config["selected_files"] = curriculum["Custom Directory"].get("_selected_paths_list", [])
                save_tutor_config(tutor_config)
                
    # 3. Path & Module selection menu (runs if selected_path and selected_module are not yet established)
    if not selected_path or not selected_module:
        print("\n\033[93mSELECT YOUR LEARNING PATH:\033[0m")
        paths = list(curriculum.keys())
        for idx, path in enumerate(paths, 1):
            print(f"[{idx}] {path}")
            
        try:
            path_choice = int(input("\nEnter Path Number: ").strip()) - 1
            if path_choice < 0 or path_choice >= len(paths):
                raise ValueError
            selected_path = paths[path_choice]
        except Exception:
            print("Invalid selection. Connecting to Path 1.")
            selected_path = paths[0]
            
        print(f"\n\033[93mSELECT A MODULE UNDER: {selected_path}\033[0m")
        modules = list(curriculum[selected_path].keys())
        for idx, module in enumerate(modules, 1):
            print(f"[{idx}] {module}")
            
        try:
            module_choice = int(input("\nEnter Module Number: ").strip()) - 1
            if module_choice < 0 or module_choice >= len(modules):
                raise ValueError
            selected_module = modules[module_choice]
        except Exception:
            print("Invalid selection. Connecting to Module 1.")
            selected_module = modules[0]
            
    if tutor_config.get("last_type") in ["directory_structured"]:
        tutor_config["last_track"] = selected_path
        tutor_config["last_module"] = selected_module
        
        # Save specific module files inside selected_files to guarantee absolute resume state
        track_path = os.path.join(tutor_config["last_path"], selected_path)
        module_path = os.path.join(track_path, selected_module)
        if os.path.exists(module_path):
            if os.path.isdir(module_path):
                file_tree = scan_directory(module_path)
                tutor_config["selected_files"] = [os.path.join(module_path, f) for f in file_tree.keys()]
            else:
                tutor_config["selected_files"] = [module_path]
        save_tutor_config(tutor_config)
        
    selected_content = curriculum[selected_path][selected_module]
    print(f"\n\033[92m✔ Loaded Module: {selected_module} ({len(selected_content)} bytes of study material)\033[0m")
    
    # Analyze and compress the study material to prevent HTTP 429 Rate Limits / TPM Quota Exceeded on premium TTS models
    print(f"\033[94m⚙ Analyzing and preparing dense Socratic study context...\033[0m")
    dense_summary, summarizer_model = summarize_content(api_key, selected_content)
    try:
        percentage_reduction = 100 - int(len(dense_summary) / max(1, len(selected_content)) * 100)
    except Exception:
        percentage_reduction = 85
    print(f"\033[92m✔ Study material summarized into high-density reference context via {summarizer_model} (reduced by {percentage_reduction}%)\033[0m")
    
    # 4. Construct Socratic System Instruction
    system_instruction = f"""You are a world-class Socratic Tutor conducting a 1-on-1 verbal quiz session with an advanced systems engineer.
The reference material is the high-density course module summary provided below.

Your Core Guidelines:
1. Speak in a friendly, conversational, professional tone.
2. Ask exactly ONE question at a time.
3. Be EXTREMELY CONCISE: Write exactly ONE or TWO short, punchy sentences (maximum 20-25 words total) per turn. Keep your questions and hints brief, direct, and conversational because your responses are synthesized to speech. This minimizes synthesis latency.
4. OPTIMIZE FOR VOICE: Do NOT use markdown symbols, asterisks, hash signs, math symbols, bullet points, or list formatting. Write clear, natural, speakable English.
5. Socratic Method: Validate correct lines of reasoning, but adapt the difficulty up. If they are incorrect or unsure, break the concept down, offer a gentle hint or ask a simpler sub-question, and never reveal the answers directly.
6. Summary: When they successfully demonstrate understanding of the main concepts in this module, or they wish to wrap up, end the session with a warm 2-sentence summary of what they mastered, and do not assign a score.

Reference Material for this Entire Module:
{dense_summary}"""

    # 5. Dialog Session Loop
    print("\n\033[94m" + "="*60 + "\033[0m")
    print("       SOCRATIC SESSION STARTED - COMMENCING HANDS-FREE VOICE")
    print("   Type your responses below. The Tutor will speak neural audio.")
    print("   Type 'exit' or 'quit' at any time to conclude your quiz.")
    print("\033[94m" + "="*60 + "\033[0m\n")
    
    chat_history = []
    user_input = "[START_QUIZ]"
    audio_path = None
    
    # Flag to monitor if we had to failover to local TTS due to API key restrictions
    use_neural_audio = True
    
    while True:
        try:
            # Start the animated loader to reassure the user
            loader = AnimatedLoader("Thinking")
            loader.start()
                 
            ai_text, audio_base64 = query_gemini(
                api_key, 
                selected_model, 
                system_instruction, 
                user_input if user_input != "[START_QUIZ]" else "Begin the Socratic quiz, introduce yourself warmly, and ask the first foundational question.",
                chat_history,
                voice_name,
                audio_path
            )
            
            # Stop the loader cleanly
            loader.stop()
            
            # Print response
            print(f"\n\033[92mTutor:\033[0m {ai_text}\n")
            
            # Record in history (using text tokens to preserve prompt context weight)
            if user_input != "[START_QUIZ]":
                chat_history.append({"role": "user", "text": user_input})
            chat_history.append({"role": "model", "text": ai_text})
            
            if len(chat_history) > 20:
                chat_history = chat_history[-20:]
                
            # Play Neural Audio via afplay
            if use_neural_audio and audio_base64:
                played = play_pcm_audio(audio_base64, play_rate=voice_speed)
                if not played:
                    # Fallback to high-quality macOS system default voice
                    print("\033[30;43m[Voice Output: macOS Premium System Fallback]\033[0m")
                    subprocess.run(["say", ai_text])
            else:
                # Fallback to high-quality macOS system default voice when model returns text-only
                print("\033[30;43m[Voice Output: macOS Premium System Fallback]\033[0m")
                subprocess.run(["say", ai_text])
                
            # Get User Input
            print("\033[94mYou:\033[0m")
            if ffmpeg_available:
                print("  \033[90m- Press [ENTER] to record your voice\033[0m")
                print("  \033[90m- Or type your response below and press [ENTER]\033[0m")
            else:
                print("  \033[90m- [Voice input disabled (ffmpeg missing)] Type response below and press [ENTER]\033[0m")
            user_input = input("\033[94m> \033[0m").strip()
            
            if user_input.lower() in ['exit', 'quit']:
                print("\n\033[93mSocratic Session Concluded. Warm study greetings!\033[0m")
                break
                
            audio_path = None
            if not user_input:
                if not ffmpeg_available:
                    print("\033[31m⚠ Voice input is disabled. Please type your response.\033[0m")
                    user_input = "Please continue."
                else:
                    # Trigger native voice capture
                    success = record_voice("student_input.wav")
                    if success:
                        print("\033[90mTranscribing your voice response...\033[0m", end="\r")
                        transcription = transcribe_audio_gemini(api_key, selected_model, "student_input.wav")
                        # Clear the loading line and print the beautiful transcription inline!
                        print("\r\033[K", end="")
                        print(f"\033[94mYou (Spoken):\033[0m {transcription}\n")
                        user_input = transcription
                        audio_path = None # Set to None because we now have the perfect text transcription!
                    else:
                        # Fallback if recording failed or cancelled
                        user_input = "Please continue."
                
        except Exception as e:
            err_str = str(e)
            # If the selected model does not support audio modalities, fall back to text-only mode
            if "requested response modalities: audio" in err_str and use_neural_audio:
                print("\033[33m\n[Failover] Selected model does not support native audio. Switching to text-only mode...\033[0m")
                use_neural_audio = False
                continue
            # If model is rate-limited or quota is exhausted, shift to the next candidate model
            elif "quota" in err_str.lower() or "429" in err_str or "exhausted" in err_str.lower():
                try:
                    current_idx = active_candidates.index(selected_model)
                    next_idx = current_idx + 1
                    if next_idx < len(active_candidates):
                        selected_model = active_candidates[next_idx]
                        print(f"\033[33m\n[Quota Failover] Active model rate-limited/quota exceeded. Shifting to next candidate: {selected_model}...\033[0m")
                        continue
                except ValueError:
                    pass
            # If model not found, try falling back to gemini-2.5-flash or gemini-1.5-flash
            elif "not found" in err_str or "no longer available" in err_str:
                if selected_model == "gemini-3.5-flash":
                    selected_model = "gemini-2.5-flash"
                    print(f"\033[33m\n[Failover] Shifting active model to: {selected_model}...\033[0m")
                    continue
                elif selected_model == "gemini-2.5-flash":
                    selected_model = "gemini-1.5-flash"
                    print(f"\033[33m\n[Failover] Shifting active model to: {selected_model}...\033[0m")
                    continue
                
            print(f"\033[91m\n[System Error] contacting Gemini: {e}\033[0m")
            # Clear invalid keys if requested
            if "key" in err_str.lower() or "400" in err_str:
                if os.path.exists(KEY_FILE):
                    os.remove(KEY_FILE)
                print("Your local Key cache has been reset. Please run again to provide a fresh API Key.")
            break

if __name__ == "__main__":
    main()
