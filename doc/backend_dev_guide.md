# 后端开发与数据库连接指南

## 1. 技术栈要求
- **后端框架**: Python FastAPI (异步)
- **数据库驱动**: asyncpg + SQLAlchemy 2.0 (异步 ORM) 或 psycopg2 (同步)
- **前端框架**: React (Next.js) 或 Vue 3 (由开发者决定)
- **环境变量管理**: python-dotenv

## 2. 数据库连接与安全规范
**绝对禁止在代码中硬编码数据库密码或 IP！** 
必须使用 `python-dotenv` 从项目根目录的 `.env` 文件中读取连接信息。

### 连接代码示例:
```python
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT")
)