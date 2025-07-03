from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime

def get_calendar_service(credentials_path):
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    return build('calendar', 'v3', credentials=creds)

def check_availability(service, calendar_id, date_str):
    date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    start = f"{date.strftime('%Y-%m-%d')}T00:00:00Z"
    end = f"{date.strftime('%Y-%m-%d')}T23:59:59Z"
    events = service.events().list(calendarId=calendar_id, timeMin=start, timeMax=end).execute()
    return events.get('items', [])

def book_slot(service, calendar_id, summary, date_str, start_time, end_time):
    try:
        print("[DEBUG] Trying to insert:", summary, date_str, start_time, end_time)

        event = {
            'summary': summary,
            'start': {'dateTime': f'{date_str}T{start_time}:00', 'timeZone': 'Asia/Kolkata'},
            'end': {'dateTime': f'{date_str}T{end_time}:00', 'timeZone': 'Asia/Kolkata'}
        }

        result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print("[DEBUG] Event successfully created:", result.get("id"))
        return result
    except Exception as e:
        print("❌ Error inserting event:", e)
        return {"error": str(e)}

def delete_event(service, calendar_id, summary, date_str, start_time=None):
    events = check_availability(service, calendar_id, date_str)
    deleted = False
    for event in events:
        event_summary = event.get("summary", "").lower()
        event_start = event.get("start", {}).get("dateTime", "")
        if summary.lower() in event_summary:
            if start_time:
                if start_time in event_start:
                    event_id = event["id"]
                    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                    deleted = True
                    break
            else:
                event_id = event["id"]
                service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
                deleted = True
                break
    if deleted:
        return f"✅ Event '{summary}' deleted on {date_str}."
    else:
        return f"❌ No matching event '{summary}' found on {date_str} with time {start_time or '[any]'}."

def reschedule_event(service, calendar_id, summary, old_date, new_date, new_start, new_end):
    events = check_availability(service, calendar_id, old_date)
    for event in events:
        if event.get("summary", "").lower() == summary.lower():
            event_id = event["id"]
            event['start']['dateTime'] = f'{new_date}T{new_start}:00'
            event['end']['dateTime'] = f'{new_date}T{new_end}:00'
            event['start']['timeZone'] = 'Asia/Kolkata'
            event['end']['timeZone'] = 'Asia/Kolkata'
            updated_event = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
            print(f"[DEBUG] Rescheduled event: {summary}")
            return f"Rescheduled '{summary}' to {new_date} from {new_start} to {new_end}"
    return f"No matching event titled '{summary}' found on {old_date}."
