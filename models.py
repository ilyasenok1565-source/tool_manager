from pydantic import BaseModel
from typing import Optional

class ToolCreate(BaseModel):
    name: str
    container: Optional[str] = None

class ToolUpdate(BaseModel):
    name: Optional[str] = None
    container: Optional[str] = None

class EmployeeCreate(BaseModel):
    name: str
    tab_number: str

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    tab_number: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "worker"

class UserRoleUpdate(BaseModel):
    role: str

class IssueRequest(BaseModel):
    tool_qr: str
    employee_qr: str

class ReturnRequest(BaseModel):
    tool_qr: str
