# ---------------------------------------------------------------------
#   Flask server wrapper handling HTTP routes and serving the web app.
# -------------------------------------------------------------------
from flask import Flask, Response,request, jsonify, render_template, send_file

# ---------------------------------------------------------------------
#   Wrapper for the Flask application server.
# -------------------------------------------------------------------
class FlaskServer:
    def __init__(self, processor, db=None):
        self.processor = processor
        self.db = db
        self.audio_path = ""
        self.app = Flask(__name__, static_folder='../static', template_folder='../templates')
        self.app.add_url_rule('/', 'index', self.index)
            
    # ---------------------------------------------------------------------
    #   Route: Serves the main index HTML.
    # -------------------------------------------------------------------
    def index(self):
        """Serves the main HTML page."""
        return render_template('index.html')

    # ---------------------------------------------------------------------
    #   Starts the Flask web server.
    # -------------------------------------------------------------------
    def run(self):
        """Starts the Flask server."""
        self.app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
