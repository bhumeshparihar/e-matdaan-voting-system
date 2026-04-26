import os
import base64
import numpy as np
import cv2
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient, ReturnDocument
from bson.objectid import ObjectId
import face_recognition
from datetime import datetime

app = Flask(__name__, static_folder='static')
CORS(app)

client = MongoClient("mongodb://localhost:27017/")
db = client["evoting"]

users_col = db["users"]
parties_col = db["parties"]
votes_col = db["votes"]

DEMO_OTP = "123456"
OTP_STORE = {}

# ---------------- HELPERS ----------------
def decode_image(base64_str):
    header, encoded = base64_str.split(",", 1)
    img_bytes = base64.b64decode(encoded)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

def get_encoding(img):
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    enc = face_recognition.face_encodings(rgb)
    return enc[0] if enc else None

# ---------------- HOME ----------------
@app.route('/')
def home():
    return send_from_directory("static", "index.html")

# ---------------- OTP ----------------
@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    aadhaar = data.get("aadhaar")
    OTP_STORE[aadhaar] = DEMO_OTP
    return jsonify({"otp": DEMO_OTP})

@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    aadhaar = data.get("aadhaar")
    otp = data.get("otp")

    if OTP_STORE.get(aadhaar) == otp:
        return jsonify({"message": "verified"})
    return jsonify({"error": "invalid otp"}), 400

# ---------------- REGISTER ----------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    aadhaar = data.get("aadhaar")
    image = data.get("image")

    if users_col.find_one({"aadhaar": aadhaar}):
        return jsonify({"error": "already registered"}), 400

    img = decode_image(image)
    enc = get_encoding(img)

    if enc is None:
        return jsonify({"error": "face not detected"}), 400

    users_col.insert_one({
        "aadhaar": aadhaar,
        "face_encoding": enc.tolist(),
        "has_voted": False
    })

    return jsonify({"message": "registered"})

# ---------------- LOGIN ----------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    aadhaar = data.get("aadhaar")
    image = data.get("image")

    user = users_col.find_one({"aadhaar": aadhaar})
    if not user:
        return jsonify({"error": "user not found"}), 404

    img = decode_image(image)
    enc = get_encoding(img)

    if enc is None:
        return jsonify({"error": "face not detected"}), 400

    stored = np.array(user["face_encoding"])
    incoming = np.array(enc)

    dist = np.linalg.norm(stored - incoming)

    if dist <= 0.5:
        return jsonify({"success": True})
    return jsonify({"error": "face not matched"}), 401

# ---------------- PARTIES ----------------
@app.route('/api/parties', methods=['GET'])
def get_parties():
    parties = list(parties_col.find({}, {"_id":1, "name":1, "voteCount":1}))
    for p in parties:
        p["id"] = str(p["_id"])
        del p["_id"]
    return jsonify(parties)

# ---------------- VOTE ----------------
@app.route('/api/vote', methods=['POST'])
def vote():
    data = request.get_json()
    aadhaar = data.get("aadhaar")
    party_id = data.get("party_id")

    user = users_col.find_one({"aadhaar": aadhaar})
    if not user:
        return jsonify({"error": "user not found"}), 404

    if user.get("has_voted"):
        return jsonify({"error": "already voted"}), 400

    party = parties_col.find_one_and_update(
        {"_id": ObjectId(party_id)},
        {"$inc": {"voteCount": 1}},
        return_document=ReturnDocument.AFTER
    )

    votes_col.insert_one({
        "aadhaar": aadhaar,
        "party_id": party_id,
        "time": datetime.utcnow()
    })

    users_col.update_one(
        {"aadhaar": aadhaar},
        {"$set": {"has_voted": True}}
    )

    return jsonify({"message": "vote recorded"})

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)