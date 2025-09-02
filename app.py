from flask import Flask
from controllers.ont_controller import ont_bp

APP_VERSION = "2.2"  # 👈 aquí defines tu versión

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key-here'
    app.config['APP_VERSION'] = APP_VERSION  # pasar la versión a los templates

    # Registrar blueprints
    app.register_blueprint(ont_bp)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5002, debug=True)