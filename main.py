import sys
import sqlite3
import requests
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QTextEdit
)
from datetime import datetime
import json
import os
from time import time
import threading
from flask import Flask, request, jsonify

# --------------------
# Zoho Creator API Yardımcı
# --------------------
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REFRESH_TOKEN = "YOUR_REFRESH_TOKEN"
API_DOMAIN = "https://www.zohoapis.eu"
OWNER_NAME = "YOUR_OWNER_NAME"
APP_LINK_NAME = "YOUR_APP_LINK_NAME"
ACCESS_TOKEN = None
ACCOUNTS_DOMAIN = "https://accounts.zoho.eu"
TOKEN_FILE = "token.json"

def save_token_file(access_token, expires_in=None):
    try:
        payload = {"access_token": access_token, "saved_at": int(time())}
        if expires_in:
            payload["expires_in"] = int(expires_in)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception as e:
        print("token.json kaydedilemedi:", e)

def load_token_file():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("token.json okunamadı:", e)
        return None

_tok = load_token_file()
if _tok and "access_token" in _tok:
    ACCESS_TOKEN = _tok["access_token"]

def refresh_access_token():
    global ACCESS_TOKEN
    url = f"{ACCOUNTS_DOMAIN}/oauth/v2/token"
    data = {
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token"
    }
    try:
        resp = requests.post(url, data=data, timeout=20)
        print("Refresh token endpoint response:", resp.status_code)
        print("Refresh response text:", resp.text)
        if resp.status_code != 200:
            return False
        json_resp = resp.json()
        if "access_token" in json_resp:
            ACCESS_TOKEN = json_resp["access_token"]
            save_token_file(ACCESS_TOKEN, expires_in=json_resp.get("expires_in"))
            print("Yeni access token alındı (kayıt edildi).")
            return True
        else:
            print("Refresh token yanıtı hatalı:", json_resp)
            return False
    except Exception as e:
        print("Refresh token işlenirken hata:", e)
        return False
    
def check_record_exists(report_name, record_id):
    """Creator'da kayıt var mı diye kontrol eder."""
    global ACCESS_TOKEN
    if not ACCESS_TOKEN:
        if not refresh_access_token():
            return False

    url = f"{API_DOMAIN}/creator/v2/data/{OWNER_NAME}/{APP_LINK_NAME}/report/{report_name}/{record_id}"
    headers = {"Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}"}

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            return True
        elif resp.status_code == 404:
            return False
        elif resp.status_code in (401, 403):
            if refresh_access_token():
                return check_record_exists(report_name, record_id)
        return False
    except Exception as e:
        print("⚠️ check_record_exists hata:", e)
        return False


def send_to_creator(form_link_name, data, method="POST", record_id=None):
    """Zoho Creator’a veri gönderir (ekle/güncelle)."""
    global ACCESS_TOKEN
    if not ACCESS_TOKEN:
        if not refresh_access_token():
            return False, "Token alınamadı."

    headers = {"Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}"}

    try:
        if method == "PUT" and record_id:
            # Güncelleme
            url = f"{API_DOMAIN}/creator/v2/data/{OWNER_NAME}/{APP_LINK_NAME}/form/{form_link_name}/{record_id}"
            resp = requests.put(url, headers=headers, json={"data": data}, timeout=20)

        else:
            # Ekleme (önce var mı kontrol et)
            if data.get("ID"):
                report_name = f"All_{form_link_name}"
                exists = check_record_exists(report_name, data["ID"])
                if exists:
                    return False, f"Kayıt zaten Creator'da var (ID={data['ID']})."

            url = f"{API_DOMAIN}/creator/v2/data/{OWNER_NAME}/{APP_LINK_NAME}/form/{form_link_name}"
            resp = requests.post(url, headers=headers, json={"data": data}, timeout=20)

        if resp.status_code in (200, 201):
            return True, resp.json()
        elif resp.status_code in (401, 403):
            if refresh_access_token():
                return send_to_creator(form_link_name, data, method, record_id)
        return False, f"Hata: {resp.status_code}, {resp.text}"

    except Exception as e:
        return False, f"send_to_creator hata: {e}"


def extract_record_id_from_data(data_obj):
    if isinstance(data_obj, dict):
        return data_obj.get("ID")
    if isinstance(data_obj, list) and data_obj:
        elem = data_obj[0]
        if isinstance(elem, dict):
            return elem.get("ID")
    return None

from functools import partial

def delete_from_creator(form_name, record_id):
    """Zoho Creator’dan kayıt siler (önce var mı kontrol eder)."""
    global ACCESS_TOKEN
    if not ACCESS_TOKEN:
        if not refresh_access_token():
            return False

    report_name = f"All_{form_name}"

    # Silmeden önce kontrol
    exists = check_record_exists(report_name, record_id)
    if not exists:
        print(f"⚠️ {form_name} id={record_id} Creator'da zaten yok, silme atlanıyor.")
        return True

    url = f"{API_DOMAIN}/creator/v2/data/{OWNER_NAME}/{APP_LINK_NAME}/report/{report_name}/{record_id}"
    headers = {"Authorization": f"Zoho-oauthtoken {ACCESS_TOKEN}"}

    try:
        resp = requests.delete(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            return True
        elif resp.status_code in (401, 403):
            if refresh_access_token():
                return delete_from_creator(form_name, record_id)
        return False
    except Exception as e:
        print("⚠️ delete_from_creator hata:", e)
        return False








# --------------------
# SQLite Veritabanı
# --------------------
def init_db():
    conn = sqlite3.connect("depo.db")
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        description TEXT,
        quantity INTEGER DEFAULT 0,
        shelf TEXT,
        creator_id TEXT
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_id INTEGER,
        movement_type TEXT,
        quantity INTEGER,
        shelf TEXT,
        creator_id TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(part_id) REFERENCES parts(id)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS work_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        records TEXT,
        required_parts TEXT,
        status TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        creator_id TEXT
    )""")
    conn.commit()
    conn.close()

# --------------------
# Flask Webhook Listener
# --------------------
app = Flask(__name__)

# Flask Webhook Listener
@app.route('/creator-webhook', methods=['POST'])
def creator_webhook():
    data = request.json
    print("Webhook payload received:", data)

    # Work Order ise kayıt ekle
    if "Maintenance_Repair_Records" in data:
        records = data.get("Maintenance_Repair_Records", "")
        parts = data.get("Required_Parts", "")
        status = data.get("Status_Information", "")

        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()

        # Aynı kayıt zaten varsa ekleme (tekilleştirme)
        cursor.execute("""
            SELECT COUNT(*) FROM work_orders 
            WHERE records=? AND required_parts=? AND status=?
        """, (records, parts, status))
        count = cursor.fetchone()[0]

        if count == 0:
            cursor.execute(
                "INSERT INTO work_orders (records, required_parts, status) VALUES (?, ?, ?)",
                (records, parts, status)
            )
            conn.commit()

        conn.close()

    return jsonify({"status": "success", "message": "Payload saved", "received_payload": data})






def run_server(host="0.0.0.0", port=5000):
    app.run(host=host, port=port)
# --------------------
# Ana Pencere
# --------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Depo Yönetim Uygulaması")
        self.setGeometry(100, 100, 1200, 600)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.stok_tab = QWidget()
        self.sayim_tab = QWidget()
        self.is_emirleri_tab = QWidget()
        self.senkron_tab = QWidget()

        self.stok_tab.layout = QVBoxLayout()
        self.sayim_tab.layout = QVBoxLayout()
        self.is_emirleri_tab.layout = QVBoxLayout()
        self.senkron_tab.layout = QVBoxLayout()

        self.tabs.addTab(self.stok_tab, "Stok Hareketleri")
        self.tabs.addTab(self.sayim_tab, "Sayım")
        self.tabs.addTab(self.is_emirleri_tab, "İş Emirleri")
        self.tabs.addTab(self.senkron_tab, "Senkronizasyon")

        self.info_label = QLabel("")
        self.senkron_tab.layout.addWidget(self.info_label)

        self.init_stok_tab()
        self.init_sayim_tab()
        self.init_is_emirleri_tab()
        self.init_senkron_tab()

    # --------------------
    # Stok Hareketleri Sekmesi
    # --------------------
    def init_stok_tab(self):
        self.part_code_input = QLineEdit()
        self.part_code_input.setPlaceholderText("Parça Kodu")
        self.quantity_input = QLineEdit()
        self.quantity_input.setPlaceholderText("Miktar")
        entry_button = QPushButton("Giriş")
        exit_button = QPushButton("Çıkış")

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.part_code_input)
        h_layout.addWidget(self.quantity_input)
        h_layout.addWidget(entry_button)
        h_layout.addWidget(exit_button)
        self.stok_tab.layout.addLayout(h_layout)

        self.stok_info_label = QLabel("")
        self.stok_tab.layout.addWidget(self.stok_info_label)

        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(6)
        self.stock_table.setHorizontalHeaderLabels(["Parça Kodu", "Eklenen/Çıkarılan", "Stok", "Hareket", "Tarih", "Sil"])
        self.stock_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stok_tab.layout.addWidget(self.stock_table)

        self.stok_tab.setLayout(self.stok_tab.layout)

        entry_button.clicked.connect(lambda: self.add_stock("Giriş"))
        exit_button.clicked.connect(lambda: self.add_stock("Çıkış"))

        self.load_stock_table()

    def add_stock(self, movement):
        code = self.part_code_input.text().strip()
        try:
            quantity = int(self.quantity_input.text())
        except ValueError:
            self.stok_info_label.setText("Hatalı miktar girdiniz!")
            return
        if not code:
            self.stok_info_label.setText("Parça kodu boş olamaz!")
            return

        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, quantity, creator_id FROM parts WHERE code = ?", (code,))
        result = cursor.fetchone()
        if result:
            part_id, current_qty, part_creator_id = result
            new_qty = current_qty + quantity if movement == "Giriş" else current_qty - quantity
            cursor.execute("UPDATE parts SET quantity=? WHERE id=?", (new_qty, part_id))
        else:
            cursor.execute("INSERT INTO parts (code, description, quantity, shelf, creator_id) VALUES (?, ?, ?, ?, ?)",
                        (code, "", quantity if movement=="Giriş" else 0, "", None))
            part_id = cursor.lastrowid
            new_qty = quantity if movement=="Giriş" else 0
            part_creator_id = None

        # Stock movement kaydı SQLite
        cursor.execute("INSERT INTO stock_movements (part_id, movement_type, quantity) VALUES (?, ?, ?)",
                    (part_id, movement, quantity))
        local_movement_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Creator payload
        dt_str = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
        movement_map = {"Giriş": "added", "Çıkış": "removed", "Sayım": "count"}
        payload = {
            "Part_Code": code, #3423
            "Added_Removed": int(quantity), #25
            "Stock": int(new_qty),
            "Movement": movement_map[movement],
            "Date_Time": dt_str
        }

        success, res = send_to_creator("Stock_Movements", payload, record_id=None if not part_creator_id else part_creator_id)
        if success:
            new_creator_id = extract_record_id_from_data(res)
            # SQLite stock_movements kaydına creator_id ekle
            conn = sqlite3.connect("depo.db")
            c = conn.cursor()
            c.execute("UPDATE stock_movements SET creator_id=? WHERE id=?", (new_creator_id, local_movement_id))
            # Parça için de creator_id boşsa ekle
            if not part_creator_id:
                c.execute("UPDATE parts SET creator_id=? WHERE id=?", (new_creator_id, part_id))
            conn.commit()
            conn.close()

        self.stok_info_label.setText("Stock Movements: " + ("Başarılı" if success else f"Hata: {res}"))

        self.part_code_input.setText("")
        self.quantity_input.setText("")
        self.load_stock_table()


    def load_stock_table(self):
        self.stock_table.setRowCount(0)
        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, p.code, s.movement_type, s.quantity, s.date
            FROM stock_movements s
            JOIN parts p ON s.part_id = p.id
            ORDER BY s.id ASC
        """)
        records = cursor.fetchall()
        conn.close()

        for row_idx, row_data in enumerate(records):
            movement_id, code, movement_type, movement_qty, date = row_data
            conn2 = sqlite3.connect("depo.db")
            cursor2 = conn2.cursor()
            cursor2.execute("SELECT quantity FROM parts WHERE code = ?", (code,))
            stock_after = cursor2.fetchone()[0]
            conn2.close()

            self.stock_table.insertRow(row_idx)
            self.stock_table.setItem(row_idx, 0, QTableWidgetItem(str(code)))
            self.stock_table.setItem(row_idx, 1, QTableWidgetItem(str(movement_qty)))
            self.stock_table.setItem(row_idx, 2, QTableWidgetItem(str(stock_after)))
            self.stock_table.setItem(row_idx, 3, QTableWidgetItem(str(movement_type)))
            self.stock_table.setItem(row_idx, 4, QTableWidgetItem(str(date)))

            delete_btn = QPushButton("Sil")
            delete_btn.clicked.connect(lambda _, mid=movement_id: self.delete_stock(mid))
            self.stock_table.setCellWidget(row_idx, 5, delete_btn)
    # --------------------
    # Sayım Sekmesi
    # --------------------
    def init_sayim_tab(self):
        self.shelf_input = QLineEdit()
        self.shelf_input.setPlaceholderText("Raf/Lokasyon")
        self.count_code_input = QLineEdit()
        self.count_code_input.setPlaceholderText("Parça Kodu")
        self.count_quantity_input = QLineEdit()
        self.count_quantity_input.setPlaceholderText("Sayım Miktarı")

        count_button = QPushButton("Sayımı Kaydet")

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.shelf_input)
        h_layout.addWidget(self.count_code_input)
        h_layout.addWidget(self.count_quantity_input)
        h_layout.addWidget(count_button)
        self.sayim_tab.layout.addLayout(h_layout)

        self.count_table = QTableWidget()
        self.count_table.setColumnCount(6)
        self.count_table.setHorizontalHeaderLabels(["Parça Kodu", "Mevcut Stok", "Sayım Miktarı", "Fark", "Raf/Lokasyon", "Sil"])
        self.sayim_tab.layout.addWidget(self.count_table)

        self.sayim_tab.setLayout(self.sayim_tab.layout)

        count_button.clicked.connect(self.add_count)
        self.load_count_table()

    def add_count(self):
        code = self.count_code_input.text().strip()
        shelf = self.shelf_input.text().strip()
        try:
            counted_qty = int(self.count_quantity_input.text())
        except ValueError:
            self.stok_info_label.setText("Sayım miktarı hatalı!")
            return
        if not code:
            self.stok_info_label.setText("Parça kodu boş olamaz!")
            return

        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, quantity, creator_id FROM parts WHERE code = ?", (code,))
        result = cursor.fetchone()
        if result:
            part_id, current_qty, part_creator_id = result
        else:
            cursor.execute(
                "INSERT INTO parts (code, description, quantity, shelf, creator_id) VALUES (?, ?, ?, ?, ?)",
                (code, "", 0, shelf, None)
            )
            part_id = cursor.lastrowid
            current_qty = 0
            part_creator_id = None
            conn.commit()

        difference = counted_qty - current_qty
        new_qty = counted_qty
        cursor.execute("UPDATE parts SET quantity=?, shelf=? WHERE id=?", (new_qty, shelf, part_id))
        cursor.execute(
            "INSERT INTO stock_movements (part_id, movement_type, quantity, shelf) VALUES (?, ?, ?, ?)",
            (part_id, "Sayım", difference, shelf)
        )
        local_movement_id = cursor.lastrowid
        conn.commit()
        conn.close()

        dt_str = datetime.now().strftime("%d-%b-%Y %H:%M:%S")

        # --- Stock Movements raporuna gönderim ---
        movement_payload = {
            "Part_Code": code,
            "Added_Removed": int(difference),
            "Stock": int(new_qty),
            "Movement": "count",
            "Date_Time": dt_str
        }

        success1, res1 = send_to_creator("Stock_Movements", movement_payload, record_id=part_creator_id)
        if success1:
            new_creator_id = extract_record_id_from_data(res1)
            conn2 = sqlite3.connect("depo.db")
            c2 = conn2.cursor()
            c2.execute("UPDATE stock_movements SET creator_id=? WHERE id=?", (new_creator_id, local_movement_id))
            if not part_creator_id:
                c2.execute("UPDATE parts SET creator_id=? WHERE id=?", (new_creator_id, part_id))
            conn2.commit()
            conn2.close()

        # --- Stocks raporuna parça bazlı güncelleme/ekleme ---
        stock_payload = {
            "Part_Code": code,
            "Available_Quantity": int(new_qty),
            "Shelf_Location": shelf or ""
        }
        # Eğer parça daha önce Stocks raporuna eklenmişse güncelle, yoksa ekle
        success2, res2 = send_to_creator("Stocks", stock_payload, record_id=part_creator_id)
        if success2 and not part_creator_id:
            new_stock_id = extract_record_id_from_data(res2)
            if new_stock_id:
                conn3 = sqlite3.connect("depo.db")
                c3 = conn3.cursor()
                c3.execute("UPDATE parts SET creator_id=? WHERE id=?", (new_stock_id, part_id))
                conn3.commit()
                conn3.close()

        self.stok_info_label.setText(
            "Stock Movements: " + ("Başarılı" if success1 else f"Hata: {res1}") +
            " | Stocks: " + ("Başarılı" if success2 else f"Hata: {res2}")
        )

        self.count_code_input.setText("")
        self.count_quantity_input.setText("")
        self.shelf_input.setText("")
        self.load_count_table()
        self.load_stock_table()





    def load_count_table(self):
        self.count_table.setRowCount(0)
        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, p.code, s.quantity, s.movement_type, s.shelf, p.quantity
            FROM stock_movements s
            JOIN parts p ON s.part_id = p.id
            WHERE s.movement_type='Sayım'
            ORDER BY s.id ASC
        """)
        records = cursor.fetchall()
        conn.close()

        for row_idx, (mid, code, diff, mtype, shelf, stock_after) in enumerate(records):
            self.count_table.insertRow(row_idx)
            self.count_table.setItem(row_idx, 0, QTableWidgetItem(code))
            self.count_table.setItem(row_idx, 1, QTableWidgetItem(str(stock_after - diff)))
            self.count_table.setItem(row_idx, 2, QTableWidgetItem(str(stock_after)))
            self.count_table.setItem(row_idx, 3, QTableWidgetItem(str(diff)))
            self.count_table.setItem(row_idx, 4, QTableWidgetItem(str(shelf or "")))

            delete_btn = QPushButton("Sil")
            delete_btn.clicked.connect(lambda _, mid=mid: self.delete_stock(mid))
            self.count_table.setCellWidget(row_idx, 5, delete_btn)

    # --------------------
    # İş Emirleri Sekmesi
    # --------------------
    def init_is_emirleri_tab(self):
        self.records_input = QTextEdit()
        self.records_input.setPlaceholderText("Bakım / Onarım Kaydı")
        self.required_parts_input = QLineEdit()
        self.required_parts_input.setPlaceholderText("Gerekli Parçalar")
        self.status_input = QLineEdit()
        self.status_input.setPlaceholderText("Durum Bilgisi")

        save_btn = QPushButton("İş Emrini Kaydet")

        self.is_emirleri_tab.layout.addWidget(self.records_input)
        self.is_emirleri_tab.layout.addWidget(self.required_parts_input)
        self.is_emirleri_tab.layout.addWidget(self.status_input)
        self.is_emirleri_tab.layout.addWidget(save_btn)

        self.work_orders_table = QTableWidget()
        self.work_orders_table.setColumnCount(5)
        self.work_orders_table.setHorizontalHeaderLabels(["Bakım/Onarım Kaydı", "Gerekli Parçalar", "Durum", "Tarih", "Sil"])
        self.work_orders_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.is_emirleri_tab.layout.addWidget(self.work_orders_table)

        self.is_emirleri_tab.setLayout(self.is_emirleri_tab.layout)

        save_btn.clicked.connect(self.save_work_order)
        self.load_work_orders()

    def save_work_order(self):
        records = self.records_input.toPlainText().strip()
        parts = self.required_parts_input.text().strip()
        status = self.status_input.text().strip()

        if not records:
            self.info_label.setText("İş emri kaydı boş olamaz.")
            return

        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO work_orders (records, required_parts, status) VALUES (?, ?, ?)",
                       (records, parts, status))
        conn.commit()
        conn.close()

        success, res = send_to_creator("Work_Order", {
            "Maintenance_Repair_Records": records,
            "Required_Parts": parts,
            "Status_Information": status
        })

        if success:
            new_creator_id = extract_record_id_from_data(res)
            if new_creator_id:
                conn2 = sqlite3.connect("depo.db")
                c2 = conn2.cursor()
                c2.execute("SELECT id FROM work_orders ORDER BY id DESC LIMIT 1")
                last = c2.fetchone()
                if last:
                    local_id = last[0]
                    c2.execute("UPDATE work_orders SET creator_id=? WHERE id=?", (new_creator_id, local_id))
                    conn2.commit()
                conn2.close()

        self.info_label.setText("Work Order: " + ("Başarılı" if success else f"Hata: {res}"))
        self.records_input.clear()
        self.required_parts_input.clear()
        self.status_input.clear()
        self.load_work_orders()

    def load_work_orders(self):
        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, records, required_parts, status, date FROM work_orders ORDER BY id DESC")
        records = cursor.fetchall()
        conn.close()

        self.work_orders_table.setRowCount(len(records))
        for row_idx, (wid, recs, parts, status, date) in enumerate(records):
            self.work_orders_table.setItem(row_idx, 0, QTableWidgetItem(str(recs)))
            self.work_orders_table.setItem(row_idx, 1, QTableWidgetItem(str(parts)))
            self.work_orders_table.setItem(row_idx, 2, QTableWidgetItem(str(status)))
            self.work_orders_table.setItem(row_idx, 3, QTableWidgetItem(str(date)))

            del_btn = QPushButton("Sil")
            del_btn.clicked.connect(lambda _, id=wid: self.delete_work_order(id))
            self.work_orders_table.setCellWidget(row_idx, 4, del_btn)

    def delete_work_order(self, work_order_id):
        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT creator_id FROM work_orders WHERE id=?", (work_order_id,))
        creator_id = cursor.fetchone()
        if creator_id:
            creator_id = creator_id[0]
        cursor.execute("DELETE FROM work_orders WHERE id=?", (work_order_id,))
        conn.commit()
        conn.close()

        # Creator’dan sil
        if creator_id:
            delete_from_creator("All_Work_Orders", creator_id)  # <- Burayı All_Work_Orders yaptık

        self.load_work_orders()
        self.info_label.setText(f"İş Emri (id={work_order_id}) silindi.")




    # --------------------
    # Senkronizasyon Sekmesi
    # --------------------
    # --------------------
# Senkronizasyon Sekmesi
# --------------------
    def init_senkron_tab(self):
        # Butonlar
        sync_btn = QPushButton("Tüm Verileri Creator’a Gönder")
        refresh_btn = QPushButton("Tüm Tabloları Yenile")

        # Sekme layout'una ekle
        self.senkron_tab.layout.addWidget(sync_btn)
        self.senkron_tab.layout.addWidget(refresh_btn)
        self.senkron_tab.setLayout(self.senkron_tab.layout)

        # Buton click olayları
        sync_btn.clicked.connect(self.sync_data)
        refresh_btn.clicked.connect(self.load_all_tables)

    # Tüm tabloları yükleme fonksiyonu
    def load_all_tables(self):
        self.load_stock_table()     # Stok hareketleri tablosunu yükle
        self.load_count_table()     # Sayım tablosunu yükle
        self.load_work_orders()     # İş emirleri tablosunu yükle
        self.info_label.setText("Tüm tablolar yenilendi.")  # Kullanıcıya bilgi

    def sync_data(self):
        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, quantity, shelf, creator_id FROM parts")
        parts = cursor.fetchall()
        conn.close()

        for part_id, code, qty, shelf, creator_id in parts:
            data_to_send = {
                "Part_Code": code,
                "Available_Quantity": int(qty),
                "Shelf_Location": shelf or ""
            }

            success, res = send_to_creator("Stock", data_to_send, record_id=creator_id if creator_id else None)

            if success and not creator_id:
                new_id = extract_record_id_from_data(res)
                if new_id:
                    conn2 = sqlite3.connect("depo.db")
                    c2 = conn2.cursor()
                    c2.execute("UPDATE parts SET creator_id=? WHERE id=?", (new_id, part_id))
                    conn2.commit()
                    conn2.close()

        self.info_label.setText("Tüm parçalar Creator’a gönderildi.")

    # --------------------
    # Silme Fonksiyonu (stok hareketleri/sayım)
    # --------------------
    def delete_stock(self, movement_id):
        conn = sqlite3.connect("depo.db")
        cursor = conn.cursor()
        cursor.execute("SELECT part_id, movement_type, quantity, creator_id FROM stock_movements WHERE id=?", (movement_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return

        part_id, movement_type, quantity, movement_creator_id = result
        cursor.execute("SELECT quantity FROM parts WHERE id=?", (part_id,))
        current_qty = cursor.fetchone()[0]

        if movement_type in ("Giriş", "Sayım"):
            new_qty = current_qty - quantity
        elif movement_type == "Çıkış":
            new_qty = current_qty + quantity
        else:
            new_qty = current_qty

        cursor.execute("UPDATE parts SET quantity=? WHERE id=?", (new_qty, part_id))
        cursor.execute("DELETE FROM stock_movements WHERE id=?", (movement_id,))
        conn.commit()
        conn.close()

        # --- Creator’a otomatik silme ---
        if movement_creator_id:
            delete_from_creator("Stock_Movements", movement_creator_id)

        self.load_stock_table()
        self.load_count_table()


# --------------------
# Uygulama Başlat
# --------------------
if __name__ == "__main__":
    init_db()
    # Flask server arka planda
    server_thread = threading.Thread(target=run_server, kwargs={"host":"0.0.0.0","port":5000}, daemon=True)
    server_thread.start()
    print("Webhook server başlatıldı: http://0.0.0.0:5000/creator-webhook")

    # PyQt uygulaması başlat
    app_qt = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app_qt.exec_())
