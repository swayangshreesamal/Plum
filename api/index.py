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
    
    # Extract transcript and summary
    transcript = data.get("message", {}).get("transcript", "")
    summary = data.get("message", {}).get("summary", "No summary provided.")
    
    # Use the safer extraction for Vapi data
    customer_data = data.get("customer", {})
    caller_name = customer_data.get("name") or data.get("call", {}).get("customer", {}).get("name", "Unknown Caller")
    phone = customer_data.get("number") or data.get("call", {}).get("customer", {}).get("number", "Unknown Number")

    # Mapping to your Supabase table columns
    new_booking = {
        "client_name": "Plum Home Services",
        "caller_name": caller_name,
        "phone": phone,
        "booking_details": f"Transcript: {transcript}\n\nSummary: {summary}",
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
