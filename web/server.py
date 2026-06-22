from datetime import date
from flask import Flask, jsonify, render_template, request

SAMSUNG_TICKER = '005930'


def create_app(db):
    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/latest')
    def api_latest():
        ticker = request.args.get('ticker', SAMSUNG_TICKER)
        limit = int(request.args.get('limit', 60))
        return jsonify(db.get_latest(ticker, limit))

    @app.route('/api/prices')
    def api_prices():
        ticker = request.args.get('ticker', SAMSUNG_TICKER)
        dt = request.args.get('date', date.today().isoformat())
        return jsonify(db.get_by_date(ticker, dt))

    return app
