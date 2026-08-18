import os
import re
import html
import requests
import xml.etree.ElementTree as ET
from supabase import create_client

# 環境変数の取得
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 為替レート・計算パラメーター
USD_TO_JPY = 155.0         # 1ドルあたりの円換算レート
IMPORT_TAX_RATE = 1.10     # 輸入時の消費税・関税目安 (10%)
SHIPPING_COST_USD = 15.0   # 1枚あたりの国際送料・転送費用目安 ($15)
JP_PLATFORM_FEE = 0.09     # 国内販売時の手数料目安 (約9%)
JP_SHIPPING_JPY = 500      # 国内発送送料目安 (500円)

# 簡易国内相場データベース（型番・キーマン検索用マスター）
# プログラムが型番を検知して自動的に相場を引き当てます
JAPAN_MARKET_DATABASE = {
    "229/BW-P": {"name": "ピカチュウ BW-P", "jp_price": 28000},
    "068/028":  {"name": "ミュウツー&ミュウGX GX", "jp_price": 45000},
    "154/XY-P": {"name": "ポンチョを着たピカチュウ", "jp_price": 180000},
    "001/S-P":  {"name": "ピカチュウ VMAX S-P", "jp_price": 35000},
    "201/S-P":  {"name": "ピカチュウV S-P", "jp_price": 22000},
}

def extract_price_from_text(text):
    """eBayのタイトルや説明文から出品価格($)を自動抽出する"""
    # $123.45 や $99 のような価格パターンを検索
    matches = re.findall(r'\$\s*([0-9]+(?:\.[0-9]{1,2})?)', text)
    if matches:
        # 見つかった最初の金額をフロートで返す
        return float(matches[0])
    return None

def estimate_jp_market_price(title):
    """カード名・タイトルから日本の相場価格(JPY)を動的に推定する"""
    title_upper = title.upper()
    
    # 1. 型番マスターデータベースとのマッチング
    for code, info in JAPAN_MARKET_DATABASE.items():
        if code.upper() in title_upper:
            return info["jp_price"], info["name"]

    # 2. マスターにない場合のキーワード推定ロジック（PSA10全般の安全推定）
    # タイトル内の人気キーワードから市場想定価格を自動推定
    if "CHARIZARD" in title_upper or "リザードン" in title_upper:
        return 35000, "リザードン PSA10"
    elif "PIKACHU" in title_upper or "ピカチュウ" in title_upper:
        return 25000, "ピカチュウ PSA10"
    elif "MARNIE" in title_upper or "マリィ" in title_upper:
        return 40000, "マリィ PSA10"
    elif "LILLIE" in title_upper or "リーリエ" in title_upper:
        return 120000, "リーリエ PSA10"
    elif "GENGAR" in title_upper or "ゲンガー" in title_upper:
        return 30000, "ゲンガー PSA10"

    # デフォルト推定相場（一般的なトレカPSA10相場）
    return 18000, "PSA10 Trading Card"

def fetch_ebay_rss_items(keyword):
    """eBayの新着RSSフィードからリアルタイムデータを取得"""
    encoded_kw = requests.utils.quote(keyword)
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_kw}&_rss=1&LH_BIN=1&_sop=10"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    response = requests.get(url, headers=headers, timeout=10)
    items = []
    
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else ""
            link = item.find('link').text if item.find('link') is not None else ""
            description = item.find('description').text if item.find('description') is not None else ""
            
            # 特殊文字のエスケープ解除
            title = html.unescape(title)
            
            # テキスト全体から価格を自動抽出
            price_usd = extract_price_from_text(title + " " + description)
            
            if price_usd and price_usd > 0:
                items.append({
                    "title": title,
                    "url": link,
                    "price_usd": price_usd
                })
    return items

def run_auto_research():
    print("🔍 リアルタイム自動リサーチを開始します...")

    # 自動巡回キーワードリスト（主要TCGのPSA10）
    search_keywords = [
        "Pokemon PSA 10 Japanese",
        "Yu-Gi-Oh PSA 10 Japanese",
        "One Piece Card PSA 10 Japanese",
        "Weiss Schwarz PSA 10 Japanese"
    ]

    for keyword in search_keywords:
        print(f"📡 巡回中: {keyword}")
        ebay_items = fetch_ebay_rss_items(keyword)

        for item in ebay_items[:10]: # 各キーワード最新10件チェック
            title = item["title"]
            ebay_url = item["url"]
            actual_price_usd = item["price_usd"] # ★実際の出品価格（ドル）

            # 過去に通知済みのURLは二重通知防止でスキップ
            existing = supabase.table("profit_cards").select("id").eq("ebay_url", ebay_url).execute()
            if existing.data:
                continue

            # 日本国内相場を動的に推定
            jp_market_jpy, matched_name = estimate_jp_market_price(title)

            # --- リアルタイム利益計算 ---
            # 仕入総額(円) = (商品価格USD + 国際送料USD) * 為替レート * 輸入消費税
            total_cost_jpy = (actual_price_usd + SHIPPING_COST_USD) * USD_TO_JPY * IMPORT_TAX_RATE
            
            # 販売入金額(円) = 国内売価 - 手数料 - 送料
            net_sales_jpy = jp_market_jpy * (1.0 - JP_PLATFORM_FEE) - JP_SHIPPING_JPY
            
            # 純利益 & ROI算出
            profit_jpy = round(net_sales_jpy - total_cost_jpy)
            roi_percent = round((profit_jpy / total_cost_jpy) * 100, 1)

            # 🔥 利益2,000円以上 ＆ ROI 15%以上 のみフィルタリング通知
            if profit_jpy >= 2000 and roi_percent >= 15.0:
                print(f"🔥 お宝発見!: {title}")
                print(f"   仕入(実売): ${actual_price_usd} (約{round(total_cost_jpy):,}円)")
                print(f"   想定国内相場: {jp_market_jpy:,}円 ➔ 利益: {profit_jpy:,}円 (ROI: {roi_percent}%)")

                # 1. Supabaseへリアルデータを保存
                supabase.table("profit_cards").insert({
                    "card_name": f"{title} [{matched_name}]",
                    "ebay_price_usd": actual_price_usd,
                    "jp_price_jpy": jp_market_jpy,
                    "profit_jpy": profit_jpy,
                    "roi_percent": roi_percent,
                    "ebay_url": ebay_url
                }).execute()

                # 2. Discordへ通知を発信
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

if __name__ == "__main__":
    run_auto_research()
