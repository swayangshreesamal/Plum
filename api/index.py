from flask import Flask, request, jsonify
from supabase import create_client
import os

app = Flask(__name__)

# Initialize Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    # 1. FIXED: Only insert data on the final summary report to stop the 36-row duplication
    message_type = data.get("type") or data.get("message", {}).get("type")
    if message_type != "end-of-call-report":
        # Politely tell Vapi we received the update, but don't write to Supabase yet
        return jsonify({"status": "ignored", "message": "Not the final report"}), 200

    # Extract transcript and summary
    message_obj = data.get("message", {})
    transcript = message_obj.get("transcript", "")
    summary = message_obj.get("summary", "No summary provided.")
    
    # Extract customer contact details safely
    customer_data = data.get("customer", {}) or message_obj.get("customer", {})
    caller_name = customer_data.get("name")
    phone = customer_data.get("number")

    # 2. FIXED: Fallback for Web Sandbox Chats so names don't show up as 'Unknown'
    if not caller_name or caller_name == "Unknown Caller":
        # Look at Vapi's structured extraction variables if available
        caller_name = data.get("call", {}).get("analysis", {}).get("structuredData", {}).get("name")
        if not caller_name:
            caller_name = "Web Sandbox User" # Tells you clearly it was a browser test

    if not phone or phone == "Unknown Number":
        phone = data.get("call", {}).get("customer", {}).get("number", "Web Chat Session")

    # Final data package mapping perfectly to your database columns
    new_booking = {
        "client_name": "Plum Home Services",
        "caller_name": caller_name,
        "phone": phone,
        "booking_details": f"Summary: {summary}\n\nTranscript: {transcript}",
        "lead_status": "valid",
        "lead_value": 0
    }
    
    # Push to Supabase
    try:
        response = supabase.table("bookings").insert(new_booking).execute()
        return jsonify({"status": "success", "data": response.data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"service": "AI Booking Gateway", "status": "healthy"}), 200

if __name__ == '__main__':
    app.run()
