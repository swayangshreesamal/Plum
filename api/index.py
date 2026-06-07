from flask import Flask, request, jsonify
from supabase import create_client, Client
from twilio.rest import Client as TwilioClient
import os
from datetime import datetime

app = Flask(__name__)

# Initialize Cloud Infrastructures via Environment Variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "AI Booking Gateway"}), 200

@app.route('/webhook', methods=['POST'])
def vapi_webhook():
    data = request.json
    
    # Verify the incoming payload is an end-of-call summary from Vapi
    if not data or data.get("message", {}).get("type") != "end-of-call-report":
        return jsonify({"status": "ignored", "message": "Not an end-of-call report"}), 200
    
    call_report = data["message"]
    artifact = call_report.get("artifact", {})
    transcript = call_report.get("transcript", "")
    
    # Extract structured data from Vapi's custom extracted properties
    analysis = call_report.get("analysis", {})
    structured_data = analysis.get("structuredData", {})
    
    customer_name = structured_data.get("customerName", "Unknown Caller")
    customer_phone = call_report.get("customer", {}).get("number", "No Phone Provided")
    booking_summary = analysis.get("summary", "No details provided.")
    
    # Default billing settings for initial stair-step pricing
    client_name = "Americool HVAC" 
    lead_value = 50.00 
    
    try:
        # 1. Insert lead directly into your Supabase Data Layer
        db_response = supabase.table("bookings").insert({
            "client_name": client_name,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "booking_details": booking_summary,
            "lead_value": lead_value,
            "lead_status": "valid"
        }).execute()
        
        # 2. Dispatch real-time SMS to the contractor using Twilio
        if TWILIO_SID and TWILIO_AUTH:
            twilio_client = TwilioClient(TWILIO_SID, TWILIO_AUTH)
            sms_body = f"🤖 AI Booking Alert for {client_name}:\n\nCust: {customer_name}\nPhone: {customer_phone}\nNeeds: {booking_summary}\n\nCheck your dashboard to view full transcript."
            
            # Replace with your client's real phone number
            twilio_client.messages.create(
                body=sms_body,
                from_=TWILIO_NUMBER,
                to=os.environ.get("CLIENT_PHONE_NUMBER") 
            )
            
        return jsonify({"status": "success", "message": "Lead logged and SMS dispatched"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
