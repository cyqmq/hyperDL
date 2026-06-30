"""
构建单文件可执行文件 (PyInstaller)

用法:
    python build_scripts/build_exe.py

输出:
    dist/hyperdownloader.exe  (API 服务器)
    dist/hyperdownloader-cli.exe  (CLI 下载工具)
"""
import os
import sys
import shutil
import subprocess

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

VERSION = "1.0.4"
TOOLS_DIR = os.path.join(ROOT, "tools")
DIST_DIR = os.path.join(ROOT, "dist")
SPEC_DIR = os.path.join(ROOT, "build_scripts")


def clean():
    """清理旧的构建产物"""
    for d in ["build", "dist", "__pycache__"]:
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    for f in ["hyperdownloader.spec"]:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)


def build_api_server():
    """构建 API 服务器单文件"""
    print("=" * 60)
    print("  构建 API 服务器...")
    print("=" * 60)

    # 数据文件：web_demo.html
    data = [
        (TOOLS_DIR, "tools"),
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                      # 单文件
        "--name", f"hyperdownloader-{VERSION}",
        "--distpath", DIST_DIR,
        "--add-data", f"{os.path.join(TOOLS_DIR, 'web_demo.html')}{os.pathsep}tools",
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--collect-submodules", "hyperdownloader",
        "--collect-data", "hyperdownloader",
        "--optimize", "2",
        "--console",                      # 保留控制台窗口显示日志
        os.path.join(ROOT, "hyperdownloader", "api_server.py"),
    ]

    print(f"  运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ 构建失败:")
        print(result.stderr)
        return False

    # 找到生成的 exe
    for f in os.listdir(DIST_DIR):
        if f.endswith(".exe"):
            src = os.path.join(DIST_DIR, f)
            dst = os.path.join(DIST_DIR, "hyperdownloader-server.exe")
            os.rename(src, dst)
            print(f"  ✅ 生成: {dst}")
            print(f"     大小: {os.path.getsize(dst) >> 20} MB")
            return True
    return False


def build_cli_tool():
    """构建 CLI 下载工具单文件"""
    print("\n" + "=" * 60)
    print("  构建 CLI 下载工具...")
    print("=" * 60)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "hyperdownloader-cli",
        "--distpath", DIST_DIR,
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--collect-submodules", "hyperdownloader",
        "--optimize", "2",
        "--console",
        os.path.join(ROOT, "tools", "drag_drop_downloader.py"),
    ]

    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ 构建失败:")
        print(result.stderr)
        return False

    for f in os.listdir(DIST_DIR):
        if f.endswith(".exe") and "cli" in f:
            exe_path = os.path.join(DIST_DIR, f)
            print(f"  ✅ 生成: {exe_path}")
            print(f"     大小: {os.path.getsize(exe_path) >> 20} MB")
            return True
    return False


def main():
    print(f"  HyperDownloader Core v{VERSION} — 单文件构建")
    print(f"  Python: {sys.version}")
    print()

    clean()

    ok1 = build_api_server()
    ok2 = build_cli_tool()

    print("\n" + "=" * 60)
    if ok1 or ok2:
        print("  ✅ 构建完成!")
        if ok1:
            s1 = os.path.getsize(os.path.join(DIST_DIR, "hyperdownloader-server.exe"))
            print(f"     hyperdownloader-server.exe  ({s1 >> 20} MB)")
        if ok2:
            s2 = os.path.getsize(os.path.join(DIST_DIR, "hyperdownloader-cli.exe"))
            print(f"     hyperdownloader-cli.exe      ({s2 >> 20} MB)")
    else:
        print("  ❌ 全部构建失败")
    print("=" * 60)


if __name__ == "__main__":
    main()
