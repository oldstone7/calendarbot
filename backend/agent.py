import os
import re
from dotenv import load_dotenv
import google.generativeai as genai
from langchain.agents import Tool
from backend.calendar_tools import (
    get_calendar_service, check_availability,
    book_slot, delete_event, reschedule_event
)

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# --- Chat Wrapper ---
class GeminiWrapper:
    def __init__(self, model, system_message=""):
        self.chat = model.start_chat(history=[])
        if system_message:
            self.chat.send_message(system_message)

    def send(self, message: str) -> str:
        response = self.chat.send_message(message)
        return response.text

# --- Tools ---
def check_events_tool(date: str) -> str:
    service = get_calendar_service(os.getenv("GOOGLE_CREDENTIALS_PATH"))
    calendar_id = os.getenv("CALENDAR_ID")
    events = check_availability(service, calendar_id, date)
    if not events:
        return f"No events on {date}."
    return "\n".join([f"- {e['summary']} at {e['start']['dateTime']}" for e in events])

def book_event_tool(info: str) -> str:
    print("[DEBUG] book_event_tool called with:", info)
    service = get_calendar_service(os.getenv("GOOGLE_CREDENTIALS_PATH"))
    calendar_id = os.getenv("CALENDAR_ID")

    try:
        summary, date, start, end = [x.strip() for x in info.split(',')]

        # Fetch events on the same day
        events = check_availability(service, calendar_id, date)

        # Check for time conflict
        start_dt = f"{date}T{start}:00"
        end_dt = f"{date}T{end}:00"

        for event in events:
            existing_start = event.get('start', {}).get('dateTime', '')
            existing_end = event.get('end', {}).get('dateTime', '')

            if existing_start < end_dt and start_dt < existing_end:
                return f"⚠️ Cannot book '{summary}' from {start} to {end} on {date} because it overlaps with '{event.get('summary')}'."

        result = book_slot(service, calendar_id, summary, date, start, end)
        return f"📅 Booked: '{summary}' from {start} to {end} on {date}."

    except Exception as e:
        print("❌ Error in booking:", e)
        return f"❌ Booking failed: {str(e)}"

def delete_event_tool(info: str) -> str:
    print("[DEBUG] delete_event_tool called with:", info)
    parts = [x.strip() for x in info.split(',')]
    service = get_calendar_service(os.getenv("GOOGLE_CREDENTIALS_PATH"))
    calendar_id = os.getenv("CALENDAR_ID")

    if len(parts) == 3:
        summary, date, time = parts
        return delete_event(service, calendar_id, summary, date, time)
    elif len(parts) == 2:
        summary, date = parts
        return delete_event(service, calendar_id, summary, date)
    else:
        return "❌ Invalid delete format. Use: Summary,Date[,Time]"

def reschedule_event_tool(info: str) -> str:
    print("[DEBUG] reschedule_event_tool called with:", info)
    service = get_calendar_service(os.getenv("GOOGLE_CREDENTIALS_PATH"))
    calendar_id = os.getenv("CALENDAR_ID")
    summary, old_date, new_date, start, end = info.split(',')
    return reschedule_event(service, calendar_id, summary.strip(), old_date.strip(), new_date.strip(), start.strip(), end.strip())

tools = [
    Tool(name="CheckAvailability", func=check_events_tool, description="Check events on a date (YYYY-MM-DD)"),
    Tool(name="BookEvent", func=book_event_tool, description="Book event with info: Summary,Date,StartTime,EndTime"),
    Tool(name="DeleteEvent", func=delete_event_tool, description="Delete event with info: Summary,Date,Time"),
    Tool(name="RescheduleEvent", func=reschedule_event_tool, description="Reschedule an event with info: Summary,OldDate,NewDate,StartTime,EndTime"),
]

# --- Agent ---
class FakeAgent:
    def __init__(self, tools, llm: GeminiWrapper):
        self.tools = {tool.name: tool for tool in tools}
        self.llm = llm

    def run(self, message: str):
        tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in self.tools.values()])
        tool_hint = (
            "You are a helpful AI assistant named CalendarBot that helps users manage their Google Calendar.\n\n"
            "Respond like a human assistant, but always support your actions with tool calls.\n\n"
            "Rules:\n"
            "- Always use `CheckAvailability(date)` when the user asks about events on a day. Never assume the schedule.\n"
            "- You may use multiple tools in a single reply if the user asks to book, delete, or reschedule multiple events.\n"
            "- If the user gives a date like 'July 5' without a year, confirm the year or suggest 2025.\n\n"
            "Time Logic:\n"
            "- If the user says 'move the meeting 2 hours later' or 'shift it 1 hour earlier', adjust both start and end times correctly.\n"
            "- Example: 'Team Sync' at 11:00–12:00, moved 1 hour later → becomes 12:00–13:00.\n"
            "- You may adjust start time by 1–2 minutes if there's a conflict, unless the user insists on exact timing.\n\n"
            "Available tools:\n"
            f"{tool_descriptions}\n\n"
            "Tool call format:\n"
            "CheckAvailability(2025-07-06)\n"
            "BookEvent(Meeting,2025-07-06,14:00,15:00)\n"
            "DeleteEvent(Meeting,2025-07-06,14:00)\n"
            "RescheduleEvent(Meeting,2025-07-06,2025-07-06,14:00,15:00)"
        )

        self.llm.send(tool_hint)
        reply = self.llm.send(f"User: {message}")
        print("[DEBUG] Initial AI reply:", reply)

        while True:
            matches = re.findall(r"(CheckAvailability|BookEvent|DeleteEvent|RescheduleEvent)\((.*?)\)", reply)
            if not matches:
                break  # No more tool calls

            for tool_name, args in matches:
                print(f"[DEBUG] Tool detected: {tool_name} with args: {args}")
                if tool_name in self.tools:
                    tool_output = self.tools[tool_name].func(args)
                    print(f"[DEBUG] Tool output: {tool_output}")
                    reply = self.llm.send(f"Here’s what I found: {tool_output}. What should I do next?")

                else:
                    reply = f"❌ Unknown tool: {tool_name}"
                    print(reply)

        return reply

# --- Initialize Agent ---
llm = GeminiWrapper(model)
agent = FakeAgent(tools, llm)
