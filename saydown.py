"""打包成 exe 時的入口：同一支 Saydown.exe 依參數扮演守護程式、主程式、歷史紀錄或設定視窗。"""

import os
import sys


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "--guard"
    if role != "--main" and sys.stdout is None:  # 沒有主控台
        sys.stdout = sys.stderr = open(os.devnull, "w")
    if role == "--main":
        import voice_input
        voice_input.main()
    elif role == "--history":
        import history
        history.run_window()
    elif role == "--settings":
        import settings
        settings.run_window()
    else:
        import saydown_guard
        saydown_guard.main()


if __name__ == "__main__":
    main()
