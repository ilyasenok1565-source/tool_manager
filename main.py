import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import qrcode
import bcrypt

import database
from models import *

app = FastAPI()

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

database.init_db()
database.insert_sample_data()
database.insert_default_user()

os.makedirs("qrcodes", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/qrcodes", StaticFiles(directory="qrcodes"), name="qrcodes")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = database.get_user_by_username(form_data.username)
    if not user or not database.verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user["username"], "role": user["role"]})
    response = JSONResponse({"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60)
    return response

@app.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}

@app.get("/auth/me")
async def get_me(current_user = Depends(get_current_user_from_cookie)):
    return current_user

@app.get("/tools")
async def get_tools(user = Depends(get_current_user_from_cookie)):
    return database.get_all_tools()

@app.get("/employees")
async def get_employees(user = Depends(get_current_user_from_cookie)):
    return database.get_all_employees()

@app.get("/issued")
async def get_issued(user = Depends(get_current_user_from_cookie)):
    return database.get_issued_tools()

@app.post("/issue")
async def issue_tool(req: IssueRequest, user = Depends(get_current_user_from_cookie)):
    if user["role"] not in ["admin", "worker"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    tool = database.get_tool_by_qr(req.tool_qr)
    if not tool:
        raise HTTPException(status_code=404, detail="Инструмент не найден")
    if tool["status"] == "issued":
        raise HTTPException(status_code=400, detail="Инструмент уже выдан")
    employee = database.get_employee_by_qr(req.employee_qr)
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    database.issue_tool(tool["id"], employee["id"])
    return {"message": f"Инструмент '{tool['name']}' выдан сотруднику {employee['name']}"}

@app.post("/return")
async def return_tool(req: ReturnRequest, user = Depends(get_current_user_from_cookie)):
    if user["role"] not in ["admin", "worker"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    tool = database.get_tool_by_qr(req.tool_qr)
    if not tool:
        raise HTTPException(status_code=404, detail="Инструмент не найден")
    if tool["status"] == "in_stock":
        raise HTTPException(status_code=400, detail="Инструмент уже на складе")
    database.return_tool(tool["id"])
    return {"message": f"Инструмент '{tool['name']}' возвращён"}

# Админские эндпоинты
@app.get("/admin/tools")
async def get_all_tools_admin(user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return database.get_all_tools()

@app.post("/admin/tools")
async def create_tool(tool: ToolCreate, user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("SELECT MAX(id) FROM tools")
    max_id = c.fetchone()[0] or 0
    new_id = max_id + 1
    qr_code = f"tool_{new_id}"
    c.execute("INSERT INTO tools (name, qr_code, container) VALUES (?,?,?)",
              (tool.name, qr_code, tool.container))
    conn.commit()
    conn.close()
    img = qrcode.make(qr_code)
    img.save(f"qrcodes/{qr_code}.png")
    return {"message": "Инструмент добавлен", "qr_code": qr_code}

@app.put("/admin/tools/{tool_id}")
async def update_tool(tool_id: int, tool: ToolUpdate, user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM tools WHERE id=?", (tool_id,))
    if not c.fetchone():
        raise HTTPException(status_code=404, detail="Инструмент не найден")
    updates = []
    params = []
    if tool.name is not None:
        updates.append("name=?")
        params.append(tool.name)
    if tool.container is not None:
        updates.append("container=?")
        params.append(tool.container)
    if updates:
        params.append(tool_id)
        c.execute(f"UPDATE tools SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
    conn.close()
    return {"message": "Инструмент обновлён"}

@app.delete("/admin/tools/{tool_id}")
async def delete_tool(tool_id: int, user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("SELECT status FROM tools WHERE id=?", (tool_id,))
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Инструмент не найден")
    if row[0] == "issued":
        raise HTTPException(status_code=400, detail="Нельзя удалить выданный инструмент")
    c.execute("DELETE FROM tools WHERE id=?", (tool_id,))
    conn.commit()
    conn.close()
    return {"message": "Инструмент удалён"}

@app.get("/admin/employees")
async def get_all_employees_admin(user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return database.get_all_employees()

@app.post("/admin/employees")
async def create_employee(emp: EmployeeCreate, user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    qr_code = f"emp_{emp.tab_number}"
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO employees (name, tab_number, qr_code) VALUES (?,?,?)",
                  (emp.name, emp.tab_number, qr_code))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Сотрудник с таким табельным номером уже существует")
    finally:
        conn.close()
    img = qrcode.make(qr_code)
    img.save(f"qrcodes/{qr_code}.png")
    return {"message": "Сотрудник добавлен", "qr_code": qr_code}

@app.put("/admin/employees/{emp_id}")
async def update_employee(emp_id: int, emp: EmployeeUpdate, user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM employees WHERE id=?", (emp_id,))
    if not c.fetchone():
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    updates = []
    params = []
    if emp.name is not None:
        updates.append("name=?")
        params.append(emp.name)
    if emp.tab_number is not None:
        updates.append("tab_number=?")
        params.append(emp.tab_number)
        new_qr = f"emp_{emp.tab_number}"
        updates.append("qr_code=?")
        params.append(new_qr)
    if updates:
        params.append(emp_id)
        c.execute(f"UPDATE employees SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
        if emp.tab_number is not None:
            img = qrcode.make(new_qr)
            img.save(f"qrcodes/{new_qr}.png")
    conn.close()
    return {"message": "Сотрудник обновлён"}

@app.delete("/admin/employees/{emp_id}")
async def delete_employee(emp_id: int, user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tools WHERE issued_to=? AND status='issued'", (emp_id,))
    count = c.fetchone()[0]
    if count > 0:
        raise HTTPException(status_code=400, detail="Сотрудник имеет выданные инструменты")
    c.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    conn.commit()
    conn.close()
    return {"message": "Сотрудник удалён"}

@app.get("/admin/users")
async def get_all_users(user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, username, role FROM users")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1], "role": r[2]} for r in rows]

@app.post("/admin/users")
async def create_user_api(new_user: UserCreate, user = Depends(get_current_user_from_cookie)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    success = database.create_user(new_user.username, new_user.password, new_user.role)
    if not success:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    return {"message": "Пользователь создан"}

@app.put("/admin/users/{user_id}/role")
async def update_user_role(user_id: int, role_update: UserRoleUpdate, current_user = Depends(get_current_user_from_cookie)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET role=? WHERE id=?", (role_update.role, user_id))
    if c.rowcount == 0:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    conn.commit()
    conn.close()
    return {"message": "Роль обновлена"}

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, current_user = Depends(get_current_user_from_cookie)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = sqlite3.connect(database.DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    if c.rowcount == 0:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    conn.commit()
    conn.close()
    return {"message": "Пользователь удалён"}

@app.on_event("startup")
def generate_qr_codes():
    tools = database.get_all_tools()
    for tool in tools:
        img = qrcode.make(tool["qr_code"])
        img.save(f"qrcodes/{tool['qr_code']}.png")
    employees = database.get_all_employees()
    for emp in employees:
        img = qrcode.make(emp["qr_code"])
        img.save(f"qrcodes/{emp['qr_code']}.png")
