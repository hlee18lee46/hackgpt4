from flask import Flask, request, jsonify, render_template
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv
import base64
import requests
import json
import re
import pymongo
from bson import ObjectId
from flask_cors import CORS

app = Flask(__name__)
CORS(app)



# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Function to create a MongoDB client
def get_mongo_client():
    uri = os.getenv("MONGO_URI")  # Ensure MONGO_URI is correctly set in your environment
    return pymongo.MongoClient(uri)

# Get MongoDB URI and API key from environment variables
uri = os.getenv("MONGO_URI")
client = MongoClient(uri, server_api=ServerApi('1'))
db = client['hancluster']  # MongoDB database name
collection = db['dog_breeds']  # MongoDB collection name
search_stats_collection = db['search_stats']  # New collection for breed search counts

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

@app.route('/drop_collections', methods=['POST'])
def drop_collections():
    try:
        # Drop the breed_stats collection
        db.breed_stats.drop()
        print("Collection dropped successfully!")
        return jsonify({"message": "Collection dropped successfully!"}), 200
    except Exception as e:
        print("Error dropping collection:", e)
        return jsonify({"error": str(e)}), 500

# Route to display the upload form
@app.route("/upload", methods=["GET"])
def upload_form():
    return render_template("upload.html")

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
            "Can you provide a JSON object with details such as height (as the field name \"height\"), weight (as the field name \"weight\"), "
            "lifespan (as the field name \"lifespan\"), breed (as the field name \"breed\"), breed group (only group name, not including \"Group\", as the field name \"breed_group\"), shed level (as the field name \"shed_level\"), temperament (in a list, as the field name \"temperament\"), energy level (as the field name \"energy_level\"), and "
            "common health concerns (in the list, as the field name \"common_health_concerns\") about the dog in the image? Format the response in JSON."
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
                    
                    # Display the full JSON data to the user
                    display_data = dog_data

                    # Extract breed and breed_group for search stats
                    breed = dog_data.get("breed")
                    breed_group = dog_data.get("breed_group")

                    # Update or insert search count in `breed_stats` collection
                    if breed and breed_group:
                        db.breed_stats.update_one(
                            {"breed": breed, "breed_group": breed_group},
                            {"$inc": {"count": 1}},  # Increment count by 1 if it exists
                            upsert=True  # Insert a new document if it doesn't exist
                        )

                    # Return the full JSON to the user
                    return jsonify(display_data), 200
                except Exception as e:
                    print("Error parsing JSON:", e)
                    return jsonify({"error": "Error parsing JSON response"}), 500
            else:
                # No JSON detected; return a friendly message
                return jsonify({
                    "error": "No dog detected in the image. Please upload an image with a clear view of a dog."
                }), 200

    return jsonify({"error": "Unknown error"}), 500


@app.route("/upload_base64", methods=["POST"])
def upload_base64_image():
    # Check if the request contains JSON data with an "image" field
    data = request.get_json()
    if not data or "image" not in data:
        return jsonify({"error": "No image data provided"}), 400

    # Decode the base64 image data
    try:
        base64_image = data["image"]
        image_data = base64.b64decode(base64_image)
        
        # Save the decoded image as "img1.jpg"
        image_path = "img1.jpg"
        with open(image_path, "wb") as img_file:
            img_file.write(image_data)
        
        # Re-encode the saved image to base64 to return in the response
        with open(image_path, "rb") as img_file:
            encoded_image = base64.b64encode(img_file.read()).decode("utf-8")
        
        return jsonify({
            "message": "Image received and saved successfully!",
            "image_base64": encoded_image  # Send the base64-encoded image back in the response
        }), 200

    except Exception as e:
        print("Error decoding or saving image:", e)
        return jsonify({"error": "Failed to decode or save image"}), 500


@app.route("/upload_base64_return_info", methods=["POST"])
def upload_base64_return_info():

    data = request.get_json()
    # Debugging: Print the raw data received
    print("Received data:", data)
    if not data or "image" not in data:
        return jsonify({"error": "No image data provided"}), 400


    # Encode the image in base64
    base64_image = data["image"]

    # Define the prompt
    prompt = (
        "Can you provide a JSON object with details such as height (as the field name \"height\"), weight (as the field name \"weight\"), "
        "lifespan (as the field name \"lifespan\"), breed (as the field name \"breed\"), breed group (only group name, not including \"Group\", as the field name \"breed_group\"), shed level (as the field name \"shed_level\"), temperament (in a list, as the field name \"temperament\"), energy level (as the field name \"energy_level\"), and "
        "common health concerns (in the list, as the field name \"common_health_concerns\") about the dog in the image? Format the response in JSON."
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
                
                # Display the full JSON data to the user
                display_data = dog_data

                # Extract breed and breed_group for search stats
                breed = dog_data.get("breed")
                breed_group = dog_data.get("breed_group")

                # Update or insert search count in `breed_stats` collection
                if breed and breed_group:
                    db.breed_stats.update_one(
                        {"breed": breed, "breed_group": breed_group},
                        {"$inc": {"count": 1}},  # Increment count by 1 if it exists
                        upsert=True  # Insert a new document if it doesn't exist
                    )

                # Return the full JSON to the user
                return jsonify(display_data), 200
            except Exception as e:
                print("Error parsing JSON:", e)
                return jsonify({"error": "Error parsing JSON response"}), 500
        else:
            # No JSON detected; return a friendly message
            return jsonify({
                "error": "No dog detected in the image. Please upload an image with a clear view of a dog."
            }), 200

    return jsonify({"error": "Unknown error"}), 500

@app.route("/upload_multipart", methods=["POST"])
def upload():
    # Ensure a file was provided
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    # Retrieve the file
    file = request.files["file"]
    
    # Optionally, you can save or process this file
    file.save("uploaded_image.jpg")  # Save temporarily to disk for processing
    
    # For demonstration, return a success message
    return jsonify({"message": "File received successfully"}), 200

@app.route('/convert_to_base64', methods=['GET', 'POST'])
def convert_to_base64():
    if request.method == 'POST':
        if 'image' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        # Convert the uploaded image to a base64 string
        base64_image = base64.b64encode(file.read()).decode('utf-8')
        print("Base64 Encoded Image:", base64_image)  # Debugging: Print to console

        # Return the base64-encoded string as JSON
        return jsonify({"base64_string": base64_image}), 200

    # Render the HTML form on GET request
    return render_template('upload_image.html')

@app.route("/insert_breed_data", methods=["POST"])
def insert_breed_data():
    # Define the breed data to be inserted
    breed_data = {
        "breed": "Chihuahua",
        "breed_group": "Toy",
        "count": 1
    }
    
    # Insert the data into `breed_stats` collection
    result = db.breed_stats.update_one(
        {"breed": breed_data["breed"], "breed_group": breed_data["breed_group"]},
        {"$set": breed_data},
        upsert=True  # Ensures the document is created if it doesn't already exist
    )
    
    # Check if the document was inserted or updated
    if result.upserted_id:
        message = "New document inserted successfully!"
    else:
        message = "Document already exists. Count reset to 1."

    return jsonify({"message": message})

@app.route('/view_data')
def view_data():
    # Fetch all documents from `breed_stats`
    breed_stats_data = list(db.breed_stats.find())  # Adjusted to use a single collection

    # Convert ObjectId to string for JSON serialization
    for item in breed_stats_data:
        item["_id"] = str(item["_id"])

    return jsonify({
        "breed_stats": breed_stats_data
    })



@app.route('/')
def home():
    return "Welcome to GPT4o: Code & Conquer with MongoDB and GPT-4!"


if __name__ == '__main__':
    app.run(debug=True)
