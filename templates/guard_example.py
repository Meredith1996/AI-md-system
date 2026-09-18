"""守衛骨架 —— 放在 tools/，提交前手動跑（或掛進 CI）。

═══════════════════════════════════════════════════════════════════════════
一支合格的守衛，長什麼樣
═══════════════════════════════════════════════════════════════════════════

  PASS 時   只印一行，**而且那一行要有覆蓋率數字**。原始碼永遠不進上下文。
  FAIL 時   印出**實際抓到的那一行**，不是只印 pass/fail。
  前置條件不滿足時   **FAIL，不可以是 return。**

🚨 這三條都是踩出來的：

  · 一支守衛曾經用**五種不同的方式**報假綠燈。五種都印 PASS，五種都沒在驗東西。
  · 另一支的某個檢查方向因為載不到設定檔而整段跳過，**它照樣 exit 0** ——
    那個方向從此完全沒在驗，而終端機上看到的是一個漂亮的綠燈。

  ⇒ 判準：看到 `if not X: return` 出現在守衛裡，
     先問「**X 不在的時候，誰會知道**」。

═══════════════════════════════════════════════════════════════════════════
好的輸出 vs 壞的輸出
═══════════════════════════════════════════════════════════════════════════

  ✅  PASS  寫入端點 148 個 · 帶 write=True 145 · 具名豁免 3 · 未保護 0
  ❌  PASS

  第二種你永遠不知道它是驗過了，還是一個 return 就跳出去了。
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════
# 失敗的唯一出口
# ═══════════════════════════════════════════════════════════════════════

FAILURES = []


def fail(msg, evidence=None):
    """記一筆失敗。

    `evidence` 是**實際抓到的那一行**。演練會檢查它有沒有印出來 ——
    只看 exit code 的話，你分不出「抓到了」跟「因為別的原因紅了」。
    """
    FAILURES.append((msg, evidence))


def require(condition, msg):
    """前置條件。不滿足＝FAIL，不是 return。"""
    if not condition:
        fail(f"[前置條件不滿足] {msg} —— 這個方向整段沒有被驗到")
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════
# 檢查方向（每一個都要回報「走過幾個」）
# ═══════════════════════════════════════════════════════════════════════

def check_write_endpoints_guarded():
    """範例：所有寫入端點都必須帶權限檢查。

    它擋的那種安靜失敗：**前端把按鈕變灰、後端其實照寫。**
    而且參數預設是 False ⇒ 漏傳＝沒有防護，**而且沒有任何錯誤訊息**。
    ⇒ 所以覆蓋率必須由守衛去數，不能靠人記得。
    """
    api_dir = os.path.join(REPO, "app", "api")
    if not require(os.path.isdir(api_dir), f"找不到 {api_dir}"):
        return None                       # 前置條件已記成 FAIL，可以安全返回

    total = guarded = 0
    exempt = []
    for root, _dirs, files in os.walk(api_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for m in re.finditer(r'@router\.(post|put|patch|delete)\([^)]*\)\s*\n\s*async def (\w+)', src):
                total += 1
                # 往下看 20 行，找權限依賴
                tail = src[m.end():m.end() + 1200]
                if "write=True" in tail:
                    guarded += 1
                elif "# guard-exempt:" in tail:
                    exempt.append(m.group(2))
                else:
                    fail(
                        f"寫入端點 {m.group(2)} 沒有帶 write=True",
                        evidence=f"{os.path.relpath(path, REPO)}: {m.group(0).strip()}",
                    )

    # 🚨 覆蓋率是守衛的價值本身 —— 走了 0 個檔案也叫 PASS 的話，這支守衛沒有意義
    if total == 0:
        fail("走過 0 個寫入端點 —— 不是沒有問題，是沒去看")

    return f"寫入端點 {total} 個 · 帶 write=True {guarded} · 具名豁免 {len(exempt)} · 未保護 {total - guarded - len(exempt)}"


def check_declared_numbers_match_reality():
    """範例：文件宣稱的數字 vs code 現算。

    它擋的那種安靜失敗：文件說 84 張表，實際 103 張。
    而且錯的那一刻**沒有任何症狀**，是三個月後有人照著它做決定才炸。
    """
    doc = os.path.join(REPO, "CLAUDE.md")
    if not require(os.path.exists(doc), "找不到 CLAUDE.md"):
        return None

    with open(doc, encoding="utf-8") as f:
        text = f.read()

    actual = count_tables()                      # ← 換成你的現算邏輯
    checked = 0
    for m in re.finditer(r"(\d+)\s*張表", text):
        checked += 1
        declared = int(m.group(1))
        if declared != actual:
            fail(
                f"CLAUDE.md 宣稱 {declared} 張表，code 現算 {actual} 張",
                evidence=m.group(0),
            )

    if checked == 0:
        fail("沒有找到任何數字宣告 —— 可能是格式改了，這個方向已經失效")

    return f"規模數字宣告 {checked} 條與 code 現算一致（現值 {actual} 張表）"


def count_tables():
    """現算：從 model 檔數 __tablename__。"""
    n = 0
    models = os.path.join(REPO, "app", "models")
    if not os.path.isdir(models):
        return 0
    for fn in os.listdir(models):
        if fn.endswith(".py"):
            with open(os.path.join(models, fn), encoding="utf-8") as f:
                n += len(re.findall(r"__tablename__\s*=", f.read()))
    return n


# 掛上來的方向。加新方向＝這裡加一行 ＋ 在 drill 加正向與反向各一個。
CHECKS = [
    check_write_endpoints_guarded,
    check_declared_numbers_match_reality,
]


def main():
    summaries = []
    for fn in CHECKS:
        try:
            s = fn()
            if s:
                summaries.append(s)
        except Exception as e:
            # 🚨 例外 ＝ FAIL，不是「跳過這個方向」
            fail(f"{fn.__name__} 執行時爆炸：{e!r}")

    if FAILURES:
        print(f"[FAIL] {len(FAILURES)} 個問題\n")
        for msg, evidence in FAILURES:
            print(f"  · {msg}")
            if evidence:
                print(f"      實際抓到：{evidence}")     # ← 演練會檢查這一行
        sys.exit(1)

    # PASS 只印一行，而且那一行有數字
    print("[OK] " + "； ".join(summaries))
    sys.exit(0)


if __name__ == "__main__":
    main()
