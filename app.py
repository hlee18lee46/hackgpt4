from flask import Flask, request, jsonify, render_template
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv
import base64
import requests
import json
import re
from bson import ObjectId

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Get MongoDB URI and API key from environment variables
uri = os.getenv("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi('1'))
db = client['hancluster']  # MongoDB database name
collection = db['dog_breeds']  # MongoDB collection name
api_key = os.getenv("OPENAI_API_KEY")

# Helper function to serialize MongoDB ObjectId
def serialize_mongo_object(data):
    if "_id" in data:
        data["_id"] = str(data["_id"])
    return data

# Check MongoDB connection
@app.route('/ping_db', methods=['GET'])
def ping_db():
    try:
        client.admin.command('ping')
        return jsonify({"message": "Pinged your deployment. Successfully connected to MongoDB!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to display the upload form
@app.route("/upload", methods=["GET"])
def upload_form():
    return render_template("upload.html")

# Process the uploaded image and analyze it
# Process the uploaded image and analyze it
@app.route("/upload", methods=["POST"])
def upload_and_analyze_image():
    if "image" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file:
        # Encode the image in base64
        base64_image = base64.b64encode(file.read()).decode("utf-8")

        # Define the prompt
        prompt = (
            "Can you provide a JSON object with details such as height, weight, "
            "lifespan, breed, breed group (only group name, not including \"Group\"), shed level, temperament (in the list), energy level, and "
            "common health concerns (in the list) about the dog in the image? Format the response in JSON."
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # Build the payload for the API call
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            "max_tokens": 900
        }

        # Make the request to OpenAI API
        response = requests.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
        )
        response_data = response.json()

        # Print response data for debugging
        print("Response Data:", response_data)

        if response_data and "choices" in response_data and len(response_data["choices"]) > 0:
            content_text = response_data["choices"][0]["message"]["content"]
            
            # Use regular expressions to check for JSON structure inside content_text
            json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
            
            if json_match:
                dog_info_json = json_match.group(0)

                try:
                    # Parse the JSON string into a Python dictionary
                    dog_data = json.loads(dog_info_json)
                    
                    # Insert parsed information into MongoDB
                    result = collection.insert_one(dog_data)
                    
                    # Serialize MongoDB ObjectId and return response
                    dog_data["_id"] = str(result.inserted_id)
                    return jsonify(dog_data), 200
                except Exception as e:
                    print("Error parsing JSON:", e)
                    return jsonify({"error": "Error parsing JSON response"}), 500
            else:
                # No JSON detected; return a friendly message
                return jsonify({
                    "error": "No dog detected in the image. Please upload an image with a clear view of a dog."
                }), 200

    return jsonify({"error": "Unknown error"}), 500

@app.route('/')
def home():
    return "Welcome to GPT4o: Code & Conquer with MongoDB and GPT-4!"

if __name__ == '__main__':
    app.run(debug=True)
