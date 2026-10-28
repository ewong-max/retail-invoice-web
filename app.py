"""Retail Invoice - web version.

Runs a small web server on this PC only (127.0.0.1) and opens the browser.
Data: SQLite in Documents\\RetailInvoicesWeb. PDFs: reportlab.
"""
import io
import os
import socket
import sqlite3
import sys
import threading
import webbrowser
from datetime import date, datetime

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------- settings
PORT = 5080
DEFAULT_CUSTOMER = "Cash"
CURRENCY = "RM"
DEFAULT_SHOP = "YK Enterprise\n"
DATA_DIR = os.environ.get("RETAIL_INVOICE_DATA") or os.path.join(
    os.path.expanduser("~"), "Documents", "RetailInvoicesWeb")
DB_PATH = os.path.join(DATA_DIR, "invoices.db")
SHOP_FILE = os.path.join(DATA_DIR, "shop_details.txt")

# when packaged by PyInstaller, templates live in sys._MEIPASS
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, template_folder=os.path.join(BASE, "templates"))


def read_shop():
    """Shop name (line 1) + address lines. Edit shop_details.txt in the data folder to change."""
    if not os.path.exists(SHOP_FILE):
        with open(SHOP_FILE, "w", encoding="utf-8") as f:
            f.write(DEFAULT_SHOP)
    with open(SHOP_FILE, encoding="utf-8") as f:
        lines = [l.rstrip() for l in f if l.strip()]
    return lines or ["MY SHOP"]


@app.template_filter("money")
def money(v):
    return f"{v:,.2f}"


@app.template_filter("qty")
def qty_text(q):
    return str(int(q)) if q == int(q) else f"{q:g}"


@app.template_filter("dmy")
def dmy(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


@app.context_processor
def globals_for_templates():
    return {"shop": read_shop(), "currency": CURRENCY}


# ---------------------------------------------------------------- database
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = connect()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inv_no TEXT, inv_date TEXT, customer TEXT, total REAL,
            status TEXT DEFAULT 'ACTIVE', updated_at TEXT);
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER, description TEXT, qty REAL, price REAL);
    """)
    con.close()


def save_invoice(inv_id, inv_date, customer, items):
    """Insert a new invoice (inv_id=None) or overwrite an existing one. Returns the id."""
    total = round(sum(i["qty"] * i["price"] for i in items), 2)
    now = datetime.now().isoformat(timespec="seconds")
    con = connect()
    with con:
        if inv_id is None:
            cur = con.execute("INSERT INTO invoices (inv_date, customer, total, updated_at) VALUES (?,?,?,?)",
                              (inv_date, customer, total, now))
            inv_id = cur.lastrowid
            con.execute("UPDATE invoices SET inv_no=? WHERE id=?", (f"INV-{inv_id:06d}", inv_id))
        else:
            con.execute("UPDATE invoices SET inv_date=?, customer=?, total=?, updated_at=? WHERE id=?",
                        (inv_date, customer, total, now, inv_id))
            con.execute("DELETE FROM items WHERE invoice_id=?", (inv_id,))
        con.executemany("INSERT INTO items (invoice_id, description, qty, price) VALUES (?,?,?,?)",
                        [(inv_id, i["description"], i["qty"], i["price"]) for i in items])
    con.close()
    return inv_id


def load_invoice(inv_id):
    con = connect()
    row = con.execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()
    if row is None:
        con.close()
        abort(404)
    inv = dict(row)
    inv["items"] = [{"description": r["description"], "qty": r["qty"], "price": r["price"]} for r in
                    con.execute("SELECT * FROM items WHERE invoice_id=? ORDER BY id", (inv_id,))]
    con.close()
    return inv


def list_invoices(search=""):
    try:  # dates are stored as yyyy-mm-dd; let people search the way they write them
        search = datetime.strptime(search, "%d/%m/%Y").date().isoformat()
    except ValueError:
        pass
    like = f"%{search}%"
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM invoices WHERE inv_no LIKE ? OR customer LIKE ? OR inv_date LIKE ? "
        "ORDER BY id DESC", (like, like, like))]
    con.close()
    return rows


# ---------------------------------------------------------------- PDF
def make_pdf(inv, out):
    """Draw the invoice as an A4 PDF into `out` (a file path or a file-like object)."""
    W, H = A4
    L, R = 20 * mm, W - 20 * mm
    c = canvas.Canvas(out, pagesize=A4)
    c.setTitle(inv["inv_no"])
    shop = read_shop()

    def fit(text, width, font="Helvetica", size=10):
        while text and c.stringWidth(text, font, size) > width:
            text = text[:-1]
        return text

    def page_header():
        y = H - 20 * mm
        c.setFont("Helvetica-Bold", 16)
        c.drawString(L, y, shop[0])
        c.setFont("Helvetica", 9)
        for line in shop[1:]:
            y -= 4.5 * mm
            c.drawString(L, y, line)
        c.setFont("Helvetica-Bold", 18)
        c.drawRightString(R, H - 20 * mm, "INVOICE")
        c.setFont("Helvetica", 10)
        c.drawRightString(R, H - 27 * mm, f"No: {inv['inv_no']}")
        c.drawRightString(R, H - 32 * mm, f"Date: {dmy(inv['inv_date'])}")
        y = min(y, H - 32 * mm) - 12 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(L, y, f"Customer: {inv['customer']}")
        y -= 9 * mm
        c.line(L, y + 4 * mm, R, y + 4 * mm)
        c.drawString(L, y, "No")
        c.drawString(L + 10 * mm, y, "Item")
        c.drawRightString(130 * mm, y, "Qty")
        c.drawRightString(158 * mm, y, f"Price ({CURRENCY})")
        c.drawRightString(R, y, f"Amount ({CURRENCY})")
        c.line(L, y - 2.5 * mm, R, y - 2.5 * mm)
        if inv["status"] == "CANCELLED":
            c.saveState()
            c.setFillColorRGB(1, 0, 0, alpha=0.25)
            c.setFont("Helvetica-Bold", 80)
            c.translate(W / 2, H / 2)
            c.rotate(35)
            c.drawCentredString(0, 0, "CANCELLED")
            c.restoreState()
        c.setFont("Helvetica", 10)
        return y - 8 * mm

    y = page_header()
    for n, it in enumerate(inv["items"], 1):
        if y < 35 * mm:
            c.showPage()
            y = page_header()
        c.drawString(L, y, str(n))
        c.drawString(L + 10 * mm, y, fit(it["description"], 85 * mm))
        c.drawRightString(130 * mm, y, qty_text(it["qty"]))
        c.drawRightString(158 * mm, y, money(it["price"]))
        c.drawRightString(R, y, money(it["qty"] * it["price"]))
        y -= 6 * mm

    c.line(L, y + 2 * mm, R, y + 2 * mm)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(158 * mm, y - 5 * mm, "TOTAL")
    c.drawRightString(R, y - 5 * mm, f"{CURRENCY} {money(inv['total'])}")
    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(W / 2, 15 * mm, "Thank you for your purchase!")
    c.save()


# ---------------------------------------------------------------- pages
@app.route("/")
def new_invoice():
    blank = {"id": None, "inv_no": None, "inv_date": date.today().isoformat(),
             "customer": DEFAULT_CUSTOMER, "status": "ACTIVE", "items": []}
    return render_template("editor.html", inv=blank)


@app.route("/invoice/<int:inv_id>")
def edit_invoice(inv_id):
    return render_template("editor.html", inv=load_invoice(inv_id))


@app.route("/history")
def history():
    q = request.args.get("q", "").strip()
    return render_template("history.html", invoices=list_invoices(q), q=q)


@app.route("/invoice/<int:inv_id>/print")
def print_invoice(inv_id):
    return render_template("print.html", inv=load_invoice(inv_id))


@app.route("/invoice/<int:inv_id>/pdf")
def pdf_invoice(inv_id):
    inv = load_invoice(inv_id)
    buf = io.BytesIO()
    make_pdf(inv, buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", download_name=f"{inv['inv_no']}.pdf",
                     as_attachment=request.args.get("download") == "1")


@app.post("/invoice/<int:inv_id>/cancel")
def cancel_invoice(inv_id):
    load_invoice(inv_id)  # 404 if missing
    con = connect()
    with con:
        con.execute("UPDATE invoices SET status='CANCELLED', updated_at=? WHERE id=?",
                    (datetime.now().isoformat(timespec="seconds"), inv_id))
    con.close()
    return redirect(request.form.get("next") or url_for("history"))


@app.post("/api/save")
def api_save():
    """Body: {id, inv_date: 'YYYY-MM-DD', customer, items: [{description, qty, price}]}"""
    d = request.get_json(force=True)
    inv_id = d.get("id")
    if inv_id is not None and load_invoice(inv_id)["status"] == "CANCELLED":
        return jsonify(error="This invoice is cancelled and cannot be changed."), 400
    try:
        datetime.strptime(d.get("inv_date", ""), "%Y-%m-%d")
        items = [{"description": str(i["description"]).strip(), "qty": float(i["qty"]),
                  "price": float(i["price"])} for i in d.get("items", [])]
    except (ValueError, KeyError, TypeError):
        return jsonify(error="Please check the date, quantities and prices."), 400
    if not items:
        return jsonify(error="Please add at least one item."), 400
    if any(not i["description"] or i["qty"] <= 0 or i["price"] < 0 for i in items):
        return jsonify(error="Each item needs a name, a quantity above 0 and a price."), 400
    customer = (d.get("customer") or "").strip() or DEFAULT_CUSTOMER
    inv_id = save_invoice(inv_id, d["inv_date"], customer, items)
    return jsonify(invoice=load_invoice(inv_id))


# ---------------------------------------------------------------- start
def already_running():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


if __name__ == "__main__":
    init_db()
    read_shop()
    url = f"http://127.0.0.1:{PORT}/"
    if already_running():          # second double-click: just open another browser tab
        webbrowser.open(url)
        sys.exit()
    print("=" * 60)
    print(f"  Retail Invoice is running at {url}")
    print("  Keep this window open while using the app.")
    print("  Close this window to shut the app down.")
    print(f"  Data folder: {DATA_DIR}")
    print("=" * 60)
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    from waitress import serve
    serve(app, host="127.0.0.1", port=PORT)
