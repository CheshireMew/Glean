"""Protect application data using native Windows ACLs or owner-only POSIX modes."""
import os
from pathlib import Path
import stat
import subprocess


def _no_links(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.exists() and getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400:
            raise RuntimeError('数据权限设置拒绝目录链接：' + str(parent))
        if parent.is_symlink():
            raise RuntimeError('数据权限设置拒绝符号链接：' + str(parent))
    return path


def secure_path(path, recursive=False):
    path = _no_links(path)
    if not path.exists():
        raise RuntimeError('需要保护的路径不存在：' + str(path))
    children = []
    if recursive:
        for folder, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                children.append(_no_links(Path(folder) / name))
    if os.name == 'nt':
        output = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True)
        import csv
        sid = next(csv.reader([output.strip()]))[1]
        grants = [f'*{sid}', '*S-1-5-18', '*S-1-5-32-544']
        for target in [path, *children]:
            rights = '(OI)(CI)F' if target.is_dir() else 'F'
            args = ['icacls', str(target), '/inheritance:r', '/grant:r']
            args += [f'{account}:{rights}' for account in grants]
            args += ['/remove:g', '*S-1-1-0', '*S-1-5-11', '*S-1-5-32-545']
            result = subprocess.run(args, capture_output=True)
            if result.returncode:
                raise RuntimeError('无法设置数据权限：' + str(target))
    else:
        for target in [path, *children]:
            os.chmod(target, stat.S_IRWXU if target.is_dir() else stat.S_IRUSR | stat.S_IWUSR)


def protect_database(db_path):
    path = Path(db_path).absolute()
    # Never restrict the whole checkout for a legacy root-level database.
    if path.parent.name == 'data':
        secure_path(path.parent, recursive=True)
    else:
        if path.exists():
            secure_path(path)
        backups = path.parent / 'backups'
        if backups.exists():
            secure_path(backups, recursive=True)
