import streamlit as st
import requests
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime, timedelta
import pandas as pd
from openai import OpenAI
import re

# Load environment variables from .env file
load_dotenv()

# Your Vapi API Authorization token
auth_token = os.getenv('AUTH_TOKEN')
phone_number_id = os.getenv('PHONE_NUMBER_ID')
mongo_uri = os.getenv('MONGODB_URI')
openai_api_key = os.getenv('OPENAI_API_KEY')

# Connect to MongoDB
client = MongoClient(mongo_uri)
db = client.hospital

# Ensure the user_appointments collection exists
user_appointments = db.user_appointments

# Initialize OpenAI client
openai_client = OpenAI(api_key=openai_api_key)

# Function to format datetime without year
def format_datetime(dt):
    return dt.strftime("%d %B at %I %p")

# Function to make a call
def make_call(phone_number):
    try:
        specialties_list = [specialty["name"] for specialty in db.specialties.find()]
        
        user_prompt = """
        You are a friendly and professional receptionist at Manipal Hospital. Your primary task is to schedule appointments for patients efficiently and courteously. Engage with callers in a warm, personalized manner while maintaining a professional demeanor. Use natural language and a conversational tone, adapting to the caller's style and needs.

        Begin the call with: "Thank you for calling Manipal Hospital. This is [choose a common Indian name], how may I assist you today?"

        If the caller wants to schedule an appointment, guide them through the process:

        1. Ask which medical specialty they need. We offer: {specialties}
        2. Once they choose a specialty, respond with "Ok." and provide the names of available doctors in that field.
        3. Politely collect the following information, asking each question one by one:
            - Patient's full name
            - Mobile number
            - Preferred doctor
            - Appointment type (in-person or teleconsultation)
            - Preferred date and time (our hours are 9 AM to 6 PM)

        4. Check the availability for their chosen slot. If it's available, confirm the appointment. If not, offer the next available slot or alternative dates.

        5. After booking, summarize the appointment details and ask if they need any additional information.

        Throughout the conversation:
            - Use polite phrases like "Certainly," "Of course," "I'd be happy to help with that."
            - Show empathy and patience, especially if the caller seems confused or anxious.
            - Offer to repeat information if necessary.
            - Ask clarifying questions if the caller's request is unclear.
            - Provide brief pauses as if you're checking information on a computer.

        End the call with: "Thank you for choosing Manipal Hospital. We look forward to seeing you/speaking with you on [appointment date]. Have a great day!"

        Remember, your goal is to make the caller feel valued and ensure they have a positive experience scheduling their appointment.
        """
        
        specialties_details = {}
        for specialty in db.specialties.find():
            doctor_names = [doctor["name"] for doctor in specialty["doctors"]]
            specialties_details[specialty["name"]] = doctor_names
        
        user_prompt = user_prompt.format(specialties=', '.join(specialties_list))
        for specialty, doctors in specialties_details.items():
            doctor_list_str = ', '.join([f"{i+1}. {doctor}" for i, doctor in enumerate(doctors)])
            user_prompt += f"\nFor {specialty}, the available doctors are: {doctor_list_str}."

        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json',
        }

        data = {
            'assistant': {
                "firstMessage": "Hello",
                "model": {
                    "provider": "openai",
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": user_prompt
                        }
                    ]
                },
                "voice": "jennifer-playht"
            },
            'phoneNumberId': phone_number_id,
            'customer': {
                'number': phone_number,
            },
        }

        response = requests.post('https://api.vapi.ai/call/phone', headers=headers, json=data)
        
        if response.status_code == 201:
            st.success('Call created successfully')
            return 'Call created successfully', response.json()
        else:
            st.error('Failed to create call')
            return 'Failed to create call', None
    except Exception as e:
        st.error(f"Error during making call: {str(e)}")
        return 'Error during making call', None

def book_appointment(specialty, doctor_name, appointment_type, time_slot, user_name, mobile_number):
    try:
        specialties = db.specialties
        specialty_doc = specialties.find_one({"name": specialty})
        if not specialty_doc:
            st.error("Specialty not found")
            return False, "Specialty not found."

        if isinstance(time_slot, str):
            try:
                time_slot = parse_relative_date(time_slot)
                if time_slot < datetime.now():
                    st.error("The selected time slot is in the past. Please choose another date or time.")
                    return False, "The selected time slot is in the past. Please choose another date or time."
            except ValueError:
                st.error("Invalid date format. Please provide the date in 'dd MMM at hh PM' format.")
                return False, "Invalid date format. Please provide the date in 'dd MMM at hh PM' format."
        
        for doctor in specialty_doc["doctors"]:
            if doctor["name"] == doctor_name:
                if "booked_slots" in doctor and any(abs((datetime.strptime(existing_slot, "%d %B at %I %p") - time_slot).total_seconds()) < 3600 for existing_slot in doctor["booked_slots"]):
                    st.error("The selected time slot is already taken. Please choose another date or time.")
                    return False, "The selected time slot is already taken. Please choose another date or time."

                result = specialties.update_one(
                    {"name": specialty, "doctors.name": doctor_name},
                    {
                        "$push": {"doctors.$.booked_slots": format_datetime(time_slot)},
                        "$pull": {"doctors.$.available_slots": format_datetime(time_slot)}
                    }
                )

                if result.modified_count == 0:
                    st.error("Failed to update the database.")
                    return False, "Failed to update the database."

                appointment_details = {
                    "Name": user_name,
                    "Specialty": specialty,
                    "Doctor Name": doctor_name,
                    "Appointment Type": appointment_type,
                    "Time Slot": time_slot
                }
                save_appointment_to_excel(appointment_details)
                collect_user_info_and_save(mobile_number, user_name, specialty, doctor_name, appointment_type, time_slot)
                
                st.success("Appointment booked successfully")
                return True, "Appointment booked successfully."

        st.error("Doctor not found")
        return False, "Doctor not found."
    except Exception as e:
        st.error(f"Error during booking appointment: {str(e)}")
        return False, str(e)

def save_appointment_to_excel(appointment_details):
    try:
        df = pd.DataFrame([{
            "User Name": appointment_details["Name"],
            "Specialty": appointment_details["Specialty"],
            "Doctor Name": appointment_details["Doctor Name"],
            "Appointment Type": appointment_details["Appointment Type"],
            "Date": appointment_details["Time Slot"].strftime("%d %B at %I %p"),
        }])
        file_path = "appointments.xlsx"
        if os.path.exists(file_path):
            existing_df = pd.read_excel(file_path)
            df = pd.concat([existing_df, df], ignore_index=True)
        df.to_excel(file_path, index=False)
        st.success(f"Appointment saved to {file_path}")
    except Exception as e:
        st.error(f"Error during saving to Excel: {str(e)}")

def collect_user_info_and_save(phone_number, user_name, specialty, doctor_name, appointment_type, appointment_date):
    try:
        appointment = {
            "mobile_number": phone_number,
            "name": user_name,
            "specialty": specialty,
            "doctor_name": doctor_name,
            "appointment_type": appointment_type,
            "appointment_date": appointment_date
        }

        result = user_appointments.insert_one(appointment)
        st.success(f"Appointment for {user_name} has been saved successfully.")
        return True, "Appointment saved successfully."
    except Exception as e:
        st.error(f"Error during saving appointment: {str(e)}")
        return False, str(e)

def handle_conversation(call_id):
    transcript = fetch_transcript(call_id)
    extract_and_save_appointment_details(transcript)

def suggest_slots(specialty, doctor_name):
    specialty_doc = db.specialties.find_one({"name": specialty})
    if not specialty_doc:
        st.error("Specialty not found")
        return None, "Specialty not found."

    for doctor in specialty_doc["doctors"]:
        if doctor["name"] == doctor_name:
            available_slots = doctor.get("available_slots", [])
            booked_slots = doctor.get("booked_slots", [])
            formatted_available_slots = [format_datetime(datetime.strptime(slot, "%d %B at %I %p")) for slot in available_slots]
            formatted_booked_slots = [format_datetime(datetime.strptime(slot, "%d %B at %I %p")) for slot in booked_slots]
            return formatted_available_slots, formatted_booked_slots

    st.error("Doctor not found")
    return None, "Doctor not found."

def fetch_appointments():
    appointments = user_appointments.find()
    appointments_list = list(appointments)
    for appointment in appointments_list:
        appointment["_id"] = str(appointment["_id"])
    return pd.DataFrame(appointments_list)

def fetch_call_logs():
    url = "https://api.vapi.ai/call"
    headers = {
        'Authorization': f'Bearer {auth_token}'
    }

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        logs = response.json()
        st.success("Call logs fetched successfully")
        return logs
    else:
        st.error("Failed to fetch call logs")
        return []

def fetch_transcript(call_id):
    url = f"https://api.vapi.ai/call/{call_id}"
    headers = {
        'Authorization': f'Bearer {auth_token}'
    }

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        call_details = response.json()
        transcript = call_details.get('transcript', 'No transcript available')
        st.success("Transcript fetched successfully")
        return transcript
    else:
        st.error("Failed to fetch transcript")
        return "Failed to fetch transcript"

def extract_and_save_appointment_details(transcript):
    prompt = f"""
    Extract the following details from the transcript:
    - phone_number
    - user_name
    - specialty
    - doctor_name
    - appointment_type
    - appointment_date
    
    Format the response as key: value pairs, one per line.
    
    Transcript:
    {transcript}
    """
    
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt}
        ],
        temperature=1,
        max_tokens=256,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    details = response.choices[0].message.content

    details_dict = {}
    for line in details.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            details_dict[key.strip()] = value.strip()

    appointment_date_str = details_dict.get("appointment_date")
    formatted_date = parse_and_format_date(appointment_date_str) if appointment_date_str else None

    collect_user_info_and_save(
        details_dict.get("phone_number"),
        details_dict.get("user_name"),
        details_dict.get("specialty"),
        details_dict.get("doctor_name"),
        details_dict.get("appointment_type"),
        formatted_date
    )

def parse_and_format_date(date_str):
    try:
        date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
        
        # Handle relative dates
        if "tomorrow" in date_str.lower():
            appointment_date = datetime.now() + timedelta(days=1)
        elif "day after tomorrow" in date_str.lower():
            appointment_date = datetime.now() + timedelta(days=2)
        else:
            appointment_date = datetime.strptime(date_str, "%d %B at %I %p")
        
        formatted_date = appointment_date.strftime("%d %B at %I %p")
        return formatted_date
    except ValueError:
        st.error(f"Failed to parse date: {date_str}")
        return date_str

# Streamlit App
st.sidebar.image('ManipalLogo.png')  # Add the path to your logo image
st.sidebar.title("Manipal Hospital Dashboard")

# Sidebar options
option = st.sidebar.selectbox(
    "Select a page",
    ("Single Call", "Appointments", "Call Logs", "Transcript")
)

if option == "Single Call":
    st.title('Single Call')
    phone_number = st.text_input('Enter phone number (with country code)')
    
    if st.button('Make Call'):
        st.write(f"Initiating call to {phone_number}")
        message, response = make_call(phone_number)
        st.write(message)
        
        if isinstance(response, dict) and 'id' in response:
            st.session_state['last_call_id'] = response['id']
        else:
            st.error("Unexpected response format")

    if st.button('Check Call Status and Process Bookings'):
        if 'last_call_id' in st.session_state:
            handle_conversation(st.session_state['last_call_id'])
        else:
            st.warning("No active call to process.")

elif option == "Appointments":
    st.title('Appointments')
    st.write("Fetching appointments from the database...")
    df = fetch_appointments()
    st.dataframe(df)

elif option == "Call Logs":
    st.title('Call Logs')
    st.write("Fetching call logs from the API...")
    logs_df = fetch_call_logs()
    logs_df = pd.DataFrame(logs_df)
    st.dataframe(logs_df)
    
elif option == "Transcript":
    st.title('Transcript')
    st.write("Fetching transcript of the most recent call...")

    call_logs = fetch_call_logs()
    if call_logs:
        most_recent_call_id = call_logs[0]['id']
        transcript = fetch_transcript(most_recent_call_id)
        st.text_area("Transcript", transcript, height=400)
        
        st.write("Extracting details from transcript using OpenAI...")
        extract_and_save_appointment_details(transcript)
        st.write("Details extracted and saved.")
    else:
        st.warning("No call logs available.")
