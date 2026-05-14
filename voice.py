import io
import os
from gtts import gTTS
from faster_whisper import WhisperModel
import speech_recognition as sr
import pyttsx3

# Initialize Whisper Model (Local, high accuracy)
# We use 'tiny' or 'base' for speed on CPU
try:
    # Use CPU by default, int8 quantization for low memory
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
except Exception as e:
    print(f"Whisper initialization failed: {e}")
    whisper_model = None

def transcribe_audio_local(audio_bytes):
    """Accurate local transcription using Faster Whisper"""
    if not whisper_model or not audio_bytes:
        return None
    
    try:
        # Faster Whisper can read bytes directly from a buffer
        segments, info = whisper_model.transcribe(io.BytesIO(audio_bytes), beam_size=5)
        text = " ".join([segment.text for segment in segments]).strip()
        return text if text else None
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return None

def speak_to_bytes(text):
    """Web Speak using gTTS, returns audio bytes"""
    try:
        if not text: return None
        tts = gTTS(text=text, lang='en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception as e:
        print(f"gTTS error: {e}")
        return None

# Keep legacy methods for CLI compatibility
def listen():
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source)
        return recognizer.recognize_google(audio)
    except: return None

def speak(text):
    print(f"AI: {text}")
    try:
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except: pass
