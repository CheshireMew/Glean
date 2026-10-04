"""Explicit local data-permission repair; does not delete or print credentials."""
from pathlib import Path
import os
from backend.app.core.config import PROJECT_ROOT
from backend.app.infrastructure.database import database
from backend.app.infrastructure.data_permissions import protect_database, secure_path


def main():
    protect_database(database.db_path)
    for name in ('.env', '.env.development', '.env.production'):
        path = Path(PROJECT_ROOT) / name
        if path.exists():
            secure_path(path)
    accounts = '当前账号、SYSTEM 和 Administrators' if os.name == 'nt' else '文件所有者'
    print(f'数据库、备份和环境文件权限已限制到{accounts}。')


if __name__ == '__main__':
    main()
