# templates — 可直接複製的骨架

回：[README](../README.md)

每一份都是**精簡到能立刻用**的版本，不是完整實作。
角括號 `<...>` 是要你填的地方。

| 檔案 | 放哪 | 用途 | 先讀 |
|---|---|---|---|
| [CLAUDE.md](CLAUDE.md) | repo 根目錄 | 規則檔骨架，含體例說明與分流表 | [02](../02-rules-file.md) |
| [MEMORY.md](MEMORY.md) | agent 的記憶目錄 | 記憶索引 ＋ 五類記憶各一則範例 | [03](../03-memory.md) |
| [work.txt](work.txt) | `task/` | 排程表（一列一行 ＋ 技術債 ＋ 決策紀錄） | [04](../04-task-files.md) |
| [journal.txt](journal.txt) | `task/` | 當季日誌（append-only） | [04](../04-task-files.md) |
| [evidence.txt](evidence.txt) | `task/` | 證據帳本（每列要有實測數字） | [04](../04-task-files.md) |
| [POSTMORTEMS.md](POSTMORTEMS.md) | repo 根目錄 | 事故記錄，含一則完整範例 | [05](../05-guards.md) |
| [settings.json](settings.json) | `.claude/` | hook 掛載設定 | [05](../05-guards.md) |
| [hook_pre_bash.py](hook_pre_bash.py) | `tools/hooks/` | 指令送出前攔截（含反向案例） | [05](../05-guards.md) |
| [hook_post_edit.py](hook_post_edit.py) | `tools/hooks/` | 檔案寫入後檢查 | [05](../05-guards.md) |
| [guard_example.py](guard_example.py) | `tools/` | 守衛骨架，**含覆蓋率輸出** | [05](../05-guards.md) |
| [guard_drill_example.py](guard_drill_example.py) | `tools/` | 故障演練，**含反向方向** | [05](../05-guards.md) |
| [SKILL.md](SKILL.md) | `.claude/skills/<name>/` | 把整套流程包成一個可呼叫的 skill | [06](../06-daily-loop.md) |

---

## 建議的落地順序

```
第 1 天   CLAUDE.md ＋ work.txt ＋ hook_pre_bash.py（只裝一條規則）
第 1 週   journal.txt ＋ POSTMORTEMS.md（讓事故開始累積）
第 2 週   guard_example.py（挑一件「做完了也不會知道出錯」的事）
第 3 週   guard_drill_example.py（你很可能會發現守衛根本沒在驗）
第 4 週   evidence.txt ＋ MEMORY.md ＋ 第一次瘦身
```

**不要一天裝完。** 沒有事故當依據的規則，九成是猜的。

---

## ⚠️ 兩件事

1. **hook 的設定檔通常不進版控**（多數 agent 的設定目錄被 gitignore 擋掉）。
   ⇒ 把**安裝動作寫成版控裡的腳本**，換機器時是「再跑一次」而不是「重寫一遍」。
2. **`.git/hooks/` 也不進版控**，理由同上，而且它更安靜 ——
   守衛不見了的時候不會有任何訊息。
