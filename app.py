from flask import Flask, request, jsonify, send_from_directory
import json
import os

app = Flask(__name__, static_folder='.', static_url_path='')
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/entries', methods=['GET'])
def get_entries():
    return jsonify(load_data())


@app.route('/api/entries', methods=['POST'])
def create_entry():
    body = request.get_json()
    data = load_data()
    body['id'] = max((e.get('id', 0) for e in data), default=0) + 1
    data.insert(0, body)
    save_data(data)
    return jsonify(body), 201


@app.route('/api/entries/<int:entry_id>', methods=['PUT'])
def update_entry(entry_id):
    body = request.get_json()
    data = load_data()
    for i, e in enumerate(data):
        if e.get('id') == entry_id:
            body['id'] = entry_id
            data[i] = body
            break
    save_data(data)
    return jsonify(body)


@app.route('/api/entries/<int:entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    data = load_data()
    data = [e for e in data if e.get('id') != entry_id]
    save_data(data)
    return jsonify({'ok': True})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
