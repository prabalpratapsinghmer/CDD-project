import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    # Content is clearly visible to make PR changes easy to recognize
    return """
    <h1>CDD Project - PR Preview Environment</h1>
    <p>Version: Base Setup (Change this text to test PR updates)</p>
    """

if __name__ == '__main__':
    # Uses platform-provided port where applicable, defaults to 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)