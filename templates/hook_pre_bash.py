"""PreToolUse hook — 在指令送出「之前」攔截。

放在 tools/hooks/pre_bash.py，掛在 .claude/settings.json 的 PreToolUse（matcher: Bash|PowerShell）。

═══════════════════════════════════════════════════════════════════════════
設計原則（每一條都是踩出來的，不要為了精簡拿掉）
═══════════════════════════════════════════════════════════════════════════

1. **hook 不可以因為自己爆掉而擋住工作。**
   所有例外一律吞掉並放行 —— 一個會崩潰的 hook 比沒有 hook 更糟，
   因為它會讓人把整個 hook 層關掉。

2. **訊息要帶著它的來歷。**
   「這樣不行」沒有用。要寫「它擋的是哪一次事故」＋「正確寫法是什麼」，
   這樣下一個看到它的人（包括兩週後的你）不需要問「為什麼有這條規則」。

3. **每一條規則都要有反向案例。**
   一支「全部擋掉」的 hook 在只有正向測試的演練裡會拿滿分。

4. **不要依賴外部程式**（jq、grep、sed…）。
   Windows Git Bash 沒有 jq，而「hook 靠一個不一定存在的程式」正是安靜失效的形狀。

5. **Windows 主控台預設不是 UTF-8**，印中文會 UnicodeEncodeError ⇒ hook 崩潰 ⇒ 規則安靜失效。
   所以下面有兩道編碼保險，兩道都不要拿掉。
"""
import json
import re
import sys

# ── 編碼保險 ①：把 stdout 轉成 UTF-8 ────────────────────────────────────
# Windows 主控台預設 cp950/cp1252，印不出箭號與 emoji。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════════════
# 基礎設施
# ═══════════════════════════════════════════════════════════════════════

def read_payload():
    """讀 stdin 的 hook JSON。壞掉就回空 dict —— 見設計原則 1。"""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def emit(obj):
    """輸出 hook 決策。

    ensure_ascii=True 是**編碼保險 ②**：就算上面的 reconfigure 失敗
    （舊 Python、被包起來的 stdout），逃脫過的 JSON 仍是純 ASCII，
    任何 codec 都印得出去，harness 解析 JSON 時會還原成中文。
    """
    try:
        print(json.dumps(obj, ensure_ascii=True))
    except Exception:
        pass  # 印不出去也不可以讓 hook 崩潰而擋住工作


def deny(reason):
    emit({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }})


def ask(reason):
    emit({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }})


def strip_heredocs(cmd):
    """把 heredoc 的**內容**剝掉再比對。

    理由：`cat <<'EOF' ... EOF` 裡面的文字是資料不是指令。
    不剝的話，一份「正在解釋這條規則的文件」會被自己的規則擋下來
    —— 這是誤報，而誤報會讓人把 hook 關掉。
    """
    out, skip_until = [], None
    for line in cmd.splitlines():
        if skip_until is not None:
            if line.strip() == skip_until:
                skip_until = None
            continue
        m = re.search(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)'?\"?", line)
        out.append(line)
        if m:
            skip_until = m.group(1)
    return "\n".join(out)


# ═══════════════════════════════════════════════════════════════════════
# 規則（把這些換成「你這週已經犯過的錯」）
# ═══════════════════════════════════════════════════════════════════════

def rule_pipe_to_head_tail(cmd):
    """守衛指令接了 | head/tail ⇒ exit code 變成 head/tail 的。

    ✅ 該擋：  python tools/spec_check.py | tail -30
    ❌ 不該擋：python tools/spec_check.py > out.txt 2>&1; echo $?; cut -c1-200 out.txt | tail -30
               （exit code 已經單獨讀過了，後面那段只是在讀檔）
    ❌ 不該擋：ls | head -5      （ls 不是守衛）
    """
    GUARDS = r"(spec_check|ext_check|role_check|pg_check|xss_fuzz|drill)"
    # 關鍵：守衛與 | 之間**不能跨過** ; && || 或換行 —— 跨過了就是兩段獨立的指令。
    pattern = rf"{GUARDS}[^;&|\n]*\|\s*(head|tail)\b"
    if re.search(pattern, cmd):
        return (
            "守衛指令接了 | head/tail —— 你看到的 exit code 會是 head/tail 的，不是守衛的。\n"
            "曾真的因此帶著紅燈提交過。\n"
            "改法：`cmd > out.txt 2>&1; code=$?` 再讀檔，或 `set -o pipefail`。"
        )
    return None


def rule_migration_without_target(cmd):
    """migration 指令沒指定資料庫目標 ⇒ 可能靜默升級到另一個庫。

    ✅ 該擋：  alembic upgrade head
    ❌ 不該擋：CASA_TARGET=dev alembic upgrade head
    ❌ 不該擋：python scripts/migrate.py dev upgrade head   （包裝會先印目標）
    """
    if re.search(r"\balembic\b", cmd) and not re.search(r"(TARGET|scripts/migrate\.py)", cmd):
        return (
            "alembic 沒帶資料庫目標。設定檔有多個具名目標，指定錯就**靜默**升級到另一個庫。\n"
            "改法：走包裝 `python scripts/migrate.py <local|dev|prod> upgrade head`，"
            "它會先印出目標，對正式庫還會要求打字確認。"
        )
    return None


def rule_commit_secret_scan(cmd):
    """提交前掃機密。這一條建議每個專案都裝。

    ⚠️ 判準：偵測「值」，不要偵測「描述值的樣式」。
       粗略的正則會擋掉偵測器自己的程式碼、也會擋掉正在講這條規則的文件
       —— 同一個結構問題曾造成六次誤報，**全部是誤報不是漏報**。
    """
    if not re.search(r"\bgit\s+commit\b", cmd):
        return None
    # 這裡只做入口攔截，真正的掃描交給獨立腳本（它也掛在 git 原生 pre-commit）
    return None  # 換成：呼叫 tools/precommit_scan.py，非 0 就 deny


# 掛上來的規則。加新規則＝在這裡加一行 ＋ 在 drill.py 加正向與反向各一個方向。
RULES = [
    (rule_pipe_to_head_tail, deny),
    (rule_migration_without_target, deny),
    (rule_commit_secret_scan, deny),
]


def check(cmd):
    """給 drill.py 靜態呼叫用：回傳 (規則名, 訊息, 動作) 或 None。"""
    cleaned = strip_heredocs(cmd)
    for fn, action in RULES:
        reason = fn(cleaned)
        if reason:
            return (fn.__name__, reason, action)
    return None


def main():
    data = read_payload()
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return
    hit = check(cmd)
    if hit:
        name, reason, action = hit
        action(f"[hook: {name}]\n{reason}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 見設計原則 1 —— 永遠不要讓 hook 自己擋住工作
