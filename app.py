import os
import google.generativeai as genai
from dotenv import load_dotenv
from tools import add_todo, list_todos, update_todo, delete_todo, add_memory, search_memory, init_db
from voice import speak, listen

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY not found in .env file.")
    # For the purpose of this assignment, we expect the user to have this set.
    # In a real scenario, we'd handle this more gracefully.
else:
    genai.configure(api_key=GOOGLE_API_KEY)

# Define tools for the agent
# Using function calling capabilities of Gemini
tools = [
    add_todo,
    list_todos,
    update_todo,
    delete_todo,
    add_memory,
    search_memory
]

SYSTEM_PROMPT = """
You are a helpful and efficient Voice-Based AI Personal Assistant. 
Your primary roles are:
1. Manage the user's To-Do list using the provided tools (add_todo, list_todos, update_todo, delete_todo).
2. Remember important facts or events mentioned by the user using add_memory and retrieve them using search_memory.
3. Be conversational and friendly, but concise.

When a user tells you something important (like a birthday, a preference, or an event), use add_memory to save it.
When a user asks about something you might have remembered, use search_memory.
Always confirm actions (e.g., "I've added that to your list") via voice.
"""

model = genai.GenerativeModel(
    model_name='gemini-2.5-flash',
    tools=tools,
    system_instruction=SYSTEM_PROMPT
)

def main():
    init_db()
    chat = model.start_chat(enable_automatic_function_calling=True)
    
    speak("Hello! I am your AI assistant. I can manage your To-Do list and remember things for you. What can I do for you?")
    
    while True:
        user_input = listen()
        
        if not user_input:
            continue
            
        if any(exit_word in user_input.lower() for exit_word in ["exit", "stop", "quit", "goodbye"]):
            speak("Goodbye! Have a great day.")
            break
            
        try:
            response = chat.send_message(user_input)
            speak(response.text)
        except Exception as e:
            print(f"Error: {e}")
            speak("I encountered an error processing your request.")

if __name__ == "__main__":
    main()
