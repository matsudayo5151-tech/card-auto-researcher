import os
import csv
import re
import requests
import xml.etree.ElementTree as ET
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

def fetch_ebay_via_rss(keyword):
    """eBay RSSフィードから最新出品情報を自動取得する（AppID不要）"""
    encoded_keyword = requests.utils.quote(keyword)
    # LH_BIN=1 (Buy It Now / 即決のみ), _sop=10 (新着順)
    rss_url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_keyword}&_rss=1&LH_BIN=1&_sop=10"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    items = []
    try:
        res = requests.get(rss_url, headers=headers, timeout=15)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            # RSS2.0の <item> タグを解析
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                
                # 価格の抽出 (description内の金額表記や標準タグから取得)
                description = item.find("description").text if item.find("description") is not None else ""
                price_match = re.search(r"\$\s*([\d,]+\.\d{2})", description)
                
                if price_match:
                    price_usd = float(price_match.group(1).replace(",", ""))
                else:
                    price_usd = 0.0

                if title and price_usd > 0 and link:
                    # Clean up URL parameters
                    clean_link = link.split("?")[0]
                    items.append({
                        "title": title,
                        "price_usd": price_usd,
                        "ebay_url": clean_link
                    })
    except Exception as e:
        print(f"⚠️ RSS取得エラー ({keyword}): {e}")

    return items

def fetch_and_save_ebay_csv(file_path="ebay_items.csv"):
    """RSS経由で全キーワードの最新データを取得しCSV化"""
    search_keywords = [
        "Pokemon PSA 10 Japanese",
        "Yu-Gi-Oh PSA 10 Japanese",
        "One Piece Card PSA 10 Japanese",
        "Weiss Schwarz PSA 10 Japanese"
    ]

    all_fetched_items = []
    print("📡 eBay RSSフィードから最新データの一括取得を開始します...")

    for keyword in search_keywords:
        fetched = fetch_ebay_via_rss(keyword)
        print(f"   ➔ {keyword}: {len(fetched)} 件取得")
        all_fetched_items.extend(fetched)

    # 重複削除
    unique_items = {item["ebay_url"]: item for item in all_fetched_items}.values()

    # CSVファイルへ上書き保存
    with open(file_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "price_usd", "ebay_url"])
        writer.writeheader()
        writer.writerows(unique_items)

    print(f"💾 合計 {len(unique_items)} 件の最新商品を {file_path} に自動保存しました。")

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
    print("🔍 RSS自動生成＆リサーチシステムを開始します...")

    # 1. RSS経由で最新データを取得しCSVを自動作成
    fetch_and_save_ebay_csv("ebay_items.csv")

    # 2. 生成されたCSVを解析
    ebay_items = load_items_from_csv("ebay_items.csv")
    print(f"📊 解析対象件数: {len(ebay_items)} 件")

    if not ebay_items:
        print("💡 処理を終了します。（データが取得できませんでした）")
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
    run_auto_research()
