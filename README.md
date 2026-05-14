# AI Productivity Agent

A voice-enabled AI personal assistant built with **Streamlit** that manages your To-Do list, stores memories, and understands natural language — powered by **Google Gemini** or **Ollama** (local LLMs).

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-red?logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

| Feature | Description |
|---|---|
| **Voice Input** | Record voice commands via the built-in microphone button (transcribed locally with Whisper) |
| **Text Input** | ChatGPT-style text input bar pinned to the bottom |
| **Smart Task Board** | Add, complete, and delete tasks with natural language ("remind me to buy milk") |
| **Memory System** | Remembers facts you tell it ("remember the wifi password is guest123") and recalls them later |
| **Dual LLM Support** | Switch between Google Gemini (cloud) and Ollama (fully local/offline) |
| **Persistent Chat** | Chat history survives page reloads — stored locally in JSON |
| **Auto-Contiguous IDs** | Task/memory IDs always stay sequential (1, 2, 3…) with no gaps after deletions |
| **Fault-Tolerant Agent** | Built-in Intent Fallback Parser and Parameter Sandbox protects against AI hallucinations |

---

## 🧠 Hybrid Agentic Architecture
Running local, smaller LLMs (like `gemma3:12b`) means dealing with AI hallucinations, forgotten formatting, and missing parameters. This app implements a dual-layer Agentic safety net:

1. **Parameter Firewall:** When the LLM outputs a tool call (e.g. `[TOOL: update_todo]`), the backend intercepts it, remaps hallucinated aliases (e.g. `description` -> `task`), and strips out unaccepted arguments before execution to prevent fatal Python `TypeErrors`.
2. **Intent Fallback Parser:** If the LLM forgets its `[TOOL:]` syntax entirely and just speaks in natural language (e.g. *"I've marked wash clothes as done"*), the custom Regex parser steps in. It strips stop-words to find core nouns, calculates the linguistic intent, and autonomously executes the correct SQLite database commands without crashing.

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Ollama** *(optional, for local LLM)*: [Download Ollama](https://ollama.com/)
- **Google Gemini API Key** *(optional, for cloud LLM)*: [Get a key](https://aistudio.google.com/app/apikey)

> You need **at least one** of Ollama or Gemini configured.

### 1. Clone & Install

```bash
git clone https://github.com/varun-aahil/aI-productivity-voice-agent.git
cd aI-productivity-voice-agent
pip install -r requirements.txt
```

> **Windows users:** If `PyAudio` fails, try:
> ```bash
> pip install pipwin && pipwin install pyaudio
> ```

### 2. Configure

**Option A — Gemini (Cloud):**
Create a `.env` file:
```
GOOGLE_API_KEY=your_api_key_here
```
Or enter the key directly in the app sidebar.

**Option B — Ollama (Local):**
```bash
ollama pull gemma3:12b
```
No API key needed. Just make sure Ollama is running.

### 3. Run

```bash
streamlit run streamlit_app.py
```

The app opens at [http://localhost:8501](http://localhost:8501).

---

## 📖 Usage

### Natural Language Commands

| Say / Type | What Happens |
|---|---|
| "Add buy groceries to my list" | Creates a new task |
| "I bought the milk" | Marks "buy milk" as completed |
| "I'm not going to the gym anymore" | Deletes the gym task |
| "Delete the duplicate tasks" | Removes duplicates intelligently |
| "Remember the project deadline is Friday" | Stores as a memory |
| "When is the project deadline?" | Recalls from memory |
| "Delete all tasks" | Clears the entire task board |
| "Forget all memories" | Clears all stored memories |

### CLI Version

For a terminal-only experience (Gemini only):
```bash
python app.py
```

---

## 🏗️ Architecture

```
├── streamlit_app.py   # Main Streamlit UI + chat logic
├── tools.py           # SQLite CRUD for tasks & memories
├── voice.py           # Whisper transcription + gTTS
├── voice_web.py       # Legacy web voice utilities
├── app.py             # CLI-only version (Gemini)
├── requirements.txt   # Python dependencies
├── PRD.md             # Product requirements doc
└── .env               # API keys (not committed)
```

| Component | Tech |
|---|---|
| Frontend | Streamlit (dark theme, custom CSS) |
| LLM | Google Gemini 2.5 Flash / Ollama (any model) |
| Database | SQLite (`todo_app.db`) |
| STT | Faster Whisper (local, CPU) |
| TTS | gTTS (Google Text-to-Speech) |

---

## 🔧 Troubleshooting

- **Ollama Connection Error**: Ensure Ollama is running (`ollama serve`) before starting the app.
- **Mic Not Working**: Make sure your browser has microphone permissions enabled.
- **PyAudio Install Issues**: On Windows, use `pipwin install pyaudio`. On Linux, install `portaudio19-dev` first.
- **Whisper Model Download**: On first run, Faster Whisper downloads the `base` model (~150MB). This is automatic.

---

## 📄 License

MIT
