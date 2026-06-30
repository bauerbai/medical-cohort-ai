project_root/
├── .env # 数据库密码等敏感信息（必须加入 .gitignore）
├── docs/
│   ├── schema.md             # 1. 数据库语义层字典（告诉 Codex 表结构和业务逻辑）
│   └── backend_dev_guide.md  # 2. 后端开发与安全规范（告诉 Codex 技术栈和连接方式）
├── backend/                  # 后端代码存放目录
└── frontend/                 # 前端代码存放目录