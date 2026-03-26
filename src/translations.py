"""
Bilingual Translation Dictionary for the Living Archive Dashboard.

Provides Traditional Chinese (繁體中文, Taiwan-style) translations for
document types, quality labels, health checks, tool names, UI terms,
and more. Intended for elderly Taiwanese family members.

Usage:
    from translations import zh, bilingual

    zh("legal/trust")          # "信託文件"
    zh("unknown key")          # "unknown key" (fallback)

    row = {"doc_type": "legal/trust", "quality": "good"}
    bilingual(row, ["doc_type", "quality"])
    # => {"doc_type": "legal/trust", "doc_type_zh": "信託文件",
    #     "quality": "good", "quality_zh": "良好"}
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Master dictionary  —  English key → Traditional Chinese value
# ---------------------------------------------------------------------------

_ZH: dict[str, str] = {

    # ------------------------------------------------------------------
    # 1. Document types  (23 unique)
    # ------------------------------------------------------------------
    "legal/trust":                  "信託文件",
    "financial/statement":          "財務報表",
    "legal/contract":               "合約",
    "employment/records":           "就業紀錄",
    "personal/certificate":         "個人證書",
    "employment/correspondence":    "工作往來信件",
    "personal/letter":              "私人信件",
    "legal/deed":                   "契約書",
    "financial/tax-return":         "報稅表",
    "medical/records":              "醫療紀錄",
    "personal/memorial":            "紀念文件",
    "medical/correspondence":       "醫療往來信件",
    "government/immigration":       "移民文件",
    "property/service-invoices":    "服務發票",
    "property/product-materials":   "產品資料",
    "personal/travel-records":      "旅行紀錄",
    "personal/correspondence":      "個人往來信件",
    "legal/will":                   "遺囑",
    "legal/power-of-attorney":      "委託書",
    "government/id":                "身份證件",
    "financial/mortgage":           "房屋貸款文件",
    "financial/insurance":          "保險文件",
    "financial/appraisal":          "鑑價報告",

    # ------------------------------------------------------------------
    # 2. Quality labels
    # ------------------------------------------------------------------
    "fair":   "尚可",
    "good":   "良好",
    "poor":   "不佳",

    # ------------------------------------------------------------------
    # 3. Language names
    # ------------------------------------------------------------------
    "English":                          "英文",
    "Chinese":                          "中文",
    "Japanese":                         "日文",
    "Bilingual":                        "雙語",
    "English/Chinese":                  "英文／中文",
    "Chinese/English":                  "中文／英文",
    "English and Chinese":              "英文與中文",
    "Bilingual (English and Chinese)":  "雙語（英文與中文）",

    # ------------------------------------------------------------------
    # 4. Sensitivity labels
    # ------------------------------------------------------------------
    "ssn":        "社會安全碼",
    "financial":  "財務資料",
    "medical":    "醫療資料",

    # ------------------------------------------------------------------
    # 5. Health check names
    # ------------------------------------------------------------------
    "NAS Mount":        "NAS 掛載",
    "Immich":           "Immich 相簿服務",
    "Claude CLI":       "Claude 命令列工具",
    "Catalog":          "目錄索引",
    "Data Freshness":   "資料新鮮度",
    "Synthesis DB":     "綜合資料庫",
    "Doc Index":        "文件索引",
    "People Registry":  "人物名冊",

    # ------------------------------------------------------------------
    # 6. Config keys
    # ------------------------------------------------------------------
    "MEDIA_ROOT":       "媒體根目錄",
    "DOCUMENTS_ROOT":   "文件根目錄",
    "AI_LAYER_DIR":     "AI 分析層目錄",
    "DOC_AI_LAYER_DIR": "文件 AI 分析層目錄",
    "IMMICH_URL":       "Immich 連線網址",
    "MODEL":            "AI 模型",
    "DOC_PROVIDER":     "文件處理供應商",
    "INFERENCE_MODE":   "推論模式",

    # ------------------------------------------------------------------
    # 7. Tool names  (18 tools)
    # ------------------------------------------------------------------
    "Photo Batch Runner":       "照片批次處理",
    "Single Slice Runner":      "單批次處理",
    "Document Extractor":       "文件擷取工具",
    "Document Scanner":         "文件掃描工具",
    "Document Index":           "文件索引工具",
    "Contact Sheet Triage":     "聯絡表分類",
    "Photo Analyzer":           "照片分析工具",
    "Catalog Manager":          "目錄管理工具",
    "Synthesis Engine":         "綜合分析引擎",
    "Dashboard Server":         "儀表板伺服器",
    "Haptic Browser":           "觸覺式瀏覽器",
    "People Sync":              "人物同步工具",
    "Dedup Report":             "重複比對報告",
    "Cost Estimator":           "成本估算工具",
    "Preflight Checks":         "預檢工具",
    "Review Dashboard":         "審閱儀表板",
    "Immich Push":              "Immich 上傳工具",
    "Chronology Builder":       "年表建立工具",

    # ------------------------------------------------------------------
    # 7b. Tool descriptions  (keyed as "desc:<ToolName>")
    # ------------------------------------------------------------------
    "desc:Photo Batch Runner":    "批次分析大量照片，自動產生 AI 描述",
    "desc:Single Slice Runner":   "針對單一批次照片進行分析處理",
    "desc:Document Extractor":    "從掃描檔案中擷取文字與關鍵資訊",
    "desc:Document Scanner":      "掃描並辨識文件內容",
    "desc:Document Index":        "建立與更新文件搜尋索引",
    "desc:Contact Sheet Triage":  "快速預覽並分類聯絡表上的照片",
    "desc:Photo Analyzer":        "深入分析單張照片的內容與細節",
    "desc:Catalog Manager":       "管理檔案目錄結構與分類",
    "desc:Synthesis Engine":      "整合多來源資料進行綜合分析",
    "desc:Dashboard Server":      "啟動與管理儀表板網頁伺服器",
    "desc:Haptic Browser":        "以觸覺式互動方式瀏覽檔案庫",
    "desc:People Sync":           "同步與更新人物資料庫",
    "desc:Dedup Report":          "偵測並報告重複的檔案或照片",
    "desc:Cost Estimator":        "估算 AI 分析所需的費用",
    "desc:Preflight Checks":      "執行系統環境預檢，確認一切就緒",
    "desc:Review Dashboard":      "開啟審閱儀表板，檢視待審項目",
    "desc:Immich Push":           "將照片上傳至 Immich 相簿服務",
    "desc:Chronology Builder":    "依照時間順序建立家族年表",

    # ------------------------------------------------------------------
    # 8. Tool categories
    # ------------------------------------------------------------------
    "pipeline":         "處理流程",
    "analysis":         "分析工具",
    "infrastructure":   "基礎設施",
    "review":           "審閱工具",

    # ------------------------------------------------------------------
    # 9. Common UI terms
    # ------------------------------------------------------------------
    "Dashboard":        "儀表板",
    "Overview":         "總覽",
    "Settings":         "設定",
    "Status":           "狀態",
    "Healthy":          "正常",
    "Unhealthy":        "異常",
    "Unknown":          "未知",
    "Error":            "錯誤",
    "Warning":          "警告",
    "OK":               "正常",
    "Loading":          "載入中",
    "Search":           "搜尋",
    "Filter":           "篩選",
    "Sort":             "排序",
    "Name":             "名稱",
    "Date":             "日期",
    "Type":             "類型",
    "Size":             "大小",
    "Count":            "數量",
    "Total":            "總計",
    "Details":          "詳細資訊",
    "Description":      "說明",
    "Actions":          "操作",
    "Run":              "執行",
    "Stop":             "停止",
    "Refresh":          "重新整理",
    "Export":           "匯出",
    "Import":           "匯入",
    "Delete":           "刪除",
    "Edit":             "編輯",
    "Save":             "儲存",
    "Cancel":           "取消",
    "Confirm":          "確認",
    "Back":             "返回",
    "Next":             "下一步",
    "Previous":         "上一步",
    "Page":             "頁",
    "of":               "之",
    "Yes":              "是",
    "No":               "否",
    "None":             "無",
    "All":              "全部",
    "Selected":         "已選取",
    "Pending":          "待處理",
    "Complete":         "已完成",
    "Failed":           "失敗",
    "In Progress":      "進行中",
    "Photos":           "照片",
    "Documents":        "文件",
    "People":           "人物",
    "Family":           "家庭",
    "Archive":          "檔案庫",
    "Living Archive":   "家族生活檔案庫",
    "Last Updated":     "最後更新",
    "Created":          "建立日期",
    "Modified":         "修改日期",
    "Sensitivity":      "敏感度",
    "Language":         "語言",
    "Quality":          "品質",
    "Category":         "分類",
    "Tools":            "工具",
    "Health":           "系統健康",
    "Config":           "設定",
    "Help":             "說明",
    "About":            "關於",
    "Version":          "版本",
    "Logout":           "登出",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def zh(key: str) -> str:
    """Return the Traditional Chinese translation for *key*.

    Falls back to the original English key if no translation exists,
    so callers never get a KeyError or None.
    """
    return _ZH.get(key, key)


def bilingual(data: dict, fields: list[str]) -> dict:
    """Add ``<field>_zh`` siblings to *data* for each field in *fields*.

    Example::

        >>> row = {"doc_type": "legal/trust", "quality": "good"}
        >>> bilingual(row, ["doc_type", "quality"])
        {'doc_type': 'legal/trust', 'doc_type_zh': '信託文件',
         'quality': 'good', 'quality_zh': '良好'}

    The original dict is mutated *and* returned for convenience.
    Non-string values and missing keys are silently skipped.
    """
    for field in fields:
        value = data.get(field)
        if isinstance(value, str):
            data[f"{field}_zh"] = zh(value)
    return data


# ---------------------------------------------------------------------------
# Convenience: expose the raw dict for iteration / export
# ---------------------------------------------------------------------------

def all_translations() -> dict[str, str]:
    """Return a shallow copy of the full translation dictionary."""
    return dict(_ZH)
