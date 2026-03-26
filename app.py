import os
import logging
import re
import tempfile
import requests
from flask import Flask, request, jsonify
import cloudinary
import cloudinary.uploader

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Cloudinary from environment variables
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

logger.info("Cloudinary configured with cloud_name=%s", os.environ.get('CLOUDINARY_CLOUD_NAME'))

WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')

# Warn at startup if required environment variables are missing
for _var in ('CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET', 'WEBHOOK_SECRET'):
    if not os.environ.get(_var):
        logger.warning("Environment variable %s is not set", _var)


# Cognito webhook endpoint
@app.route('/cognito-webhook', methods=['POST'])
def cognito_webhook():
    # Validate webhook token from query parameter
    token = request.args.get('token')
    if not WEBHOOK_SECRET or token != WEBHOOK_SECRET:
        logger.warning("Unauthorized webhook attempt with token: %s", token)
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    if not data:
        logger.error("No JSON payload received")
        return jsonify({'error': 'No JSON payload'}), 400

    logger.info("Received Cognito webhook payload: %s", data)

    # Extract video temp URL from Cognito payload
    # Cognito sends the file URL in data['entry']['fields'] or similar structure
    try:
        video_url = (
            data.get('video_url')
            or data.get('url')
            or (data.get('entry') or {}).get('video_url')
            or (data.get('entry') or {}).get('url')
        )

        # Extract contestant name and video title
        entry = data.get('entry') or data
        contestant_name = (
            entry.get('contestant_name')
            or entry.get('name')
            or entry.get('submitter_name')
            or 'unknown'
        )
        video_title = (
            entry.get('video_title')
            or entry.get('title')
            or entry.get('submission_title')
            or 'untitled'
        )

        if not video_url:
            logger.error("No video URL found in payload: %s", data)
            return jsonify({'error': 'No video URL in payload'}), 400

        # Basic SSRF mitigation: only allow https:// URLs
        from urllib.parse import urlparse
        parsed = urlparse(video_url)
        if parsed.scheme != 'https':
            logger.error("Rejected non-HTTPS video URL: %s", video_url)
            return jsonify({'error': 'Only HTTPS video URLs are accepted'}), 400

        logger.info("Downloading video from: %s", video_url)

        # Download video from Cognito temp URL (streaming to handle large files)
        dl_response = requests.get(video_url, timeout=60, stream=True)
        dl_response.raise_for_status()

        # Determine file extension from URL or Content-Type header
        content_type = dl_response.headers.get('Content-Type', '')
        ext = '.mp4'
        if 'quicktime' in content_type or video_url.lower().endswith('.mov'):
            ext = '.mov'
        elif 'webm' in content_type or video_url.lower().endswith('.webm'):
            ext = '.webm'
        elif 'avi' in content_type or video_url.lower().endswith('.avi'):
            ext = '.avi'

        # Sanitize public_id: keep only alphanumeric, underscores, and hyphens
        raw_id = f"{contestant_name}_{video_title}"
        safe_id = re.sub(r'[^A-Za-z0-9_\-]', '_', raw_id)

        # Write to a temp file and upload to Cloudinary
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                for chunk in dl_response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name

            logger.info("Uploading video to Cloudinary for contestant=%s title=%s", contestant_name, video_title)

            upload_result = cloudinary.uploader.upload(
                tmp_path,
                resource_type='video',
                folder='submissions',
                public_id=safe_id,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        logger.info("Upload successful: %s", upload_result.get('secure_url'))

        return jsonify({
            'status': 'success',
            'url': upload_result['secure_url'],
            'contestant_name': contestant_name,
            'video_title': video_title,
        }), 200

    except requests.RequestException as e:
        logger.error("Failed to download video: %s", e)
        return jsonify({'error': f'Failed to download video: {str(e)}'}), 500
    except Exception as e:
        logger.error("Unexpected error processing webhook: %s", e)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


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


# Video API endpoints
@app.route('/videos', methods=['GET'])
def list_videos():
    videos = []  # Implement logic to retrieve video data as needed
    return jsonify({'videos': videos}), 200


if __name__ == '__main__':
    app.run(debug=True)
