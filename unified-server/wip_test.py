# -*- coding: utf-8 -*-

from flask import Flask
import logging

# 直接 import 你的 blueprint 檔
from wip_automation_blueprint import wip_automation_bp


logging.basicConfig(level=logging.INFO)

def create_app():
    app = Flask(__name__)

    # 掛 blueprint
    app.register_blueprint(wip_automation_bp)

    return app


if __name__ == "__main__":
    app = create_app()

    print("🚀 WIP test server start at 0.0.0.0:5099")
    app.run(host="0.0.0.0", port=5099, debug=True)
