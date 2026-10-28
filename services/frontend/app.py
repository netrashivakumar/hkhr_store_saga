import os
from flask import Flask, render_template

app = Flask(__name__)

# Public URL of the order-service, e.g. https://hkhr-order-service.onrender.com
ORDER_API_URL = os.environ.get("ORDER_API_URL", "http://localhost:5001")


@app.route("/")
def index():
    return render_template("index.html", api_url=ORDER_API_URL)


@app.route("/health")
def health():
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
