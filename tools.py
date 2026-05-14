import sqlite3

DB_NAME = "todo_app.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_todo(task):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO todos (task) VALUES (?)", (task,))
    conn.commit()
    # Call resequence to ensure even the very first gaps are handled if any
    conn.close()
    return f"Added task: '{task}'"

def list_todos():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, task, status FROM todos")
    todos = cursor.fetchall()
    conn.close()
    if not todos:
        return "Your To-Do list is empty."
    return "\n".join([f"{t[0]}. [{t[2]}] {t[1]}" for t in todos])

def update_todo(todo_id, task=None, status=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if task and status:
        cursor.execute("UPDATE todos SET task = ?, status = ? WHERE id = ?", (task, status, todo_id))
    elif task:
        cursor.execute("UPDATE todos SET task = ? WHERE id = ?", (task, todo_id))
    elif status:
        cursor.execute("UPDATE todos SET status = ? WHERE id = ?", (status, todo_id))
    else:
        conn.close()
        return "No updates provided."
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    if affected == 0:
        return f"No task found with ID: {todo_id}"
    return f"Updated task {todo_id}."

def mark_all_todos(status="completed"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE todos SET status = ?", (status,))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return f"Updated all {affected} tasks to {status}."

def unmark_all_todos():
    return mark_all_todos(status="pending")

def resequence_todos(cursor):
    cursor.execute("SELECT id FROM todos ORDER BY id ASC")
    rows = cursor.fetchall()
    last_id = 0
    for new_id, (old_id,) in enumerate(rows, 1):
        last_id = new_id
        if new_id != old_id:
            cursor.execute("UPDATE todos SET id = ? WHERE id = ?", (new_id, old_id))
    # Reset the auto-increment sequence so next insert is perfectly contiguous
    cursor.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'todos'", (last_id,))

def delete_todo(todo_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Handle both single ID (int) and multiple IDs (comma-separated string)
    if isinstance(todo_id, str) and "," in todo_id:
        ids = [i.strip() for i in todo_id.split(",") if i.strip().isdigit()]
        cursor.execute(f"DELETE FROM todos WHERE id IN ({','.join(ids)})")
    else:
        cursor.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    
    resequence_todos(cursor)
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    if affected == 0:
        return f"No task found with provided ID(s)."
    return f"Deleted {affected} task(s) and resequenced IDs."

def delete_all_todos():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM todos")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='todos'") # Reset autoincrement
    conn.commit()
    conn.close()
    return "All tasks deleted."

def add_memory(content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO memory (content) VALUES (?)", (content,))
    conn.commit()
    conn.close()
    return "Memory stored."

def search_memory(query):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Simple keyword search for now
    cursor.execute("SELECT content FROM memory WHERE content LIKE ?", (f"%{query}%",))
    results = cursor.fetchall()
    conn.close()
    if not results:
        return "No matching memories found."
    return "\n".join([r[0] for r in results])

def resequence_memories(cursor):
    cursor.execute("SELECT id FROM memory ORDER BY id ASC")
    rows = cursor.fetchall()
    last_id = 0
    for new_id, (old_id,) in enumerate(rows, 1):
        last_id = new_id
        if new_id != old_id:
            cursor.execute("UPDATE memory SET id = ? WHERE id = ?", (new_id, old_id))
    # Reset the auto-increment sequence so next insert is perfectly contiguous
    cursor.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'memory'", (last_id,))

def delete_memory(memory_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Handle both single ID (int) and multiple IDs (comma-separated string)
    if isinstance(memory_id, str) and "," in memory_id:
        ids = [i.strip() for i in memory_id.split(",") if i.strip().isdigit()]
        cursor.execute(f"DELETE FROM memory WHERE id IN ({','.join(ids)})")
    else:
        cursor.execute("DELETE FROM memory WHERE id = ?", (memory_id,))
    
    resequence_memories(cursor)
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    if affected == 0:
        return f"No memory found with provided ID(s)."
    return f"Deleted {affected} memory/memories and resequenced IDs."

def delete_all_memories():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM memory")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='memory'") # Reset autoincrement
    conn.commit()
    conn.close()
    return "All memories deleted."

def update_memory(memory_id, content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE memory SET content = ? WHERE id = ?", (content, memory_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    if affected == 0:
        return f"No memory found with ID: {memory_id}"
    return f"Updated memory {memory_id}."

if __name__ == "__main__":
    init_db()
