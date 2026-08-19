import os
import csv
import re
import requests
from supabase import create_client

# 環境変数の取得
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 計算パラメーター
USD_TO_JPY = 155.0         # 1ドルあたりの円換算レート
IMPORT_TAX_RATE = 1.10     # 輸入消費税等 (10%)
SHIPPING_COST_USD = 15.0   # 1枚あたりの国際送料 ($15)
JP_PLATFORM_FEE = 0.09     # 国内販売手数料 (9%)
JP_SHIPPING_JPY = 500      # 国内発送送料 (500円)

# 簡易国内相場データベース
JAPAN_MARKET_DATABASE = {
    "229/BW-P": {"name": "ピカチュウ BW-P", "jp_price": 28000},
    "068/028":  {"name": "ミュウツー&ミュウGX", "jp_price": 45000},
    "154/XY-P": {"name": "ポンチョを着たピカチュウ", "jp_price": 180000},
    "001/S-P":  {"name": "ピカチュウ VMAX", "jp_price": 35000},
    "201/S-P":  {"name": "ピカチュウV", "jp_price": 22000},
}

def estimate_jp_market_price(title):
    """カード名・タイトルから日本の相場価格(JPY)を推定"""
    title_upper = title.upper()
    
    for code, info in JAPAN_MARKET_DATABASE.items():
        if code.upper() in title_upper:
            return info["jp_price"], info["name"]

    if "CHARIZARD" in title_upper or "リザードン" in title_upper:
        return 35000, "リザードン PSA10"
    elif "PIKACHU" in title_upper or "ピカチュウ" in title_upper:
        return 25000, "ピカチュウ PSA10"
    elif "MARNIE" in title_upper or "マリィ" in title_upper:
        return 40000, "マリィ PSA10"
    elif "LILLIE" in title_upper or "リーリエ" in title_upper:
        return 120000, "リーリエ PSA10"

    return 22000, "PSA10 Trading Card"

def load_items_from_csv(file_path="ebay_items.csv"):
    """CSVファイルからトレカ一覧を読み込む"""
    if not os.path.exists(file_path):
        print(f"⚠️ エラー: {file_path} が見つかりません。")
        return []

    items = []
    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                title = row.get("title", "").strip()
                # 価格の文字列整理 ($120.00 ➔ 120.00)
                price_raw = str(row.get("price_usd", "0")).replace("$", "").replace(",", "").strip()
                price_usd = float(price_raw)
                ebay_url = row.get("ebay_url", "").strip()

                if title and price_usd > 0 and ebay_url:
                    items.append({
                        "title": title,
                        "price_usd": price_usd,
                        "url": ebay_url
                    })
            except ValueError:
                continue

    return items

def run_auto_research():
    print("🔍 CSVベース リサーチシステムを開始します...")

    ebay_items = load_items_from_csv("ebay_items.csv")
    print(f"📊 CSVから読み込んだ総件数: {len(ebay_items)} 件")

    if not ebay_items:
        print("💡 処理を終了します。（CSVにデータがないか、形式が不適切です）")
        return

    total_found = 0

    for item in ebay_items:
        title = item["title"]
        ebay_url = item["url"]
        actual_price_usd = item["price_usd"]

        # DB重複チェック（すでに通知済みのURLはスキップ）
        existing = supabase.table("profit_cards").select("id").eq("ebay_url", ebay_url).execute()
        if existing.data:
            continue

        jp_market_jpy, matched_name = estimate_jp_market_price(title)

        # 利益計算
        total_cost_jpy = (actual_price_usd + SHIPPING_COST_USD) * USD_TO_JPY * IMPORT_TAX_RATE
        net_sales_jpy = jp_market_jpy * (1.0 - JP_PLATFORM_FEE) - JP_SHIPPING_JPY
        profit_jpy = round(net_sales_jpy - total_cost_jpy)
        roi_percent = round((profit_jpy / total_cost_jpy) * 100, 1)

        # 利益2,000円以上 ＆ ROI 15%以上 のみ通知
        if profit_jpy >= 2000 and roi_percent >= 15.0:
            total_found += 1
            print(f"🔥 お宝発見!: {title}")
            print(f"   仕入: ${actual_price_usd} (約{round(total_cost_jpy):,}円) ➔ 想定利益: {profit_jpy:,}円 (ROI: {roi_percent}%)")

            # Supabase保存
            supabase.table("profit_cards").insert({
                "card_name": f"{title} [{matched_name}]",
                "ebay_price_usd": actual_price_usd,
                "jp_price_jpy": jp_market_jpy,
                "profit_jpy": profit_jpy,
                "roi_percent": roi_percent,
                "ebay_url": ebay_url
            }).execute()

            # Discord通知
            if DISCORD_WEBHOOK_URL:
                payload = {
                    "embeds": [{
                        "title": f"🔥 【利益 {profit_jpy:,}円 / ROI {roi_percent}%】お宝カード発見！",
                        "description": (
                            f"**カード名:** {title}\n"
                            f"**eBay出品価格:** `${actual_price_usd}` (約{round(total_cost_jpy):,}円)\n"
                            f"**国内想定相場:** `¥{jp_market_jpy:,}`\n"
                            f"**想定利益:** `¥{profit_jpy:,}`\n\n"
                            f"👉 [eBayで商品ページを開く]({ebay_url})"
                        ),
                        "color": 5814783
                    }]
                }
                requests.post(DISCORD_WEBHOOK_URL, json=payload)

    print(f"✅ 処理完了: 新規発見お宝カード {total_found} 件")

if __name__ == "__main__":
    run_auto_research)
