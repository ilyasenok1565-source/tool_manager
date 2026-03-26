import sqlite3
from datetime import datetime
import bcrypt

DB_NAME = "tools.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tools
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  qr_code TEXT UNIQUE NOT NULL,
                  status TEXT DEFAULT 'in_stock',
                  issued_to INTEGER,
                  container TEXT,
                  inventory_number TEXT,
                  brand TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS employees
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  tab_number TEXT UNIQUE NOT NULL,
                  qr_code TEXT UNIQUE NOT NULL,
                  section TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  tool_id INTEGER NOT NULL,
                  employee_id INTEGER,
                  action TEXT NOT NULL,
                  timestamp TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  hashed_password TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'worker')''')
    # Добавляем новые столбцы, если их нет
    try:
        c.execute("ALTER TABLE employees ADD COLUMN section TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE tools ADD COLUMN inventory_number TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE tools ADD COLUMN brand TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def get_tool_by_qr(qr: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, qr_code, status, issued_to, container, inventory_number, brand FROM tools WHERE qr_code=?", (qr,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "qr_code": row[2], "status": row[3],
                "issued_to": row[4], "container": row[5], "inventory_number": row[6], "brand": row[7]}
    return None

def get_employee_by_qr(qr: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, tab_number, qr_code, section FROM employees WHERE qr_code=?", (qr,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "tab_number": row[2], "qr_code": row[3], "section": row[4]}
    return None

def issue_tool(tool_id: int, employee_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE tools SET status='issued', issued_to=? WHERE id=?", (employee_id, tool_id))
    c.execute("INSERT INTO transactions (tool_id, employee_id, action, timestamp) VALUES (?,?,?,?)",
              (tool_id, employee_id, "issue", datetime.now().isoformat()))
    conn.commit()
    conn.close()

def return_tool(tool_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE tools SET status='in_stock', issued_to=NULL WHERE id=?", (tool_id,))
    c.execute("INSERT INTO transactions (tool_id, employee_id, action, timestamp) VALUES (?,?,?,?)",
              (tool_id, None, "return", datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_issued_tools():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT tools.id, tools.name, employees.name, employees.tab_number, tools.container
                 FROM tools
                 LEFT JOIN employees ON tools.issued_to = employees.id
                 WHERE tools.status='issued' ''')
    rows = c.fetchall()
    conn.close()
    return [{"tool_id": r[0], "tool_name": r[1], "employee_name": r[2], "tab_number": r[3], "container": r[4]} for r in rows]

def get_all_tools():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, qr_code, status, container, inventory_number, brand FROM tools")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "qr_code": r[2], "status": r[3], "container": r[4], "inventory_number": r[5], "brand": r[6]} for r in rows]

def get_all_employees():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, tab_number, qr_code, section FROM employees")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "tab_number": r[2], "qr_code": r[3], "section": r[4]} for r in rows]

def create_user(username: str, password: str, role: str = "worker"):
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, hashed_password, role) VALUES (?,?,?)",
                  (username, hashed, role))
        conn.commit()
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()
    return True

def get_user_by_username(username: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, username, hashed_password, role FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "hashed_password": row[2], "role": row[3]}
    return None

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def insert_sample_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tools")
    if c.fetchone()[0] == 0:
        tools = [
            ("УШМ", "tool_1"),
            ("Ключ на 30 мм", "tool_2"),
            ("ПШМ", "tool_3"),
            ("Бита (набор 10 шт)", "tool_4"),
            ("Сверло 12 мм (упаковка 5 шт)", "tool_5"),
            ("Молоток", "tool_6"),
            ("Кувалда 5 кг", "tool_7"),
            ("Саморез по дереву 45 мм (упаковка 100 шт)", "tool_8"),
            ("Монтажная пена (баллон)", "tool_9"),
            ("Привязь страховочная", "tool_10"),
            ("Маркер белый (упаковка 3 шт)", "tool_11"),
            ("Маркер черный (упаковка 3 шт)", "tool_12"),
            ("Домкрат бутылочный 35 т", "tool_13"),
            ("Бумага А4 (пачка)", "tool_14"),
            ("Сварочный аппарат", "tool_15"),
            ("Ключ на 24 мм", "tool_16"),
            ("Ключ на 12 мм", "tool_17"),
            ("Строительный фен", "tool_18"),
        ]
        c.executemany("INSERT INTO tools (name, qr_code) VALUES (?,?)", tools)

        employees = [
            ("Иванов Сергей Юрьевич", "2432", "emp_2432", "Монтажный участок"),
            ("Каримов Ильдар Низамович", "4325", "emp_4325", "Сварочный участок"),
            ("Рашитов Артур Назирович", "6664", "emp_6664", "Монтажный участок"),
            ("Степанов Василий Иванович", "6269", "emp_6269", "Такелажный участок"),
            ("Лапега Сергей Юрьевич", "3212", "emp_3212", "Монтажный участок"),
        ]
        c.executemany("INSERT INTO employees (name, tab_number, qr_code, section) VALUES (?,?,?,?)", employees)
        conn.commit()
    conn.close()

def insert_default_user():
    if not get_user_by_username("admin"):
        create_user("admin", "admin123", "admin")
    if not get_user_by_username("storekeeper"):
        create_user("storekeeper", "store123", "worker")
