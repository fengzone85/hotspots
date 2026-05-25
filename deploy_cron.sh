#!/bin/bash
# ============================================
# 三站热点日报 - VPS Cron 部署脚本
# ============================================
# 使用方法:
#   chmod +x deploy_cron.sh
#   ./deploy_cron.sh install   # 安装定时任务
#   ./deploy_cron.sh remove    # 移除定时任务
#   ./deploy_cron.sh status    # 查看定时任务状态
#   ./deploy_cron.sh run       # 手动执行一次
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/fetch_hotspots.py"
CRON_MARKER="# HOTSPOTS-DAILY-REPORT"

# 定时执行时间: 每天早上9点 (可自行修改)
CRON_SCHEDULE="0 9 * * *"

# 日志文件
LOG_FILE="$SCRIPT_DIR/hotspots.log"

# ========== 函数 ==========

check_python() {
    if command -v python3 &>/dev/null; then
        echo "✅ 找到 Python3: $(python3 --version)"
        return 0
    elif command -v python &>/dev/null; then
        echo "✅ 找到 Python: $(python --version)"
        return 0
    else
        echo "❌ 未找到 Python，请先安装 Python 3.8+"
        return 1
    fi
}

install_deps() {
    echo "📦 安装 Python 依赖..."
    if command -v python3 &>/dev/null; then
        python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" -q
    else
        python -m pip install -r "$SCRIPT_DIR/requirements.txt" -q
    fi
    echo "✅ 依赖安装完成"
}

install_cron() {
    # 检查是否已安装
    if crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
        echo "⚠️ 定时任务已存在，如需更新请先运行: $0 remove"
        return 0
    fi

    # 确定 Python 路径
    PYTHON_PATH=$(command -v python3 || command -v python)

    # 创建 cron 任务
    CRON_CMD="cd $SCRIPT_DIR && $PYTHON_PATH $PYTHON_SCRIPT >> $LOG_FILE 2>&1"
    CRON_LINE="$CRON_SCHEDULE $CRON_CMD $CRON_MARKER"

    # 添加到 crontab
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

    echo "✅ 定时任务已安装！"
    echo "   执行时间: 每天 09:00"
    echo "   日志文件: $LOG_FILE"
    echo "   报告目录: $SCRIPT_DIR/reports/"
    echo ""
    echo "   当前 crontab 内容:"
    crontab -l | grep "$CRON_MARKER"
}

remove_cron() {
    if ! crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
        echo "⚠️ 未找到定时任务"
        return 0
    fi

    crontab -l 2>/dev/null | grep -v "$CRON_MARKER" | crontab -
    echo "✅ 定时任务已移除"
}

show_status() {
    echo "📋 定时任务状态:"
    if crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
        crontab -l | grep "$CRON_MARKER"
        echo ""
        echo "📄 最新日志 (最后10行):"
        if [ -f "$LOG_FILE" ]; then
            tail -10 "$LOG_FILE"
        else
            echo "   暂无日志"
        fi
        echo ""
        echo "📂 已生成的报告:"
        ls -la "$SCRIPT_DIR/reports/" 2>/dev/null || echo "   暂无报告"
    else
        echo "   未安装定时任务"
    fi
}

run_once() {
    echo "🚀 手动执行热点抓取..."
    if command -v python3 &>/dev/null; then
        python3 "$PYTHON_SCRIPT"
    else
        python "$PYTHON_SCRIPT"
    fi
}

# ========== 主逻辑 ==========

case "${1:-}" in
    install)
        check_python || exit 1
        install_deps
        install_cron
        ;;
    remove)
        remove_cron
        ;;
    status)
        show_status
        ;;
    run)
        run_once
        ;;
    *)
        echo "三站热点日报 - VPS 部署工具"
        echo ""
        echo "用法: $0 {install|remove|status|run}"
        echo ""
        echo "  install  - 安装定时任务 (每天9:00执行)"
        echo "  remove   - 移除定时任务"
        echo "  status   - 查看任务状态和日志"
        echo "  run      - 手动执行一次"
        ;;
esac
