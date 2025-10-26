import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

# Extensions
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # --- Config ---
    app.config['SECRET_KEY'] = 'supersecretkey123'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'smartbank.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB, adjust as needed


    # --- Init extensions ---
    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    # --- Login manager ---
    login_manager.login_view = "main.login"
    login_manager.login_message_category = "info"

    # --- Import models ---
    from . import models

    # --- Register blueprints ---
    from .routes import main as main_blueprint
    from .customer_routes import customer_bp
    from .staff_routes import staff_bp

    app.register_blueprint(main_blueprint)
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(staff_bp, url_prefix='/staff')

    return app
