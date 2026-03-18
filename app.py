from flask import Flask, request, jsonify, send_from_directory
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='.', static_url_path='')
DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def load_json(name):
    path = os.path.join(DATA_DIR, f'{name}.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_json(name, data):
    path = os.path.join(DATA_DIR, f'{name}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def next_id(data):
    return max((e.get('id', 0) for e in data), default=0) + 1


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# --- Artikel ---

@app.route('/api/articles', methods=['GET'])
def get_articles():
    return jsonify(load_json('articles'))


@app.route('/api/articles', methods=['POST'])
def create_article():
    body = request.get_json()
    data = load_json('articles')
    body['id'] = next_id(data)
    body['stock'] = body.get('stock', 0)
    body['created'] = datetime.now().isoformat()
    data.insert(0, body)
    save_json('articles', data)
    return jsonify(body), 201


@app.route('/api/articles/<int:aid>', methods=['PUT'])
def update_article(aid):
    body = request.get_json()
    data = load_json('articles')
    for i, e in enumerate(data):
        if e.get('id') == aid:
            body['id'] = aid
            body['created'] = e.get('created', '')
            data[i] = body
            break
    save_json('articles', data)
    return jsonify(body)


@app.route('/api/articles/<int:aid>', methods=['DELETE'])
def delete_article(aid):
    data = load_json('articles')
    data = [e for e in data if e.get('id') != aid]
    save_json('articles', data)
    return jsonify({'ok': True})


# --- Transaktionen (Belege) ---

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    return jsonify(load_json('transactions'))


@app.route('/api/transactions', methods=['POST'])
def create_transaction():
    body = request.get_json()
    txns = load_json('transactions')
    body['id'] = next_id(txns)
    body['date'] = body.get('date', datetime.now().strftime('%Y-%m-%d'))
    body['time'] = datetime.now().strftime('%H:%M')
    txns.insert(0, body)
    save_json('transactions', txns)

    articles = load_json('articles')
    for a in articles:
        if a.get('id') == body.get('articleId'):
            qty = body.get('quantity', 0)
            if body.get('type') == 'in':
                a['stock'] = a.get('stock', 0) + qty
            else:
                a['stock'] = max(0, a.get('stock', 0) - qty)
            break
    save_json('articles', articles)
    return jsonify(body), 201


# --- Ausgaben ---

@app.route('/api/expenses', methods=['GET'])
def get_expenses():
    return jsonify(load_json('expenses'))


@app.route('/api/expenses', methods=['POST'])
def create_expense():
    body = request.get_json()
    data = load_json('expenses')
    body['id'] = next_id(data)
    body['date'] = body.get('date', datetime.now().strftime('%Y-%m-%d'))
    data.insert(0, body)
    save_json('expenses', data)
    return jsonify(body), 201


@app.route('/api/expenses/<int:eid>', methods=['DELETE'])
def delete_expense(eid):
    data = load_json('expenses')
    data = [e for e in data if e.get('id') != eid]
    save_json('expenses', data)
    return jsonify({'ok': True})


# --- Kunden ---

@app.route('/api/customers', methods=['GET'])
def get_customers():
    return jsonify(load_json('customers'))


@app.route('/api/customers', methods=['POST'])
def create_customer():
    body = request.get_json()
    data = load_json('customers')
    body['id'] = next_id(data)
    body['created'] = datetime.now().isoformat()
    data.insert(0, body)
    save_json('customers', data)
    return jsonify(body), 201


@app.route('/api/customers/<int:cid>', methods=['PUT'])
def update_customer(cid):
    body = request.get_json()
    data = load_json('customers')
    for i, e in enumerate(data):
        if e.get('id') == cid:
            body['id'] = cid
            body['created'] = e.get('created', '')
            data[i] = body
            break
    save_json('customers', data)
    return jsonify(body)


@app.route('/api/customers/<int:cid>', methods=['DELETE'])
def delete_customer(cid):
    data = load_json('customers')
    data = [e for e in data if e.get('id') != cid]
    save_json('customers', data)
    return jsonify({'ok': True})


@app.route('/api/customers/<int:cid>/stats', methods=['GET'])
def customer_stats(cid):
    txns = load_json('transactions')
    articles = load_json('articles')
    art_map = {a['id']: a for a in articles}

    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    week_start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
    month_start = now.strftime('%Y-%m-01')
    year_start = now.strftime('%Y-01-01')

    customer_txns = [t for t in txns if t.get('customerId') == cid and t.get('type') == 'out']

    def calc_total(tx_list):
        total = 0
        for t in tx_list:
            art = art_map.get(t.get('articleId'))
            price = art.get('sellPrice', 0) if art else t.get('price', 0)
            total += price * t.get('quantity', 0)
        return total

    day_txns = [t for t in customer_txns if t.get('date', '') >= today]
    week_txns = [t for t in customer_txns if t.get('date', '') >= week_start]
    month_txns = [t for t in customer_txns if t.get('date', '') >= month_start]
    year_txns = [t for t in customer_txns if t.get('date', '') >= year_start]

    return jsonify({
        'today': calc_total(day_txns),
        'week': calc_total(week_txns),
        'month': calc_total(month_txns),
        'year': calc_total(year_txns),
        'todayCount': len(day_txns),
        'weekCount': len(week_txns),
        'monthCount': len(month_txns),
        'yearCount': len(year_txns),
        'transactions': customer_txns[:50]
    })


# --- Berichte ---

@app.route('/api/reports', methods=['GET'])
def get_reports():
    articles = load_json('articles')
    txns = load_json('transactions')
    expenses = load_json('expenses')

    total_stock = sum(a.get('stock', 0) for a in articles)
    total_value = sum(a.get('stock', 0) * a.get('price', 0) for a in articles)
    total_in = sum(t.get('quantity', 0) for t in txns if t.get('type') == 'in')
    total_out = sum(t.get('quantity', 0) for t in txns if t.get('type') == 'out')
    total_expenses = sum(e.get('amount', 0) for e in expenses)

    low = [a for a in articles if 0 < a.get('stock', 0) <= a.get('minStock', 5)]
    out = [a for a in articles if a.get('stock', 0) == 0]

    return jsonify({
        'totalArticles': len(articles),
        'totalStock': total_stock,
        'totalValue': total_value,
        'totalIn': total_in,
        'totalOut': total_out,
        'totalExpenses': total_expenses,
        'totalTransactions': len(txns),
        'lowStock': low,
        'outOfStock': out
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
