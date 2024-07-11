from pymongo import MongoClient
from datetime import datetime
import re

# Connect to MongoDB
client = MongoClient("mongodb+srv://sachinparmar0246:2nGATJVDEwDZzaA8@cluster0.c25rmsz.mongodb.net")
db = client.hospital

# Function to format datetime without year
def format_datetime(dt):
    return dt.strftime("%d %B at %I %p")

# Insert specialties
specialties = db.specialties
specialties.insert_many([
    {
        "name": "Cardiology",
        "doctors": [
            {
                "name": "Dr Sambaji",
                "available_slots": [
                    format_datetime(datetime(2024, 7, 11, 9, 0)),
                    format_datetime(datetime(2024, 7, 11, 11, 0)),
                    format_datetime(datetime(2024, 7, 12, 14, 0))
                ],
                "booked_slots": [
                    format_datetime(datetime(2024, 7, 10, 13, 0))
                ]
            },
            {
                "name": "Dr Kiran",
                "available_slots": [
                    format_datetime(datetime(2024, 7, 11, 10, 0)),
                    format_datetime(datetime(2024, 7, 11, 12, 0)),
                    format_datetime(datetime(2024, 7, 12, 15, 0))
                ],
                "booked_slots": [
                    format_datetime(datetime(2024, 7, 10, 14, 0))
                ]
            }
        ]
    },
    {
        "name": "General Surgery",
        "doctors": [
            {
                "name": "Dr Aritra Ghosh",
                "available_slots": [
                    format_datetime(datetime(2024, 7, 11, 9, 0)),
                    format_datetime(datetime(2024, 7, 11, 11, 0)),
                    format_datetime(datetime(2024, 7, 12, 14, 0))
                ],
                "booked_slots": [
                    format_datetime(datetime(2024, 7, 10, 15, 0))
                ]
            }
        ]
    }
])

# Ensure the user_appointments collection exists
user_appointments = db.user_appointments

# Insert sample user appointment data
user_appointments.insert_many([
    {
        "mobile_number": "+1234567890",
        "name": "John Doe",
        "specialty": "Cardiology",
        "doctor_name": "Dr Kiran",
        "appointment_type": "Physical",
        "appointment_date": "12 July at 2 PM"
    },
    {
        "mobile_number": "+0987654321",
        "name": "Jane Smith",
        "specialty": "General Surgery",
        "doctor_name": "Dr Aritra Ghosh",
        "appointment_type": "Teleconsultation",
        "appointment_date": "11 July at 11 AM"
    }
])