import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from config import Config
from database import init_db
from routes.order_routes import order_bp
from routes.staff_routes import staff_bp
from routes.payment_routes import payment_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Enable CORS for React frontend (Vite default port 5173 and preview 4173)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Ensure upload directory exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Initialize SQLite database and tables
    with app.app_context():
        init_db()

    # Register API Blueprints
    app.register_blueprint(order_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(payment_bp)

    @app.route("/")
    def index():
        return jsonify({
            "service": "Digital Xerox & Stationery Ordering API",
            "version": "1.0.0",
            "status": "online",
            "endpoints": {
                "health": "/api/health",
                "pricing": "/api/pricing",
                "create_order": "/api/orders [POST]",
                "track_order": "/api/orders/track/<query> [GET]",
                "staff_login": "/api/staff/login [POST]",
                "staff_orders": "/api/staff/orders [GET]",
                "staff_stats": "/api/staff/stats [GET]"
            }
        })

    @app.route("/api/health")
    def health():
        return jsonify({"status": "healthy", "database": "connected"}), 200

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"success": False, "error": "File size exceeds the 50MB limit"}), 413

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"success": False, "error": "Endpoint not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"success": False, "error": "Internal server error"}), 500

    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    print(f">> Digital Xerox Backend running on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
