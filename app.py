# server.py
import os
import base64
import numpy as np
import cv2
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient, ReturnDocument
import face_recognition
from datetime import datetime, date
from bson.objectid import ObjectId


# ----------------- Config -----------------
STATIC_FOLDER = 'static'    # place index.html, app.js, style.css here for convenience
TEMPLATES_FOLDER = 'templates'  # if you use templates
STUDENTS_FOLDER = 'students'  # where uploaded registration images saved (optional)

# Demo OTP: we use fixed OTP for prototype (replace with SMS service for real)
DEMO_OTP = '123456'
OTP_STORE = {}  # ephemeral: { aadhaar_phone_key: otp_sent_time }

# matching threshold (tweakable)
FACE_TOLERANCE = 0.48  # lower = stricter, higher = more tolerant

# ----------------- Init app & DB -----------------
app = Flask(__name__, static_folder=STATIC_FOLDER, template_folder=TEMPLATES_FOLDER)
CORS(app)

# MongoDB connection (change URI if needed)
client = MongoClient("mongodb://localhost:27017/")
db = client["voting_system"]

users_col = db["users"]        # registered users with face encodings
voters_col = db["voters"]      # sample voter list (pre-populated)
parties_col = db["parties"]    # parties with voteCount
votes_col = db["votes"]        # votes records

# ensure student images folder exists
os.makedirs(STUDENTS_FOLDER, exist_ok=True)

# ------------- Helper functions -------------
def save_base64_image(base64_data, prefix='img'):
    """Save base64 image to disk and return file path."""
    header, encoded = base64_data.split(",", 1) if "," in base64_data else (None, base64_data)
    img_bytes = base64.b64decode(encoded)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    filename = f"{prefix}_{int(datetime.utcnow().timestamp()*1000)}.jpg"
    path = os.path.join(STUDENTS_FOLDER, filename)
    cv2.imwrite(path, img)
    return path, img

def compute_face_encoding_from_image(img):
    """Given an OpenCV BGR image, return first face encoding as a list (or None)."""
    # face_recognition expects RGB
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    face_locs = face_recognition.face_locations(rgb)
    if not face_locs:
        return None
    encodings = face_recognition.face_encodings(rgb, face_locs)
    if not encodings:
        return None
    # return first encoding (prototype)
    return encodings[0].tolist()

def find_matching_user_by_encoding(incoming_encoding, tolerance=FACE_TOLERANCE):
    """Compare incoming encoding with stored users and return (user, distance) if matched."""
    users = list(users_col.find({}))
    best = (None, float('inf'))
    arr_in = np.array(incoming_encoding, dtype=np.float64)
    for u in users:
        enc = u.get("face_encoding")
        if not enc or len(enc) != 128:
            continue
        arr_enc = np.array(enc, dtype=np.float64)
        d = np.linalg.norm(arr_enc - arr_in)
        if d < best[1]:
            best = (u, d)
    if best[0] and best[1] <= tolerance:
        return best  # (user_doc, distance)
    return (None, None)

def aadhaar_phone_key(aadhaar, phone):
    return f"{aadhaar}::{phone}"

# ------------- Pre-populate sample voters & parties (if empty) -------------
def seed_initial_data():
    if voters_col.count_documents({}) == 0:
        sample_voters = [
            {"voterID":"ABC123456","name":"Amit Kumar","dob":"1990-05-15","constituency":"North Delhi"},
            {"voterID":"XYZ789012","name":"Priya Sharma","dob":"1992-08-22","constituency":"South Mumbai"},
            {"voterID":"DEF456789","name":"Rajesh Patel","dob":"1988-12-10","constituency":"Gujarat East"},
            {"voterID":"GHI111222","name":"Sunita Verma","dob":"1985-07-03","constituency":"Bengaluru North"},
            {"voterID":"JKL333444","name":"Ramesh Rao","dob":"1979-11-21","constituency":"Hyderabad Central"}
        ]
        voters_col.insert_many(sample_voters)
    if parties_col.count_documents({}) == 0:
        sample_parties = [
            {"name":"Bharatiya Janata Party","candidate":"Narendra Damodar Das Modi","logo":"🏛️","voteCount":0},
            {"name":"Indian National Congress","candidate":"Rahul Gandhi","logo":"🌳","voteCount":0},
            {"name":"Aam Aadmi Party","candidate":"Arvind Kejriwal","logo":"🧹","voteCount":0},
            {"name":"Trinamool Congress","candidate":"Mamata Banerjee","logo":"🌺","voteCount":0}
        ]
        parties_col.insert_many(sample_parties)

seed_initial_data()

# ----------------- Routes: static files (optional) -----------------
@app.route('/')
def index():
    # serve frontend index.html from static folder if present
    if os.path.exists(os.path.join(STATIC_FOLDER, "index.html")):
        return send_from_directory(STATIC_FOLDER, "index.html")
    return jsonify({"message":"Voting backend running. Serve a frontend from static/ directory."})

# ----------------- API: OTP demo -----------------
@app.route('/api/send_otp', methods=['POST'])
def api_send_otp():
    data = request.get_json() or {}
    aadhaar = data.get('aadhaar')
    phone = data.get('phone')
    if not aadhaar or not phone:
        return jsonify({"error":"aadhaar and phone required"}), 400
    # store in ephemeral OTP store (demo only)
    key = aadhaar_phone_key(aadhaar, phone)
    OTP_STORE[key] = {"otp": DEMO_OTP, "sent_at": datetime.utcnow()}
    # in real app: send SMS here
    return jsonify({"message":"OTP sent (demo)", "otp": DEMO_OTP})

@app.route('/api/verify_otp', methods=['POST'])
def api_verify_otp():
    data = request.get_json() or {}
    aadhaar = data.get('aadhaar'); phone = data.get('phone'); otp = data.get('otp')
    if not aadhaar or not phone or not otp:
        return jsonify({"error":"aadhaar, phone, otp required"}), 400
    key = aadhaar_phone_key(aadhaar, phone)
    rec = OTP_STORE.get(key)
    if not rec or rec.get('otp') != otp:
        return jsonify({"error":"invalid or expired otp"}), 400
    return jsonify({"message":"otp verified"})

# ----------------- API: Register user (Aadhaar + phone + face image) -----------------
@app.route('/api/register', methods=['POST'])
def api_register():
    """
    Expected JSON:
    {
      "name": "...",
      "aadhaar": "12digits",
      "phone": "10digits",
      "image": "data:image/png;base64,....."  // captured face image data URL
    }
    """
    try:
        data = request.get_json() or {}
        name = data.get('name')
        aadhaar = data.get('aadhaar')
        phone = data.get('phone')
        image = data.get('image')

        if not (name and aadhaar and phone and image):
            return jsonify({"error":"missing fields"}), 400

        if users_col.find_one({"aadhaar": aadhaar}):
            return jsonify({"error": "aadhaar already registered"}), 400

        # save image and compute encoding
        image_path, img = save_base64_image(image, prefix=f"user_{aadhaar}")
        encoding = compute_face_encoding_from_image(img)
        if encoding is None:
            return jsonify({"error":"no face detected or poor image quality"}), 400

        user_doc = {
            "name": name,
            "aadhaar": aadhaar,
            "phone": phone,
            "face_encoding": list(map(float, encoding)),
            "image_path": image_path,
            "voterID": None,
            "constituency": None,
            "created_at": datetime.utcnow()
        }
        users_col.insert_one(user_doc)
        return jsonify({"message":"registered", "user": {"name": name, "aadhaar": aadhaar}}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------- API: Face-login (Aadhaar+phone already OTP verified client-side) -----------------
@app.route('/api/login_face', methods=['POST'])
def api_login_face():
    """
    Expected JSON:
    {
      "aadhaar": "...",
      "phone": "...",
      "image": "data:image/png;base64,...."
    }
    """
    try:
        data = request.get_json() or {}
        aadhaar = data.get('aadhaar')
        phone = data.get('phone')
        image = data.get('image')

        if not (aadhaar and phone and image):
            return jsonify({"error":"missing fields"}), 400

        # check user exists
        user = users_col.find_one({"aadhaar": aadhaar, "phone": phone})
        if not user:
            return jsonify({"error":"user not found"}), 404

        # compute descriptor for incoming image
        _, img = save_base64_image(image, prefix=f"login_{aadhaar}")
        incoming = compute_face_encoding_from_image(img)
        if incoming is None:
            return jsonify({"error":"no face detected in provided image"}), 400

        # compare against stored encoding for the user (fast path)
        stored = user.get("face_encoding")
        if stored and len(stored) == 128:
            d = np.linalg.norm(np.array(stored, dtype=np.float64) - np.array(incoming, dtype=np.float64))
            if d <= FACE_TOLERANCE:
                # success
                return jsonify({"success": True, "user": {"name": user["name"], "aadhaar": user["aadhaar"], "voterID": user.get("voterID")}, "distance": float(d)}), 200

        # fallback: search entire DB (for robustness)
        match_user, distance = find_matching_user_by_encoding(incoming, FACE_TOLERANCE)
        if match_user:
            return jsonify({"success": True, "user": {"name": match_user["name"], "aadhaar": match_user["aadhaar"], "voterID": match_user.get("voterID")}, "distance": float(distance)}), 200

        return jsonify({"success": False, "message":"face not recognized"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------- API: Link Voter ID -----------------
@app.route('/api/list_voters', methods=['GET'])
def api_list_voters():
    voters = list(voters_col.find({}, {"_id":0}))
    return jsonify({"voters": voters})

@app.route('/api/link_voter', methods=['POST'])
def api_link_voter():
    """
    JSON:
    { "aadhaar": "...", "phone": "...", "voterID": "...", "dob": "YYYY-MM-DD" }
    """
    try:
        data = request.get_json() or {}
        aadhaar = data.get('aadhaar'); phone = data.get('phone')
        voterID = data.get('voterID'); dob = data.get('dob')
        if not (aadhaar and phone and voterID and dob):
            return jsonify({"error":"missing fields"}), 400

        # verify user exists
        user = users_col.find_one({"aadhaar": aadhaar, "phone": phone})
        if not user:
            return jsonify({"error":"user not found"}), 404

        # find voter record
        voter = voters_col.find_one({"voterID": voterID})
        if not voter:
            return jsonify({"error":"voterID not found"}), 404

        if voter.get("dob") != dob:
            return jsonify({"error":"DOB does not match"}), 400

        # ensure not already linked to another user
        other = users_col.find_one({"voterID": voterID, "aadhaar": {"$ne": aadhaar}})
        if other:
            return jsonify({"error":"voterID already linked to another account"}), 400

        # link
        updated = users_col.find_one_and_update({"aadhaar": aadhaar, "phone": phone},
                                               {"$set": {"voterID": voterID, "constituency": voter.get("constituency")}},
                                               return_document=ReturnDocument.AFTER)
        return jsonify({"message":"linked", "user": {"aadhaar": updated["aadhaar"], "voterID": updated.get("voterID")}}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------- API: Parties & Voting -----------------
@app.route('/api/list_parties', methods=['GET'])
def api_list_parties():
    parties = list(parties_col.find({}, {"_id":1, "name":1, "candidate":1, "logo":1, "voteCount":1}))
    # convert ObjectId to str
    for p in parties:
        p['id'] = str(p['_id'])
        p.pop('_id', None)
    return jsonify({"parties": parties})

@app.route('/api/vote', methods=['POST'])
def api_vote():
    """
    JSON:
    { "aadhaar": "...", "voterID": "...", "party_id": "..."}
    """
    try:
        data = request.get_json() or {}
        aadhaar = data.get('aadhaar'); voterID = data.get('voterID'); party_id = data.get('party_id')
        if not (aadhaar and voterID and party_id):
            return jsonify({"error":"missing fields"}), 400

        # verify user
        user = users_col.find_one({"aadhaar": aadhaar})
        if not user:
            return jsonify({"error":"user not found"}), 404
        # verify voterID matches user
        if user.get("voterID") != voterID:
            return jsonify({"error":"voterID not linked to this user"}), 400

        # check if already voted
        existing = votes_col.find_one({"voterID": voterID})
        if existing:
            return jsonify({"error":"already voted"}), 400

        # cast vote: increment party voteCount and record vote
        p_obj = parties_col.find_one_and_update({"_id": ObjectId(party_id)}, {"$inc": {"voteCount": 1}}, return_document=ReturnDocument.AFTER)
        if not p_obj:
            return jsonify({"error":"party not found"}), 404

        vote_doc = {"voterID": voterID, "party_id": str(p_obj["_id"]), "timestamp": datetime.utcnow()}
        votes_col.insert_one(vote_doc)

        return jsonify({"message":"vote recorded", "party": {"name": p_obj["name"], "voteCount": p_obj["voteCount"]}}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------- API: Admin helpers (export DB) -----------------
@app.route('/api/export_db', methods=['GET'])
def api_export_db():
    users = list(users_col.find({}, {"_id":0}))
    voters = list(voters_col.find({}, {"_id":0}))
    parties = list(parties_col.find({}, {"_id":0}))
    votes = list(votes_col.find({}, {"_id":0}))
    return jsonify({"users": users, "voters": voters, "parties": parties, "votes": votes})

# ----------------- Run server -----------------
if __name__ == '__main__':
    print("Starting voting backend on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
