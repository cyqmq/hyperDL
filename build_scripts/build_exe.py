"""
构建单文件可执行文件 (PyInstaller)

命名规则: {软件名}-{操作系统}-{架构}
  Windows: hyperdownloader-server-win-x64.exe
  Linux:   hyperdownloader-server-linux-x64

用法:
    python build_scripts/build_exe.py
"""
import os
import sys
import shutil
import subprocess
import platform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

VERSION = "1.0.7"
TOOLS_DIR = os.path.join(ROOT, "tools")
DIST_DIR = os.path.join(ROOT, "dist")

# ── 平台检测 ──
_os = platform.system().lower()        # windows / linux
_arch = platform.machine().lower()      # AMD64 / x86_64
_arch_short = "x64" if "64" in _arch else "x86"
_suffix = ".exe" if _os == "windows" else ""
_os_name = {"windows": "win", "linux": "linux"}.get(_os, _os)


def _name(base: str) -> str:
    """生成规范文件名: {name}-{os}-{arch}[.exe]"""
    return f"{base}-{_os_name}-{_arch_short}{_suffix}"


def clean():
    for d in ["build", "dist", "__pycache__"]:
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    for f in ["hyperdownloader.spec"]:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)


def build_api_server():
    """构建 API 服务器"""
    out_name = _name(f"hyperdownloader-server-{VERSION}")
    pyi_name = out_name.replace(_suffix, "")  # PyInstaller 会自动加后缀
    print(f"  构建 API 服务器 -> {out_name}")
    print("=" * 60)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", pyi_name,
        "--distpath", DIST_DIR,
        "--add-data", f"{os.path.join(TOOLS_DIR, 'web_demo.html')}{os.pathsep}tools",
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--collect-submodules", "hyperdownloader",
        "--collect-data", "hyperdownloader",
        "--optimize", "2",
        "--console",
        os.path.join(ROOT, "hyperdownloader", "api_server.py"),
    ]
    if _os == "linux":
        cmd += ["--exclude-module", "tkinter", "--exclude-module", "PIL"]

    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ 构建失败:", result.stderr[:500])
        return False

    # PyInstaller 生成的临时文件名
    tmp_name = pyi_name + _suffix
    tmp_path = os.path.join(DIST_DIR, tmp_name)
    dst_path = os.path.join(DIST_DIR, out_name)
    if os.path.exists(tmp_path):
        if os.path.exists(dst_path):
            os.remove(dst_path)
        os.rename(tmp_path, dst_path)
        print(f"  ✅ 生成: {dst_path}")
        print(f"     大小: {os.path.getsize(dst_path) >> 20} MB")
        return True

    # 也可能直接生成了目标名
    if os.path.exists(dst_path):
        print(f"  ✅ 生成: {dst_path}")
        print(f"     大小: {os.path.getsize(dst_path) >> 20} MB")
        return True

    print("  ❌ 未找到构建产物")
    return False


def _pyinstaller_build(entry_point: str, out_name: str, exclude: list[str] = None) -> bool:
    """通用 PyInstaller 构建（直接输出正确文件名）"""
    pyi_name = out_name.replace(_suffix, "")  # PyInstaller 会自动加后缀
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", pyi_name,
        "--distpath", DIST_DIR,
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--collect-submodules", "hyperdownloader",
        "--optimize", "2",
        "--console",
        entry_point,
    ]
    for mod in (exclude or []):
        cmd += ["--exclude-module", mod]

    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ 构建失败:", result.stderr[:500])
        return False

    # PyInstaller 输出文件名 = pyi_name + _suffix，正好等于 out_name
    dst = os.path.join(DIST_DIR, out_name)
    if os.path.exists(dst):
        print(f"  ✅ 生成: {dst}")
        print(f"     大小: {os.path.getsize(dst) >> 20} MB")
        return True
    print(f"  ❌ 未找到: {dst}")
    return False


def build_api_server():
    """构建 API 服务器"""
    out = _name(f"hyperdownloader-server-{VERSION}")
    print(f"  构建 API 服务器 -> {out}")
    print("=" * 60)
    pyi_name = out.replace(_suffix, "")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", pyi_name, "--distpath", DIST_DIR,
        "--hidden-import", "requests", "--hidden-import", "urllib3",
        "--collect-submodules", "hyperdownloader",
        "--add-data", f"{os.path.join(TOOLS_DIR, 'web_demo.html')}{os.pathsep}tools",
        "--collect-data", "hyperdownloader",
        "--optimize", "2", "--console",
        os.path.join(ROOT, "hyperdownloader", "api_server.py"),
    ]
    if _os == "linux":
        cmd += ["--exclude-module", "tkinter", "--exclude-module", "PIL"]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ❌ 构建失败:", result.stderr[:500]); return False
    dst = os.path.join(DIST_DIR, out)
    ok = os.path.exists(dst)
    print(f"  {'✅' if ok else '❌'} {dst}  ({os.path.getsize(dst)>>20 if ok else 0} MB)")
    return ok


def build_cli_tool():
    out = _name(f"hyperdownloader-cli-{VERSION}")
    print(f"  构建 CLI 下载工具 -> {out}")
    print("=" * 60)
    return _pyinstaller_build(
        os.path.join(ROOT, "hyperdownloader", "cli.py"), out,
        exclude=["tkinter", "tkinterdnd2", "PIL", "PIL.Image"],
    )


def build_gui_tool():
    if _os != "windows":
        print("  跳过 GUI: Linux 无需 GUI 版本")
        return True
    out = _name(f"hyperdownloader-gui-{VERSION}")
    print(f"  构建 GUI 拖拽下载 -> {out}")
    print("=" * 60)
    return _pyinstaller_build(
        os.path.join(ROOT, "tools", "drag_drop_downloader.py"), out,
    )


def main():
    print(f"  HyperDownloader Core v{VERSION}")
    print(f"  平台: {_os}-{_arch_short}")
    print(f"  Python: {sys.version}")
    print()

    clean()
    build_api_server()
    build_cli_tool()
    build_gui_tool()

    print("\n" + "=" * 60)
    print("  ✅ 构建完成!")
    for f in sorted(os.listdir(DIST_DIR)):
        fp = os.path.join(DIST_DIR, f)
        if os.path.isfile(fp) and not f.endswith((".tar.gz", ".whl")):
            print(f"     {f}  ({os.path.getsize(fp) >> 20} MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
