"""故障演練 —— 證明守衛真的會紅。

放在 tools/<guard>_drill.py。**改過守衛的比對邏輯，就要重跑這支。**

═══════════════════════════════════════════════════════════════════════════
為什麼這一層不可省略
═══════════════════════════════════════════════════════════════════════════

  🚨 **壞掉的守衛跟正常的守衛，在終端機上長得一模一樣。**

  一支新守衛曾經用**五種不同的方式**報假綠燈。五種都印 PASS，五種都沒在驗東西。
  沒有這一層的話，你的守衛有可能從第一天起就什麼都沒在擋，而你完全不會知道。

═══════════════════════════════════════════════════════════════════════════
標準流程（四個細節都是踩出來的）
═══════════════════════════════════════════════════════════════════════════

  1. **注入要真的改檔案**，不是 mock —— mock 驗的是你的想像。
  2. **要檢查「抓到的那一行」**，不是只看 exit code
     —— 有可能是**別的原因**讓它紅的。
  3. **還原一律 try/finally** —— 演練中斷會留下一個被污染的 repo。
  4. **逐位元組比對還原** —— 「看起來還原了」跟「還原了」是兩件事。

🚨 **必含反向方向**（近似但不該中的輸入必須放行）。
   沒有反向案例的話，一支 `return FAIL` 的守衛會在演練裡拿滿分。
   實際比例可以抓 40% 左右：41 個方向裡 18 個是反向。
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(REPO, "tools", "guard_example.py")


# ═══════════════════════════════════════════════════════════════════════
# 方向定義
# ═══════════════════════════════════════════════════════════════════════
# expect_fail=True   正向：注入假故障，守衛**必須**紅，而且必須印出 marker
# expect_fail=False  反向：注入一個「近似但合法」的東西，守衛**必須**放行

DIRECTIONS = [
    {
        "name": "D1 宣稱的表數被改掉 → 必須紅",
        "file": "CLAUDE.md",
        "find": r"(\d+) 張表",
        "replace": "999 張表",
        "expect_fail": True,
        "marker": "999",                    # ← FAIL 訊息裡必須出現這個
    },
    {
        "name": "D2 寫入端點拿掉權限檢查 → 必須紅",
        "file": "app/api/v1/endpoints/example.py",
        "find": r"write=True",
        "replace": "write=False",
        "expect_fail": True,
        "marker": "沒有帶 write=True",
    },
    {
        "name": "D3【反向】註解裡出現「999 張表」→ 必須放行",
        "file": "CLAUDE.md",
        "find": r"## Conventions",
        "replace": "## Conventions\n<!-- 舉例：如果寫 999 張表就會被擋 -->",
        "expect_fail": False,               # ← 這是反向：不該中
    },
    {
        "name": "D4【反向】具名豁免的端點 → 必須放行",
        "file": "app/api/v1/endpoints/example.py",
        "find": r"write=True",
        "replace": "# guard-exempt: 公開端點，設計上不需要權限",
        "expect_fail": False,
    },
]


def run_guard():
    """單獨執行守衛並讀 exit code。

    🚨 **不要接管線。** `cmd | tail` 會把 exit code 換成 tail 的，
    曾經真的因此帶著紅燈提交過。
    """
    r = subprocess.run([sys.executable, GUARD], capture_output=True, text=True, cwd=REPO)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def drill_one(d):
    path = os.path.join(REPO, d["file"])
    if not os.path.exists(path):
        print(f"  [SKIP-FAIL] {d['name']}：找不到 {d['file']}")
        return False                        # 🚨 找不到檔案＝這個方向沒驗到＝失敗，不是跳過

    with open(path, "rb") as f:
        original = f.read()                 # ← 逐位元組保存

    try:
        text = original.decode("utf-8")
        injected, n = re.subn(d["find"], d["replace"], text, count=1)
        if n == 0:
            print(f"  [SKIP-FAIL] {d['name']}：注入錨點沒找到（`{d['find']}`）—— 這個方向已經失效")
            return False                    # 錨點失效也是失敗：規則變了但演練沒跟上

        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(injected)

        code, out = run_guard()

        if d["expect_fail"]:
            if code == 0:
                print(f"  [FAIL] {d['name']}：注入了假故障，守衛卻是綠的 —— 這個方向沒在驗")
                return False
            if d.get("marker") and d["marker"] not in out:
                print(f"  [FAIL] {d['name']}：守衛紅了，但沒印出 `{d['marker']}`"
                      f" —— 可能是**別的原因**讓它紅的")
                return False
            print(f"  [OK]   {d['name']}")
            return True
        else:
            if code != 0:
                print(f"  [FAIL] {d['name']}：**誤報** —— 合法的輸入被擋下來了")
                print(f"         誤報比漏報更危險：它會讓人把守衛關掉。")
                return False
            print(f"  [OK]   {d['name']}（反向）")
            return True

    finally:
        # 🚨 一律還原，而且逐位元組比對
        with open(path, "wb") as f:
            f.write(original)
        with open(path, "rb") as f:
            if f.read() != original:
                print(f"  [FATAL] {d['file']} 還原失敗 —— repo 現在是髒的，請手動檢查")
                sys.exit(2)


def main():
    print(f"故障演練：{len(DIRECTIONS)} 個方向"
          f"（正向 {sum(1 for d in DIRECTIONS if d['expect_fail'])}"
          f" · 反向 {sum(1 for d in DIRECTIONS if not d['expect_fail'])}）\n")

    # 前置：守衛在乾淨狀態下必須是綠的，否則後面的紅燈全部沒有意義
    code, _ = run_guard()
    if code != 0:
        print("[ABORT] 守衛在乾淨狀態下就是紅的 —— 先修好它，再跑演練")
        sys.exit(1)

    results = [drill_one(d) for d in DIRECTIONS]
    passed = sum(results)

    print(f"\n{'[OK]' if passed == len(DIRECTIONS) else '[FAIL]'} "
          f"{passed}/{len(DIRECTIONS)} 個方向通過")
    sys.exit(0 if passed == len(DIRECTIONS) else 1)


if __name__ == "__main__":
    main()
