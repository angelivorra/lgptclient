import os
import subprocess

from flask import Flask, render_template
from helpers import check_service_status  # Import the helper function

def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass



    @app.route('/', methods=('GET', 'POST'))
    def home():
        name = "Cliente01"
        is_active_b, logs_b = check_service_status("bluetooth")
        return render_template('home.html', is_active_b = is_active_b, logs_b = logs_b)

    return app