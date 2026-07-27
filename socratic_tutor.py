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

# Config files
KEY_FILE = ".tutor_key"
COURSE_DATA_FILE = "course_data.js"
WAV_OUTPUT_FILE = "tutor_response.wav"

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

def load_curriculum():
    if not os.path.exists(COURSE_DATA_FILE):
        print(f"Error: {COURSE_DATA_FILE} not found. Please run this script in the same directory as course_data.js")
        sys.exit(1)
    
    try:
        with open(COURSE_DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract JSON Array from course_data.js (which contains "const COURSE_DATA = [ ... ];")
        # Find first '[' and last ']'
        start_idx = content.find('[')
        end_idx = content.rfind(']')
        if start_idx == -1 or end_idx == -1:
            raise ValueError("Could not locate JSON array structure inside course_data.js")
        
        json_str = content[start_idx:end_idx + 1]
        raw_list = json.loads(json_str)
        
        # Format list into expected dict structure: { "Path Title": { "Module Title": "Module Content" } }
        curriculum_dict = {}
        for path in raw_list:
            path_title = path["title"]
            curriculum_dict[path_title] = {}
            for module in path["modules"]:
                mod_title = module["title"]
                curriculum_dict[path_title][mod_title] = module["content"]
                
        return curriculum_dict
    except Exception as e:
        print(f"Error parsing curriculum database: {e}")
        sys.exit(1)

def play_pcm_audio(audio_base64, sample_rate=24000):
    try:
        pcm_bytes = base64.b64decode(audio_base64)
        
        # Write PCM bytes as a standard WAV file (mono, 16-bit = 2 bytes per sample, 24kHz)
        with wave.open(WAV_OUTPUT_FILE, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
            
        # Play natively on macOS via afplay (built-in command-line audio player)
        subprocess.run(["afplay", WAV_OUTPUT_FILE])
        
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
        
    # 2. Select Model and Voice
    voice_name = "Aoede" # Warm female default
    
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
    curriculum = load_curriculum()
    
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
3. Be CONCISE (no more than 2-3 sentences per turn) because your responses will be spoken aloud.
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
            # Query Gemini (pass audio input path if the turn is a voice response)
            if user_input != "[START_QUIZ]":
                print("\033[90mThinking...\033[0m", end="\r")
                
            ai_text, audio_base64 = query_gemini(
                api_key, 
                selected_model, 
                system_instruction, 
                user_input if user_input != "[START_QUIZ]" else "Begin the Socratic quiz, introduce yourself warmly, and ask the first foundational question.",
                chat_history,
                voice_name,
                audio_path
            )
            
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
                played = play_pcm_audio(audio_base64)
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
