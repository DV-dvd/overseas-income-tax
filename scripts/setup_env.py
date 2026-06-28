#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建虚拟环境并安装 PDF/Excel 依赖。

用法:
    python setup_env.py <工作目录>

会在 <工作目录>/.venv 创建虚拟环境，安装 openpyxl 和 pypdf，
最后打印 venv python 的绝对路径（后续所有 python 调用都用它）。

Windows 下 pip 可能因 SSL 问题失败，带自动重试。
"""
import os
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        print("用法: python setup_env.py <工作目录>", file=sys.stderr)
        sys.exit(1)

    work_dir = os.path.abspath(sys.argv[1])
    venv_dir = os.path.join(work_dir, ".venv")

    # 跨平台定位 venv 下的 python
    if os.name == "nt":
        python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        python_exe = os.path.join(venv_dir, "bin", "python")

    # 创建 venv（用 isfile 判断 python 可执行文件是否存在，比判断目录更可靠）
    if not os.path.isfile(python_exe):
        print(f"[setup] 创建虚拟环境: {venv_dir}")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
        except subprocess.CalledProcessError:
            print(f"[setup] venv 创建失败。请确认系统已安装 Python，或删除 {venv_dir} 后重试", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("[setup] 找不到 python，请先安装 Python 3", file=sys.stderr)
            sys.exit(1)

    # 升级 pip（非致命）
    try:
        subprocess.check_call([python_exe, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    except subprocess.CalledProcessError:
        print("[setup] pip 升级失败，继续（非致命）")

    # 安装依赖（带重试，应对 SSL 偶发失败）。统一用 python -m pip，避免 pip 自更新后路径失效
    deps = ["openpyxl", "pypdf"]
    for attempt in range(3):
        try:
            print(f"[setup] 安装依赖（第 {attempt + 1} 次尝试）: {deps}")
            subprocess.check_call([python_exe, "-m", "pip", "install"] + deps + ["-q"])
            break
        except subprocess.CalledProcessError:
            if attempt == 2:
                print(f"[setup] 依赖安装失败，请手动运行: {python_exe} -m pip install {' '.join(deps)}", file=sys.stderr)
                sys.exit(1)

    # 输出 venv python 绝对路径（关键：后续脚本调用都用它）
    print(python_exe)


if __name__ == "__main__":
    main()
