from flask import Flask, request, jsonify, send_from_directory
import json
import os
import psycopg
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='.', static_url_path='')
DATABASE_URL = os.environ.get('DATABASE_URL', '')


def get_db():
    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS store (
            name TEXT PRIMARY KEY,
            data JSONB NOT NULL DEFAULT '[]'::jsonb
        )
    ''')
    # Ensure all collections exist
    for name in ['articles', 'transactions', 'expenses', 'customers', 'catstock']:
        cur.execute(
            "INSERT INTO store (name, data) VALUES (%s, '[]'::jsonb) ON CONFLICT (name) DO NOTHING",
            (name,)
        )
    cur.close()
    conn.close()


def load_json(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT data FROM store WHERE name = %s", (name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        d = row[0]
        if isinstance(d, list):
            return d
        if isinstance(d, str):
            return json.loads(d)
        return list(d) if d else []
    return []


def save_json(name, data):
    j = json.dumps(data, ensure_ascii=False)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO store (name, data) VALUES (%s, %s::jsonb) ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data",
        (name, j)
    )
    cur.close()
    conn.close()


def next_id(data):
    return max((e.get('id', 0) for e in data), default=0) + 1


# Initialize DB on startup
if DATABASE_URL:
    try:
        init_db()
    except Exception as e:
        print(f"DB init error: {e}")


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
    body.pop('stock', None)
    body['created'] = datetime.now().isoformat()
    data.insert(0, body)
    save_json('articles', data)

    # Auto-create catstock entry for new categories
    cat = body.get('category', '')
    if cat:
        catstock = load_json('catstock')
        if not any(cs.get('category') == cat for cs in catstock):
            catstock.append({
                'id': next_id(catstock),
                'category': cat,
                'stock': 0,
                'minStock': 10
            })
            save_json('catstock', catstock)

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
    deleted = [e for e in data if e.get('id') == aid]
    data = [e for e in data if e.get('id') != aid]
    save_json('articles', data)

    # Remove catstock if no more articles in that category
    if deleted:
        cat = deleted[0].get('category', '')
        if cat and not any(a.get('category') == cat for a in data):
            catstock = load_json('catstock')
            catstock = [cs for cs in catstock if cs.get('category') != cat]
            save_json('catstock', catstock)

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

    # Generate unique receipt number for outgoing transactions
    if body.get('type') == 'out':
        now = datetime.now()
        out_count = sum(1 for t in txns if t.get('type') == 'out') + 1
        body['belegNr'] = f"A-{now.strftime('%Y%m%d')}-{out_count:04d}"
    txns.insert(0, body)
    save_json('transactions', txns)

    # Update article stock
    aid = body.get('articleId')
    qty = body.get('quantity', 0)
    cat_name = body.get('categoryName', '')
    articles = load_json('articles')

    if aid:
        for a in articles:
            if a.get('id') == aid:
                if not cat_name:
                    cat_name = a.get('category', '')
                if body.get('type') == 'in':
                    a['stock'] = a.get('stock', 0) + qty
                else:
                    a['stock'] = max(0, a.get('stock', 0) - qty)
                break
        save_json('articles', articles)

    # Sync category stock from article totals
    if cat_name:
        cat_total = sum(a.get('stock', 0) for a in articles if a.get('category') == cat_name)
        catstock = load_json('catstock')
        found = False
        for cs in catstock:
            if cs.get('category') == cat_name:
                cs['stock'] = cat_total
                found = True
                break
        if not found:
            catstock.append({
                'id': next_id(catstock),
                'category': cat_name,
                'stock': cat_total,
                'minStock': 10
            })
        save_json('catstock', catstock)

    return jsonify(body), 201


@app.route('/api/transactions/<int:tid>', methods=['DELETE'])
def delete_transaction(tid):
    txns = load_json('transactions')
    deleted = [t for t in txns if t.get('id') == tid]
    txns = [t for t in txns if t.get('id') != tid]
    save_json('transactions', txns)

    # Reverse the stock change
    if deleted:
        t = deleted[0]
        cat_name = t.get('categoryName', '')
        aid = t.get('articleId')
        qty = t.get('quantity', 0)

        # Reverse article stock
        if aid and qty:
            articles = load_json('articles')
            for a in articles:
                if a.get('id') == aid:
                    if not cat_name:
                        cat_name = a.get('category', '')
                    if t.get('type') == 'in':
                        a['stock'] = max(0, a.get('stock', 0) - qty)
                    else:
                        a['stock'] = a.get('stock', 0) + qty
                    break
            save_json('articles', articles)

            # Sync category stock from article totals
            if cat_name:
                cat_total = sum(a.get('stock', 0) for a in articles if a.get('category') == cat_name)
                catstock = load_json('catstock')
                for cs in catstock:
                    if cs.get('category') == cat_name:
                        cs['stock'] = cat_total
                        break
                save_json('catstock', catstock)

        elif cat_name and qty:
            catstock = load_json('catstock')
            for cs in catstock:
                if cs.get('category') == cat_name:
                    if t.get('type') == 'in':
                        cs['stock'] = max(0, cs.get('stock', 0) - qty)
                    else:
                        cs['stock'] = cs.get('stock', 0) + qty
                    break
            save_json('catstock', catstock)

    return jsonify({'ok': True})


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
            if t.get('price'):
                total += t.get('price', 0)
            else:
                art = art_map.get(t.get('articleId'))
                price = art.get('sellPrice', 0) if art else 0
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


# --- Kategorie-Bestand ---

@app.route('/api/catstock', methods=['GET'])
def get_catstock():
    return jsonify(load_json('catstock'))


@app.route('/api/catstock', methods=['POST'])
def set_catstock():
    body = request.get_json()
    data = load_json('catstock')

    # Delete mode
    if body.get('_delete'):
        data = [cs for cs in data if cs.get('category') != body.get('category')]
        save_json('catstock', data)
        return jsonify({'ok': True})

    found = False
    for entry in data:
        if entry.get('category') == body.get('category'):
            entry['stock'] = body.get('stock', entry.get('stock', 0))
            entry['minStock'] = body.get('minStock', entry.get('minStock', 10))
            if 'price' in body:
                entry['price'] = body['price']
            if 'sellPrice' in body:
                entry['sellPrice'] = body['sellPrice']
            found = True
            break
    if not found:
        body['id'] = next_id(data)
        body.setdefault('stock', 0)
        body.setdefault('minStock', 10)
        body.setdefault('price', 0)
        body.setdefault('sellPrice', 0)
        data.append(body)
    save_json('catstock', data)
    return jsonify(body)


# --- Berichte ---

@app.route('/api/reports', methods=['GET'])
def get_reports():
    articles = load_json('articles')
    txns = load_json('transactions')
    expenses = load_json('expenses')
    catstock = load_json('catstock')

    total_stock = sum(cs.get('stock', 0) for cs in catstock)
    total_in = sum(t.get('quantity', 0) for t in txns if t.get('type') == 'in')
    total_out = sum(t.get('quantity', 0) for t in txns if t.get('type') == 'out')
    total_expenses = sum(e.get('amount', 0) for e in expenses)

    low = [cs for cs in catstock if 0 < cs.get('stock', 0) <= cs.get('minStock', 10)]
    out = [cs for cs in catstock if cs.get('stock', 0) == 0]

    return jsonify({
        'totalArticles': len(articles),
        'totalStock': total_stock,
        'totalIn': total_in,
        'totalOut': total_out,
        'totalExpenses': total_expenses,
        'totalTransactions': len(txns),
        'lowStock': low,
        'outOfStock': out,
        'catstock': catstock
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
