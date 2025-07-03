import streamlit as st
import requests

st.title("📅 TailorTalk - Calendar Assistant")

backend_url = "http://localhost:8000/chat"

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).markdown(msg["content"])

user_input = st.chat_input("Ask me to book or check your calendar...")
if user_input:
    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("Thinking..."):
        try:
            res = requests.post(backend_url, json={"message": user_input})
            res.raise_for_status()
            response = res.json().get("response", "🤖 No meaningful reply.")
        except requests.exceptions.RequestException as e:
            err_str = str(e).lower()
            if "quota" in err_str or "429" in err_str:
                response = "😔 Sorry, you've exhausted our free message limit for today. Limit resets at **12:30 PM IST**."
            elif "connection refused" in err_str or "failed to establish a new connection" in err_str:
                response = "⚠️ Backend server is offline. Please try again after restarting the app."
            else:
                response = "⚠️ Something unexpected happened. Please try again in a moment."
        except Exception as e:
            response = "⚠️ Oops! Something broke internally. Please try again shortly."


    st.chat_message("assistant").markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
