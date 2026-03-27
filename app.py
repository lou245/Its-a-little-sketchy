from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader

# Initialize Flask app
app = Flask(__name__)

# Configure Cloudinary
cloudinary.config(
    cloud_name='your_cloud_name',
    api_key='your_api_key',
    api_secret='your_api_secret'
)

# Webhook receiver
@app.route('/webhook', methods=['POST'])
def webhook_receiver():
    data = request.json
    # Process webhook data
    # (Implement your business logic here)
    return jsonify({'status': 'success', 'data': data}), 200

# Upload endpoint
@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    upload_result = cloudinary.uploader.upload(file)
    return jsonify({'url': upload_result['secure_url']}), 200

# Video API endpoints (example)
@app.route('/videos', methods=['GET'])
def list_videos():
    # Fetch list of videos (Implement your logic to retrieve video data)
    videos = []  # Example list of videos
    return jsonify({'videos': videos}), 200
@app.route('/gallery')
def gallery():
    return app.send_static_file('gallery.html')
import os
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
