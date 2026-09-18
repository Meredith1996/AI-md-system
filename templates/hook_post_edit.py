"""PostToolUse hook — 檔案寫入「之後」檢查。

放在 tools/hooks/post_edit.py，掛在 PostToolUse（matcher: Edit|Write）。

═══════════════════════════════════════════════════════════════════════════
block 與 note 的分界（這是設計這一層時最重要的一個判斷）
═══════════════════════════════════════════════════════════════════════════

  block  這次編輯的結果本身就是錯的，而且**現在就能確定**
         例：語法錯誤、憑證寫進了不該去的目錄

  note   需要做但**現在還不能確定有沒有做**
         例：「改了一邊記得改另一邊」——
             兩步編輯的中間狀態必然不對齊，這時候擋下來就是誤報

🚨 **誤報比漏報危險。** 一條會誤報的 block 規則，會讓人把整個 hook 層關掉。
   判斷不出來的時候，先做成 note，觀察兩週再決定要不要升級成 block。
"""
import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_payload():
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def emit(obj):
    try:
        print(json.dumps(obj, ensure_ascii=True))
    except Exception:
        pass


def block(reason):
    """擋下這次編輯，要求修正。"""
    emit({"decision": "block", "reason": reason})


def note(text):
    """不擋，只把訊息放到 AI 眼前。"""
    emit({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": text,
    }})


def edited_path(data):
    ti = data.get("tool_input") or {}
    tr = data.get("tool_response") or {}
    return tr.get("filePath") or ti.get("file_path") or ""


# ═══════════════════════════════════════════════════════════════════════
# block 類規則
# ═══════════════════════════════════════════════════════════════════════

def rule_syntax_check(path):
    """前端語法檢查。

    它擋的事故：兩個並行的對話各自宣告了一次同名的 const，
    症狀是「翻譯功能壞了」—— 實際上是 SyntaxError 讓整支 script 不執行，
    翻譯函式**從來沒有被呼叫過**。
    ⇒ 這種錯誤靠讀 code 找要花半小時，靠 hook 在存檔當下擋只要 3 秒。
    """
    if not re.search(r"\.(js|html)$", path):
        return None
    result = subprocess.run(
        [sys.executable, os.path.join(REPO, "tools", "js_syntax_check.py")],
        capture_output=True, text=True, cwd=REPO,
    )
    if result.returncode != 0:
        return f"前端語法檢查失敗：\n{result.stdout}\n{result.stderr}"
    return None


def rule_secret_in_wrong_dir(path):
    """像真憑證、但不在「永不外流」目錄底下 ⇒ 擋。

    ⚠️ 判準：**偵測「值」，不要偵測「描述值的樣式」。**
       要求完整的結構（例如 JWT 要三段含簽章），並排除公開的範例值。
       粗略的正則會擋掉偵測器自己的程式碼，也會擋掉正在講這條規則的文件
       —— 同一個結構問題曾造成六次誤報，全部是誤報不是漏報。
    """
    SAFE_DIRS = ("private/", "tmp/")
    if any(seg in path.replace("\\", "/") for seg in SAFE_DIRS):
        return None
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read(200_000)
    except Exception:
        return None

    # 完整三段 JWT（含簽章），排除文件裡常見的佔位符
    jwt = re.search(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", text)
    if jwt and "EXAMPLE" not in text[:2000].upper():
        return (
            f"這個檔含有看起來是真憑證的值，但它不在 private/ 或 tmp/ 底下。\n"
            f"一個仍在有效期內的登入 token 曾經就是從這個縫進了 git 歷史。\n"
            f"改法：輸出一律寫進 private/（已 gitignore）。"
        )
    return None


# ═══════════════════════════════════════════════════════════════════════
# note 類規則（提醒，不擋）
# ═══════════════════════════════════════════════════════════════════════

def rule_cross_platform_sync(path):
    """改一邊沒改另一邊，畫面上看不出來。

    刻意是 note 不是 block：兩步編輯的中間狀態必然不同步，擋下來就是誤報。
    真正擋得住的那層是 commit 前的守衛。
    """
    p = path.replace("\\", "/")
    if "/web_" in p:
        return "改到 web 端 —— 檢查 mobile 端有沒有：①同樣功能 ②同樣 API call ③同樣 storage 欄位 ④同名事件。"
    if "/mobile_" in p:
        return "改到 mobile 端 —— 檢查 web 端有沒有：①同樣功能 ②同樣 API call ③同樣 storage 欄位 ④同名事件。"
    return None


def rule_task_file_concurrent_write(path):
    """並行寫入提醒。

    它擋的事故：另一個對話（或一個開著舊版的編輯器）任何一次存檔，
    都會把整個舊內容寫回去，靜默蓋掉你剛寫進去的東西。
    """
    if "/task/" in path.replace("\\", "/"):
        return ("動到 task/ 檔：並行對話或開著的編輯器存檔會靜默蓋掉你剛寫的內容。\n"
                "**每一個寫入步驟後都 grep -c 一次識別字**，不要只在最後驗。")
    return None


def rule_guard_changed_run_drill(path):
    """改了守衛的比對邏輯，不重跑演練，你不知道它是在擋還是沒事發生。"""
    p = path.replace("\\", "/")
    if "/tools/" in p and p.endswith(".py") and "drill" not in p:
        return "改到守衛 —— 記得重跑對應的 *_drill.py（注入 → 確認會紅 → 還原）。"
    return None


BLOCK_RULES = [rule_syntax_check, rule_secret_in_wrong_dir]
NOTE_RULES = [rule_cross_platform_sync, rule_task_file_concurrent_write, rule_guard_changed_run_drill]


def main():
    data = read_payload()
    path = edited_path(data)
    if not path or not os.path.exists(path):
        return

    for fn in BLOCK_RULES:
        reason = fn(path)
        if reason:
            block(f"[hook: {fn.__name__}]\n{reason}")
            return          # block 是終局，不再往下跑

    notes = [fn(path) for fn in NOTE_RULES]
    notes = [n for n in notes if n]
    if notes:
        note("\n".join(f"[hook] {n}" for n in notes))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # hook 永遠不可以因為自己爆掉而擋住工作
