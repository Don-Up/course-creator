"""
notify.py — 提醒开发者「我这边好了,可以回来看结果」(系统弹窗 + 一声 1 秒提示音)

Usage:
    python notify.py done                      # 任务完成
    python notify.py attention                 # 需要确认
    python notify.py help                      # 求助
    python notify.py info "自定义提示"          # 普通信息
    python notify.py error "构建失败" --title "构建"

提示音规则(已简化):
    不管是哪一种提醒,都只播一声 beep,时长 1 秒,没有区分音调。
    需要区分「做完了」和「要你看一眼」时,靠弹窗文案区分,不靠声音。

Options:
    --title TEXT   覆盖弹窗标题
    --wait         阻塞等待用户关闭弹窗(默认后台弹出,不阻塞调用方)
    --no-sound     不播提示音(仅供本脚本派生出的后台弹窗进程使用)

标题前缀:
    弹窗标题一律带 "[lowcode] " 前缀(标识来源项目),自定义 --title 同样适用;
    标题已自带前缀时不会重复加。

Exit code: 0 = 提醒已发出, 2 = 参数错(与 argparse 一致), 3 = 弹窗完全无法发出(已降级为终端输出)

跨平台:
- Windows: ctypes 调用 user32.MessageBoxW 弹窗;winsound.Beep 播 1 秒提示音
- macOS:   osascript 调 System Events 的 display dialog;afplay 播系统音补足 1 秒
- Linux:   zenity(优先) / notify-send(降级);paplay / aplay 播系统音
- 全部失败: 终端输出兜底

Claude Code 调用时机:
- 完成一个独立任务后 → python notify.py done
- 准备 AskUserQuestion / 询问用户确认前 → python notify.py attention
- 长流程被阻塞需要用户介入时 → python notify.py help
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

# 所有弹窗标题统一带上的来源前缀,方便用户一眼认出是哪个项目弹出来的
PREFIX = "[lowcode]"

# 提示音参数:只有一种声音 —— 一声、1 秒、1000Hz
BEEP_FREQ_HZ = 1000
BEEP_DURATION_MS = 1000

# 各类提醒的默认标题与正文
PRESETS: dict[str, tuple[str, str]] = {
    "done": ("任务完成", "✅ 事情做完了,可以回来看结果了。"),
    "attention": ("需要确认", "❗ 请回来看一眼,这里需要你做一个选择。"),
    "help": ("需要帮助", "🆘 卡住了,需要你介入处理一下。"),
    "info": ("提示", "ℹ️ 有一条提示信息。"),
    "error": ("出错了", "❌ 执行过程中出现错误。"),
}


def with_prefix(title: str) -> str:
    """给弹窗标题加上来源前缀,已带前缀的标题原样返回(幂等)。

    :param title: 原始标题,可能来自 --title 参数或 PRESETS 默认值。
    :return: 加上 "[lowcode] " 前缀后的标题。
    """
    if title.startswith(PREFIX):
        return title
    return f"{PREFIX} {title}"


def _default_text(command: str) -> str:
    """返回某个提醒命令的默认正文。

    :param command: 提醒命令名(done / attention / help / info / error)。
    :return: 对应的默认正文文案,未知命令返回空字符串。
    """
    preset = PRESETS.get(command)
    return preset[1] if preset else ""


def _default_title(command: str) -> str:
    """返回某个提醒命令的默认标题。

    :param command: 提醒命令名。
    :return: 对应的默认标题文案,未知命令返回"提示"。
    """
    preset = PRESETS.get(command)
    return preset[0] if preset else "提示"


def _escape_applescript(text: str) -> str:
    """把普通文本转义成可以安全嵌入 AppleScript 字符串字面量的形式。

    :param text: 原始文本,可能包含引号与反斜杠。
    :return: 转义后的文本,可直接放进双引号里。
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def beep_windows(freq_hz: int, duration_ms: int) -> bool:
    """Windows:winsound.Beep 走 PC 扬声器,频率 + 时长可控,能真正连续响满 1 秒。

    :param freq_hz: 音调频率(Hz)。
    :param duration_ms: 持续时长(毫秒)。
    :return: 是否成功播放。
    """
    try:
        import winsound  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        winsound.Beep(freq_hz, duration_ms)
        return True
    except RuntimeError:
        # 部分虚拟环境 / Windows Server core 没有扬声器
        return False


def beep_mac(duration_ms: int) -> bool:
    """macOS:afplay 播一声系统音,剩下的时长用 sleep 补足,凑满 1 秒。

    :param duration_ms: 目标总时长(毫秒),本函数按它算要补睡多久。
    :return: 是否真的播出了声音。
    """
    sound_path = "/System/Library/Sounds/Pop.aiff"
    started = time.monotonic()
    try:
        subprocess.run(
            ["afplay", sound_path],
            check=False,
            timeout=2,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    elapsed = time.monotonic() - started
    if elapsed < duration_ms / 1000:
        time.sleep(duration_ms / 1000 - elapsed)
    return True


def beep_linux(duration_ms: int) -> bool:
    """Linux:优先用 paplay / aplay 播一声系统音,凑不满的时长用 sleep 补。

    :param duration_ms: 目标总时长(毫秒)。
    :return: 是否真的播出了声音。
    """
    started = time.monotonic()
    for player in (
        ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
        ["aplay", "/usr/share/sounds/alsa/Front_Center.wav"],
    ):
        try:
            subprocess.run(
                player,
                check=False,
                timeout=2,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    else:
        return False
    elapsed = time.monotonic() - started
    if elapsed < duration_ms / 1000:
        time.sleep(duration_ms / 1000 - elapsed)
    return True


def beep_once() -> None:
    """播一声 1 秒的提示音,失败兜底:终端 BEL 字符。

    只有这一种声音,不再按提醒类型区分音调。放在主进程里同步播完再弹窗,
    这样调用方拿到退出码时,提示音已经响过了。
    """
    played = False
    if IS_WINDOWS:
        played = beep_windows(BEEP_FREQ_HZ, BEEP_DURATION_MS)
    elif IS_MAC:
        played = beep_mac(BEEP_DURATION_MS)
    else:
        played = beep_linux(BEEP_DURATION_MS)
    if not played:
        # 兜底:终端 BEL 字符(很多终端会响,有些会忽略)
        sys.stdout.write("\a")
        sys.stdout.flush()


def show_windows(title: str, text: str, icon: str) -> bool:
    """在 Windows 上通过 user32.MessageBoxW 弹出系统级模态对话框。

    :param title: 弹窗标题栏文字。
    :param text: 弹窗正文文字。
    :param icon: 图标类型(information / question / error),决定弹窗的图标样式。
    :return: 弹窗是否成功发出。
    """
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MessageBoxW.argtypes = [
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.UINT,
    ]
    user32.MessageBoxW.restype = ctypes.c_int

    MB_OK = 0x00000000
    MB_ICONQUESTION = 0x00000020
    MB_ICONERROR = 0x00000010
    MB_ICONINFORMATION = 0x00000040
    MB_TOPMOST = 0x00040000
    MB_SETFOREGROUND = 0x00010000

    icon_flag = {
        "information": MB_ICONINFORMATION,
        "question": MB_ICONQUESTION,
        "error": MB_ICONERROR,
    }.get(icon, MB_ICONINFORMATION)

    flags = MB_OK | icon_flag | MB_TOPMOST | MB_SETFOREGROUND
    body = f"{text}\n\n(由 notify.py 弹出的系统级提示,点击确定关闭)"

    try:
        user32.MessageBoxW(None, body, title, flags)
    except Exception:
        return False
    return True


def show_mac(title: str, text: str, icon: str) -> bool:
    """在 macOS 上通过 osascript 弹出系统级对话框。

    :param title: 弹窗标题文字。
    :param text: 弹窗正文文字。
    :param icon: 图标类型,目前统一映射为"停止"图标(系统限制)。
    :return: 弹窗是否成功发出。
    """
    script = (
        f'display dialog "{_escape_applescript(text)}" '
        f'with title "{_escape_applescript(title)}" '
        f'buttons {{"好"}} default button "好" with icon stop'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            timeout=300,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def show_linux(title: str, text: str, icon: str) -> bool:
    """在 Linux 上优先用 zenity 弹窗,失败降级为 notify-send 通知。

    :param title: 弹窗标题文字。
    :param text: 弹窗正文文字。
    :param icon: 图标类型(information / question / error),映射到 zenity 的模式。
    :return: 弹窗是否成功发出。
    """
    zenity_mode = {
        "information": "--info",
        "question": "--question",
        "error": "--error",
    }.get(icon, "--info")

    try:
        result = subprocess.run(
            ["zenity", zenity_mode, "--title", title, "--text", text],
            check=False,
            timeout=300,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode in (0, 1, 5):
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 降级:notify-send 发系统通知(不是模态弹窗,但至少有可见提示)
    try:
        subprocess.run(
            ["notify-send", title, text],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def show_dialog(title: str, text: str, icon: str) -> bool:
    """按当前操作系统选择合适的系统级弹窗实现。

    :param title: 弹窗标题文字。
    :param text: 弹窗正文文字。
    :param icon: 图标类型(information / question / error)。
    :return: 弹窗是否成功发出。
    """
    if IS_WINDOWS:
        return show_windows(title, text, icon)
    if IS_MAC:
        return show_mac(title, text, icon)
    return show_linux(title, text, icon)


def spawn_detached(child_args: list[str]) -> bool:
    """派生一个脱离父进程的子进程来持有弹窗,使父进程可以立即返回。

    子进程固定带 --no-sound:提示音已经在父进程里响过了,不重复播。

    :param child_args: 子进程的命令行参数列表(不含解释器路径)。
    :return: 子进程是否成功派生。
    """
    popen_kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if IS_WINDOWS:
        # DETACHED_PROCESS 让子进程不随父进程退出而终止
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), *child_args, "--no-sound"],
            **popen_kwargs,
        )
        return True
    except (FileNotFoundError, OSError):
        return False


def fallback_print(title: str, text: str) -> None:
    """在所有系统弹窗方案都不可用时,把提醒内容打印到终端作为兜底。

    提示音此时已经播过(或已用 BEL 字符兜底),这里不再追加 BEL,免得响两次。

    :param title: 弹窗标题文字(已带 [lowcode] 前缀)。
    :param text: 弹窗正文文字。
    :return: 无返回值。
    """
    sys.stdout.write(f"\n{title}\n{text}\n")
    sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。

    :return: 配置好参数规则的 ArgumentParser 实例。
    """
    parser = argparse.ArgumentParser(
        prog="notify.py",
        description="提醒开发者(系统弹窗 + 一声 1 秒提示音)",
    )
    parser.add_argument(
        "command",
        choices=sorted(PRESETS.keys()),
        help="提醒类型(只影响弹窗文案,提示音一律是同一声 beep)",
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=None,
        help="弹窗正文,省略时使用该类型的默认文案",
    )
    parser.add_argument("--title", default=None, help="弹窗标题,省略时使用默认标题")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="阻塞等待用户关闭弹窗(默认后台弹出,不阻塞调用方)",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="不播提示音(内部用:后台弹窗进程不重复播)",
    )
    return parser


def main() -> int:
    """解析命令行参数,先播一声 1 秒提示音,再发出系统级提醒。

    :return: 0 表示提醒已发出,2 表示参数写错(由 argparse 抛出),3 表示弹窗完全无法发出。
    """
    parser = build_parser()
    args = parser.parse_args()

    title = with_prefix(args.title or _default_title(args.command))
    text = args.text if args.text is not None else _default_text(args.command)

    icon = {
        "done": "information",
        "info": "information",
        "attention": "question",
        "help": "error",
        "error": "error",
    }.get(args.command, "information")

    # 提示音在主进程同步播完再走弹窗,调用方拿到退出码时声音已经响过了
    if not args.no_sound:
        beep_once()

    if not args.wait:
        # 非阻塞:派生子进程去弹窗,本进程立即返回
        child_args = [args.command, "--wait"]
        if args.text is not None:
            child_args.append(args.text)
        if args.title is not None:
            child_args += ["--title", args.title]
        if spawn_detached(child_args):
            return 0
        # 派生失败:退回阻塞模式,至少让提醒可见
        if show_dialog(title, text, icon):
            return 0
        fallback_print(title, text)
        return 3

    if show_dialog(title, text, icon):
        return 0
    fallback_print(title, text)
    return 3


if __name__ == "__main__":
    sys.exit(main())