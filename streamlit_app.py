import streamlit as st
import os
import json
import sqlite3
import requests
import hashlib
import re
from dotenv import load_dotenv, set_key
import google.generativeai as genai
from tools import init_db, add_todo, list_todos, update_todo, delete_todo, delete_all_todos, add_memory, search_memory, delete_memory, delete_all_memories, update_memory, mark_all_todos, unmark_all_todos
from voice import transcribe_audio_local
import ollama

# --- Config & Initialization ---
st.set_page_config(page_title="AI Productivity Agent", page_icon="🎙️", layout="wide", initial_sidebar_state="expanded")
init_db()
load_dotenv()
CONFIG_FILE = "settings_cache.json"

def load_settings():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f: return json.load(f)
        except: pass
    return {"provider": "Gemini", "ollama_model": ""}

def save_settings(settings):
    with open(CONFIG_FILE, "w") as f: json.dump(settings, f)

cached = load_settings()

CHAT_HISTORY_FILE = "chat_history.json"

def load_chat_history():
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, "r") as f: return json.load(f)
        except: pass
    return []

def save_chat_history(messages):
    with open(CHAT_HISTORY_FILE, "w") as f: json.dump(messages, f)

if "messages" not in st.session_state:
    st.session_state.messages = load_chat_history()
if "processed_hashes" not in st.session_state:
    st.session_state.processed_hashes = set()
if "pending_input" not in st.session_state:
    st.session_state.pending_input = None
if "db_updated" not in st.session_state:
    st.session_state.db_updated = False

# Sync widget states with DB BEFORE they render to ensure immediate UI updates
if st.session_state.db_updated:
    try:
        conn = sqlite3.connect("todo_app.db")
        cur = conn.cursor()
        cur.execute("SELECT id, status FROM todos")
        for tid, status_val in cur.fetchall():
            st.session_state[f"chk_{tid}"] = (status_val == "completed")
        conn.close()
    except:
        pass
    st.session_state.db_updated = False

# --- Helper: get current todos & memories for context ---
def get_context_string():
    conn = sqlite3.connect("todo_app.db")
    cur = conn.cursor()
    cur.execute("SELECT id, task, status FROM todos ORDER BY id ASC")
    todos = cur.fetchall()
    cur.execute("SELECT id, content FROM memory ORDER BY id ASC")
    memories = cur.fetchall()
    conn.close()

    ctx = "\n\nCURRENT STATE:\n"
    if todos:
        ctx += "TODOS:\n"
        for tid, task, status in todos:
            ctx += f"  - ID {tid}: \"{task}\" [{status}]\n"
    else:
        ctx += "TODOS: (empty)\n"
    if memories:
        ctx += "MEMORIES:\n"
        for mid, content in memories:
            ctx += f"  - ID {mid}: \"{content}\"\n"
    else:
        ctx += "MEMORIES: (empty)\n"
    return ctx

# --- Fallback intent parser ---
def fallback_intent_parser(ai_text, messages):
    """Parse AI's natural language response and execute actions it described but forgot to [TOOL:] call."""
    t = ai_text.lower()
    user_msg = messages[-1]["content"].lower() if messages else ""
    current_turn = f"{user_msg} {t}"
    
    # Gather conversational context from the last 3 messages to handle pronouns like "it"
    recent_context = " ".join([m["content"] for m in messages[-3:]]).lower() if messages else ""
    t_full = f"{recent_context} {t}"
    
    for old, new in [('\u201c', '"'), ('\u201d', '"'), ('\u2018', "'"), ('\u2019', "'"), ('\u00ab', '"'), ('\u00bb', '"')]:
        t = t.replace(old, new)
        t_full = t_full.replace(old, new)
        current_turn = current_turn.replace(old, new)
    
    conn = sqlite3.connect("todo_app.db")
    cur = conn.cursor()
    cur.execute("SELECT id, task, status FROM todos ORDER BY id ASC")
    all_todos = cur.fetchall()
    cur.execute("SELECT id, content FROM memory ORDER BY id ASC")
    all_memories = cur.fetchall()
    
    actions_taken = []
    
    # Common words that shouldn't trigger a match on their own
    stop_words = {"buy", "the", "a", "an", "some", "today", "tomorrow", "yesterday", "my", "your", "to", "for", "do", "task", "todo", "get", "make"}
    
    # 1. UNMARK / REVERT TO PENDING
    # Intent MUST be in the current turn to avoid bleeding from previous messages
    is_unmark = any(w in current_turn for w in ["unmark", "pending", "revert", "undo", "un-mark", "uncomplete", "un-complete", "incomplete"])
    if is_unmark:
        matched = False
        for tid, task, status in all_todos:
            tl = task.lower()
            core_words = [w for w in tl.split() if w not in stop_words and len(w) > 2]
            if tl in t_full or (core_words and any(w in t_full for w in core_words)):
                if status == "completed":
                    update_todo(tid, status="pending")
                    actions_taken.append(f"Unmarked '{task}'")
                    matched = True
        
        # Pronoun Fallback
        if not matched:
            for tid, task, status in reversed(all_todos):
                if status == "completed":
                    update_todo(tid, status="pending")
                    actions_taken.append(f"Unmarked '{task}' (Auto-matched)")
                    break
    
    # 2. MARK COMPLETE (only if not unmark)
    is_mark = any(w in current_turn for w in ["mark", "complete", "as done", "as completed"]) and not is_unmark
    if is_mark:
        matched = False
        for tid, task, status in all_todos:
            tl = task.lower()
            core_words = [w for w in tl.split() if w not in stop_words and len(w) > 2]
            if tl in t_full or (core_words and any(w in t_full for w in core_words)):
                if status != "completed":
                    update_todo(tid, status="completed")
                    actions_taken.append(f"Completed '{task}'")
                    matched = True
                    
        # Pronoun Fallback
        if not matched:
            for tid, task, status in reversed(all_todos):
                if status != "completed":
                    update_todo(tid, status="completed")
                    actions_taken.append(f"Completed '{task}' (Auto-matched)")
                    break
    
    # 3. DELETE MEMORY (specific or remaining)
    is_del_mem = any(p in current_turn for p in ["delete memory", "delete the memory", "remaining memory", "remove memory", "delete the remaining memory"])
    if is_del_mem:
        matched = False
        for mid, content in reversed(all_memories):
            if content.lower() in t_full:
                delete_memory(mid)
                actions_taken.append(f"Deleted memory '{content}'")
                matched = True
                break
        if not matched and all_memories:
            # Fallback to deleting the last memory
            delete_memory(all_memories[-1][0])
            actions_taken.append(f"Deleted remaining memory '{all_memories[-1][1]}'")
    
    # 4. DELETE DUPLICATE MEMORIES
    if "duplicate" in current_turn and "memor" in current_turn:
        cur.execute("SELECT content, GROUP_CONCAT(id) FROM memory GROUP BY content HAVING COUNT(*) > 1")
        for content, ids in cur.fetchall():
            for dup_id in ids.split(",")[1:]:
                delete_memory(int(dup_id))
                actions_taken.append(f"Deleted duplicate memory '{content}'")
    
    # 5. DELETE TODO
    is_del_todo = any(p in current_turn for p in ["delete", "remove"]) and not is_del_mem
    if is_del_todo:
        matched = False
        for tid, task, status in reversed(all_todos):
            tl = task.lower()
            core_words = [w for w in tl.split() if w not in stop_words and len(w) > 2]
            if tl in t_full or (core_words and any(w in t_full for w in core_words)):
                delete_todo(tid)
                actions_taken.append(f"Deleted task '{task}'")
                matched = True
                break
        
        if not matched and all_todos:
            last_tid, last_task, _ = all_todos[-1]
            delete_todo(last_tid)
            actions_taken.append(f"Deleted task '{last_task}' (Auto-matched)")

    # 6. ADD TODO
    is_add_todo_intent = any(w in current_turn for w in ["add", "create"]) and "memor" not in current_turn
    if is_add_todo_intent:
        add_match = re.search(r'["\'](.+?)["\']', current_turn)
        if add_match:
            add_todo(add_match.group(1))
            actions_taken.append(f"Added todo '{add_match.group(1)}'")
    
    # 7. ADD MEMORY  
    is_add_mem_intent = any(w in current_turn for w in ["add", "store", "save"]) and "memor" in current_turn
    if is_add_mem_intent:
        mem_match = re.search(r'["\'](.+?)["\']', current_turn)
        if mem_match:
            add_memory(mem_match.group(1))
            actions_taken.append(f"Added memory '{mem_match.group(1)}'")

    # 8. UPDATE MEMORY
    is_update_mem_intent = any(w in current_turn for w in ["update", "change", "edit"]) and "memor" in current_turn
    if is_update_mem_intent and all_memories:
        update_mem_match = re.search(r'["\'](.+?)["\']', current_turn)
        if update_mem_match:
            last_mid, old_content = all_memories[-1]
            update_memory(last_mid, update_mem_match.group(1))
            actions_taken.append(f"Updated memory to '{update_mem_match.group(1)}'")
    
    conn.close()
    if actions_taken:
        st.toast(f"Fallback executed: {', '.join(actions_taken)}")
    return actions_taken

# CSS
st.markdown("""
<style>
    section[data-testid="stSidebar"] {
        overflow: hidden !important;
    }
    /* Custom Title without breaking the sidebar */
    [data-testid="stHeader"] {
        display: none !important;
    }
    .custom-title-container {
        padding: 1rem 0 1rem 0 !important;
        margin-top: -40px !important;
        border-bottom: 1px solid rgba(250, 250, 250, 0.1) !important;
        background-color: transparent !important;
    }
    .custom-title-container h1 {
        margin: 0 !important;
        padding: 0 !important;
        font-size: 2.25rem !important;
        font-weight: 700 !important;
        color: white !important;
    }
    .main .block-container {
        padding-top: 40px !important;
        padding-bottom: 80px !important;
    }
    /* Shrink chat input to make room for mic on the right */
    .stChatInput {
        margin-right: 50px !important;
    }
    /* Position native audio input fixed at bottom-right, next to chat bar */
    .stAudioInput {
        position: fixed !important;
        bottom: 60px !important;
        right: 70px !important;
        z-index: 999 !important;
        width: 45px !important;
        height: 45px !important;
        min-height: 45px !important;
        border-radius: 50% !important;
        overflow: hidden !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
    }
    .stAudioInput button {
        width: 100% !important;
        height: 100% !important;
        padding: 0 !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
    }
    /* Hide the timer/text so the button shrinks to just the icon */
    .stAudioInput button span {
        display: none !important;
    }
    /* Remove the default right-margin from the icon so it sits dead center */
    .stAudioInput button svg {
        margin: 0 !important;
        transform: translateY(2px) !important; /* Optical centering nudge */
    }
    /* Hide playback artifacts AFTER recording, without breaking recording controls */
    .stAudioInput audio {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="custom-title-container"><h1>🤖 AI Productivity Agent</h1></div>', unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.subheader("⚙️ Settings")
    provider = st.selectbox("LLM", ["Gemini", "Ollama (Local)"], index=0 if cached["provider"] == "Gemini" else 1)
    
    if provider == "Gemini":
        api_key = os.getenv("GOOGLE_API_KEY", "")
        new_key = st.text_input("Gemini Key", value=api_key, type="password")
        if st.button("Save Key"):
            set_key(".env", "GOOGLE_API_KEY", new_key)
            os.environ["GOOGLE_API_KEY"] = new_key
            save_settings({"provider": "Gemini", "ollama_model": ""})
            st.rerun()
    else:
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=1).json()
            all_models = resp.get('models', [])
            models = [m['name'] for m in all_models if not any(x in m['name'].lower() for x in ["embed", "bert", "nomic", "mxbai"])]
            selected_m = st.selectbox("Ollama Model", models, index=models.index(cached["ollama_model"]) if cached["ollama_model"] in models else 0)
            if selected_m != cached["ollama_model"]:
                save_settings({"provider": "Ollama (Local)", "ollama_model": selected_m})
        except: st.error("Ollama Offline")

    st.divider()
    
    # Task Board
    st.subheader("✅ Task Board")
    conn = sqlite3.connect("todo_app.db")
    cur = conn.cursor()
    cur.execute("SELECT id, task, status FROM todos ORDER BY id ASC")
    for tid, task, status in cur.fetchall():
        is_done = status == "completed"
        with st.container(border=True):
            c1, c2, c3 = st.columns([0.08, 0.62, 0.3], vertical_alignment="center")
            checked = c1.checkbox(" ", value=is_done, key=f"chk_{tid}", label_visibility="collapsed")
            if checked != is_done:
                update_todo(tid, status="completed" if checked else "pending")
                st.session_state.db_updated = True
                st.rerun()
            task_display = task
            c2.caption(f"{task_display} `#{tid}`")
            if c3.button("✕", key=f"del_{tid}", type="primary"):
                delete_todo(tid); st.rerun()
    
    st.divider()
    
    # Memory
    st.subheader("🧠 Memory")
    cur.execute("SELECT id, content FROM memory ORDER BY id ASC")
    for mid, content in cur.fetchall():
        with st.container(border=True):
            c_mem, c_del = st.columns([0.8, 0.2], vertical_alignment="center")
            c_mem.caption(f"{content} `#{mid}`")
            if c_del.button("✕", key=f"mdel_{mid}", type="primary"):
                delete_memory(mid); st.rerun()
    conn.close()
    
    st.divider()

    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.processed_hashes = set()
        save_chat_history([])
        st.rerun()

# --- Chat Area ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Native Mic recorder (CSS positions it next to chat bar)
audio_data = st.audio_input("Record", label_visibility="collapsed", key="voice_recorder")

# Process voice input
user_input = None
if audio_data:
    audio_bytes = audio_data.read()
    file_hash = hashlib.md5(audio_bytes).hexdigest()
    if file_hash not in st.session_state.processed_hashes:
        with st.spinner("Transcribing..."):
            user_input = transcribe_audio_local(audio_bytes)
            st.session_state.processed_hashes.add(file_hash)

# Chat input - auto pins to bottom
if prompt := st.chat_input("Type your message here..."):
    user_input = prompt

# STEP 1: If new input arrives, save it and rerun so the user message renders immediately
if user_input:
    text_hash = hashlib.md5(user_input.encode()).hexdigest()
    if text_hash not in st.session_state.processed_hashes:
        st.session_state.processed_hashes.add(text_hash)
        st.session_state.messages.append({"role": "user", "content": user_input})
        save_chat_history(st.session_state.messages)
        st.session_state.pending_input = user_input
        st.rerun()  # Rerun NOW so user message appears instantly

# STEP 2: If there's a pending input, process the AI response (user message is already visible)
if st.session_state.pending_input:
    pending = st.session_state.pending_input
    st.session_state.pending_input = None  # Clear it so we don't loop
    
    # Build dynamic system prompt with current todos & memories
    context = get_context_string()
    
    SYSTEM_PROMPT = f"""You are a Personal Assistant that manages todos and memories. You MUST use [TOOL:] commands to perform actions.

RULES:
1. TODOS and MEMORIES are separate lists. Only use update_todo/delete_todo on TODOS. Only use delete_memory on MEMORIES.
2. Use FUZZY MATCHING. If the user says "banana stew" and you have "bananas", MATCH IT. If they say "trash" and you have "take the trash out", MATCH IT. Be aggressive about matching typos or variations.
3. If the user says they "did" or "completed" something, update its status to "completed". If it is NOT in TODOS but IS in MEMORIES, delete the memory and tell the user.
4. If NO match exists anywhere even with fuzzy matching, say "I don't see that in your todos or memories."
5. NEVER pick an unrelated task. "trash" does NOT match "buy milk".
6. If the user asks to act on ALL tasks (e.g. "mark all tasks", "unmark all"), use the mark_all_todos, unmark_all_todos, or delete_all_todos tools. Do not loop through them one by one.

HOW TO RESPOND:
- Write a short friendly message AND include [TOOL:] commands. Example:
  "Marked 'buy milk' as done! [TOOL: update_todo(todo_id=1, status="completed")]"
- For multiple actions, include multiple [TOOL:] on separate lines:
  "Fixed! [TOOL: update_todo(todo_id=1, status="pending")]
  [TOOL: delete_memory(memory_id=2)]"
- WARNING: If you describe an action without a [TOOL:] command, NOTHING happens. The [TOOL:] is what actually executes. Never list actions without [TOOL:] commands.
- Format: [TOOL: function_name(param="value")] — always use named parameters.
{context}"""

    with st.chat_message("assistant"):
        try:
            ai_text = ""
            with st.spinner("Thinking..."):
                if provider == "Gemini":
                    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                    model = genai.GenerativeModel('gemini-2.5-flash', 
                        tools=[add_todo, list_todos, update_todo, delete_todo, delete_all_todos, add_memory, search_memory, delete_memory, delete_all_memories, update_memory, mark_all_todos, unmark_all_todos],
                        system_instruction=SYSTEM_PROMPT)
                    chat = model.start_chat(enable_automatic_function_calling=True)
                    response = chat.send_message(pending)
                    ai_text = response.text
                else:
                    # Build conversation history for Ollama
                    ollama_messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
                    for prev_msg in st.session_state.messages:
                        ollama_messages.append({'role': prev_msg['role'], 'content': prev_msg['content']})
                    
                    resp = ollama.chat(model=selected_m, messages=ollama_messages)
                    ai_text = resp['message']['content']
                    
                    # Tool Parser for Ollama - handle MULTIPLE tool calls
                    tool_calls = re.findall(r"\[TOOL:\s*(\w+)\((.*)\)\]", ai_text)
                    tools_successfully_executed = 0
                    
                    for match in tool_calls:
                        f, p = match[0], match[1]
                        params = {}
                        
                        # Try parsing with quotes first
                        for k, v in re.findall(r"(\w+)=['\"]([^'\"]*)['\"]", p): params[k] = v
                        for k, v in re.findall(r"(\w+)=(\d+)", p): params[k] = int(v)
                        
                        # Handle unquoted strings (like status=pending)
                        if "status" not in params:
                            unquoted_status = re.search(r"status=([a-zA-Z]+)", p)
                            if unquoted_status:
                                params["status"] = unquoted_status.group(1)
                                
                        # Fallback for positional arguments if parameter names are missing
                        if not params:
                            pos_str = re.search(r"['\"]([^'\"]*)['\"]", p)
                            if pos_str:
                                if f == "add_todo": params["task"] = pos_str.group(1)
                                elif f == "add_memory": params["content"] = pos_str.group(1)
                            pos_int = re.search(r"(\d+)", p)
                            if pos_int and not pos_str:
                                if f in ["delete_todo", "update_todo"]: params["todo_id"] = int(pos_int.group(1))
                                elif f == "delete_memory": params["memory_id"] = int(pos_int.group(1))

                        # Align parameter names
                        if "id" in params and f in ["delete_memory", "update_memory"]: params["memory_id"] = params.pop("id")
                        if "id" in params and f in ["delete_todo", "update_todo"]: params["todo_id"] = params.pop("id")
                        
                        if f in ["add_todo", "update_todo"]:
                            for alias in ["description", "name", "title", "content"]:
                                if alias in params: params["task"] = params.pop(alias)
                                
                        if f in ["add_memory", "update_memory"]:
                            for alias in ["text", "description", "note", "memory"]:
                                if alias in params: params["content"] = params.pop(alias)
                                
                        # Filter invalid parameters to prevent TypeError crashes
                        valid_params = {
                            "add_todo": ["task"],
                            "list_todos": [],
                            "update_todo": ["todo_id", "task", "status"],
                            "delete_todo": ["todo_id"],
                            "delete_all_todos": [],
                            "add_memory": ["content"],
                            "search_memory": ["query"],
                            "delete_memory": ["memory_id"],
                            "delete_all_memories": [],
                            "update_memory": ["memory_id", "content"],
                            "mark_all_todos": [],
                            "unmark_all_todos": []
                        }
                        if f in valid_params:
                            params = {k: v for k, v in params.items() if k in valid_params[f]}
                        
                        tool_map = {"add_todo": add_todo, "update_todo": update_todo, "delete_todo": delete_todo, "delete_all_todos": delete_all_todos, "add_memory": add_memory, "delete_memory": delete_memory, "delete_all_memories": delete_all_memories, "update_memory": update_memory, "mark_all_todos": mark_all_todos, "unmark_all_todos": unmark_all_todos}
                        if f in tool_map:
                            # Strict required parameter validation to prevent crashes from AI hallucinations
                            missing_args = False
                            if f in ["update_todo", "delete_todo"] and "todo_id" not in params: missing_args = True
                            if f in ["update_memory", "delete_memory"] and "memory_id" not in params: missing_args = True
                            if f == "add_todo" and "task" not in params: missing_args = True
                            if f == "add_memory" and "content" not in params: missing_args = True
                            
                            if not missing_args:
                                res = tool_map[f](**params)
                                if res and "No updates provided" not in res and "No task found" not in res:
                                    tools_successfully_executed += 1
                    
                    # FALLBACK: If AI described actions but forgot [TOOL:] calls OR if its tool calls were malformed and failed
                    if tools_successfully_executed == 0 and ai_text:
                        acts = fallback_intent_parser(ai_text, st.session_state.messages)
                        if acts:
                            pass # st.toast handles it
                    
            # Clean up TOOL calls for display
            display_text = re.sub(r"\[TOOL:.*?\]", "", ai_text).strip()
            if not display_text:
                display_text = "Done! ✅"

            st.write(display_text)
            st.session_state.messages.append({"role": "assistant", "content": display_text})
            save_chat_history(st.session_state.messages)
            
            # FORCE CHECKBOX STATES TO SYNC WITH NEW DB STATE
            # Defer cleanup to the top of the next run to avoid Streamlit instantiation errors
            st.session_state.db_updated = True
                    
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
