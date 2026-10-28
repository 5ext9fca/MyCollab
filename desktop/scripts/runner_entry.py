"""桌面分发入口；与命令行复用同一 Runner。"""
from local_runner.__main__ import main
if __name__ == '__main__':
    raise SystemExit(main())
