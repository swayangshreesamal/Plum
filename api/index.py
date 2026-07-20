from flask import Flask, request, jsonify
from supabase import create_client
import os
import hmac
import hashlib
import json

app = Flask(__name__)

# Initialize Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vapi webhook secret for signature verification
VAPI_SECRET = os.environ.get("VAPI_WEBHOOK_SECRET", "")

def verify_vapi_signature(payload_bytes, signature):
    """Verify that the webhook actually came from Vapi."""
    if not VAPI_SECRET:
        return True  # Allow if not configured (dev mode), but WARN in production
    expected = hmac.new(
        VAPI_SECRET.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route('/webhook', methods=['POST'])
def webhook():
    # 1. SIGNATURE VERIFICATION
    payload_bytes = request.get_data()
    signature = request.headers.get('x-vapi-signature', '')
    
    if not verify_vapi_signature(payload_bytes, signature):
        return jsonify({"status": "error", "message": "Invalid signature"}), 401

    data = request.get_json()

    # 2. ONLY PROCESS FINAL REPORT
    message_type = data.get("type") or data.get("message", {}).get("type")
    if message_type != "end-of-call-report":
        return jsonify({"status": "ignored", "message": "Not the final report"}), 200

    # 3. IDEMPOTENCY: Extract call_id and check if already processed
    call_id = data.get("call", {}).get("id") or data.get("message", {}).get("call", {}).get("id")
    if not call_id:
        return jsonify({"status": "error", "message": "No call_id found"}), 400

    existing = supabase.table("bookings").select("id").eq("vapi_call_id", call_id).execute()
    if existing.data:
        return jsonify({"status": "already_processed", "call_id": call_id}), 200

    # 4. FIND WHICH PLUMBER WAS CALLED
    # Vapi sends the Twilio number that received the call
    called_number = (
        data.get("call", {}).get("phone_number", {}).get("twilio_number") or
        data.get("message", {}).get("call", {}).get("phone_number", {}).get("twilio_number") or
        data.get("phone_number_called")
    )

    plumber = None
    if called_number:
        # Look up plumber by their assigned Twilio number
        result = supabase.table("profiles").select("user_id, business_name, phone").eq("twilio_number", called_number).execute()
        if result.data:
            plumber = result.data[0]

    if not plumber:
        # Fallback: if no plumber found, log to a "unassigned" bucket so you don't lose the lead
        plumber = {
            "user_id": None,
            "business_name": "UNASSIGNED",
            "phone": None
        }

    # 5. EXTRACT CUSTOMER DATA
    message_obj = data.get("message", {})
    transcript = message_obj.get("transcript", "")
    summary = message_obj.get("summary", "No summary provided.")
    
    # Try structured extraction first (Vapi's analysis.structuredData)
    structured = data.get("call", {}).get("analysis", {}).get("structuredData", {})
    
    customer_data = data.get("customer", {}) or message_obj.get("customer", {})
    caller_name = structured.get("name") or customer_data.get("name") or "Unknown Caller"
    phone = structured.get("phone") or customer_data.get("number") or "Unknown Number"
    address = structured.get("address") or structured.get("location") or ""
    service_type = structured.get("service") or structured.get("issue") or ""
    urgency = structured.get("urgency") or "normal"

    # Web sandbox fallback
    if caller_name == "Unknown Caller" or not caller_name:
        caller_name = "Web Sandbox User"
    if phone == "Unknown Number" or not phone:
        phone = "Web Chat Session"

    # 6. INSERT INTO DATABASE (unified schema)
    new_booking = {
        "client_id": plumber["user_id"],           # Links to the actual plumber
        "client_name": plumber["business_name"],   # NOT hardcoded
        "caller_name": caller_name,
        "phone": phone,
        "address": address,
        "job_type": service_type,
        "urgency": urgency,
        "booking_details": f"Summary: {summary}\n\nTranscript: {transcript}",
        "lead_status": "pending",                  # plumber must confirm
        "lead_value": 0,
        "source": "ai_voice",                      # Track AI-sourced bookings
        "vapi_call_id": call_id,                   # Prevent duplicates
        "recording_url": data.get("call", {}).get("recording_url", ""),
        "created_at": "now()"
    }
    
    try:
        response = supabase.table("bookings").insert(new_booking).execute()
        
        # 7. OPTIONAL: Send SMS to plumber (uncomment when ready)
        # if plumber.get("phone"):
        #     send_sms_to_plumber(plumber["phone"], caller_name, service_type, address)
        
        return jsonify({
            "status": "success", 
            "call_id": call_id,
            "plumber": plumber["business_name"],
            "data": response.data
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        "service": "AI Booking Gateway", 
        "status": "healthy",
        "version": "2.0"
    }), 200

if __name__ == '__main__':
    app.run()
