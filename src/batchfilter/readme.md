# ImageFilter
```
src/
├── core/                           # 核心功能
│   ├── archive/                    # 压缩包处理模块
│   │   ├── __init__.py
│   │   ├── archive_handler.py      # 基础压缩包操作
│   │   ├── archive_merger.py       # 压缩包合并功能
│   │   └── archive_processor.py    # 压缩包处理流程
│   ├── io/                         # 输入输出处理
│   │   ├── __init__.py
│   │   ├── backup_handler.py       # 备份处理
│   │   └── input_handler.py        # 统一输入处理
│   ├── filter/                     # 过滤核心功能
│   │   ├── __init__.py
│   │   ├── filter_base.py          # 过滤器基类
│   │   ├── small_filter.py         # 小图过滤
│   │   ├── grayscale_filter.py     # 灰度图过滤
│   │   ├── duplicate_filter.py     # 重复图片过滤
│   │   ├── text_filter.py          # 文本图片过滤
│   │   ├── watermark_filter.py     # 水印过滤
│   │   └── composite_filter.py     # 组合多个过滤器
│   └── hash/                       # 哈希功能
│       ├── __init__.py
│       └── hash_utils.py           # 哈希计算与比较
├── utils/                          # 通用工具
│   ├── __init__.py
│   ├── config_utils.py             # 配置工具
│   ├── logger_utils.py             # 日志工具
│   └── tui_utils.py                # TUI界面工具
└── apps/                           # 应用程序
    ├── __init__.py
    ├── filter_app.py               # 统一过滤应用入口
    ├── filter_modes/               # 各种过滤模式实现
    │   ├── __init__.py
    │   ├── batch_filter.py         # 批量过滤模式
    │   ├── artbook_dedup.py        # 画册去重模式
    │   └── text_filter.py          # 文本过滤模式
    └── config/                     # 配置预设
        ├── __init__.py
        └── presets.py              # 预设配置
```