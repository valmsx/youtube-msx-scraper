from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "https://msx.benzac.de"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    return response

@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

def search_youtube_scrape(query, max_results=50):
    # Prendiamo fino a max_results (default 50) risultati dalla ricerca YouTube (scraping)
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"
    }
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    html = res.text

    match = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not match:
        return []

    data = __import__("json").loads(match.group(1))
    contents = data.get("contents", {})\
        .get("twoColumnSearchResultsRenderer", {})\
        .get("primaryContents", {})\
        .get("sectionListRenderer", {})\
        .get("contents", [])

    items = []
    for section in contents:
        for c in section.get("itemSectionRenderer", {}).get("contents", []):
            vr = c.get("videoRenderer")
            if not vr:
                continue
            vid = vr.get("videoId")
            title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
            thumb = vr.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url", "")
            items.append({
                "title": title,
                "playerLabel": title,
                "image": thumb,
                "action": f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={vid}"
            })
            if len(items) >= max_results:
                break
        if len(items) >= max_results:
            break
    return items

@app.route("/msx_search")
def msx_search():
    query = request.args.get("input", "").strip()
    if not query:
        return jsonify({
            "type": "pages",
            "headline": "YouTube Search",
            "template": {
                "type": "separate",
                "layout": "0,0,3,3",
                "color": "black",
                "imageFiller": "cover"
            },
            "items": []
        })

    page = int(request.args.get("page", "1"))
    results_per_page = 8

    try:
        all_items = search_youtube_scrape(query, max_results=50)  # prendi max 50 risultati dallo scraping
    except Exception as e:
        return jsonify({
            "type": "pages",
            "headline": "Errore scraping",
            "template": {
                "type": "separate",
                "layout": "0,0,3,3",
                "color": "black",
                "imageFiller": "cover"
            },
            "items": [{
                "title": "Errore",
                "playerLabel": "Errore",
                "image": "https://via.placeholder.com/320x180.png?text=Error",
                "action": f"text:{str(e)}"
            }]
        }), 500

    start = (page - 1) * results_per_page
    end = start + results_per_page
    page_items = all_items[start:end]

    response = {
        "type": "pages",
        "headline": f"Risultati per '{query}'",
        "template": {
            "type": "separate",
            "layout": "0,0,3,3",
            "color": "black",
            "imageFiller": "cover"
        },
        "items": page_items
    }

    # Se ci sono ancora risultati dopo questa pagina, aggiungi nextPage per MSX
    if end < len(all_items):
        next_page = page + 1
        response["nextPage"] = f"https://youtube-msx-scraper.onrender.com/msx_search?input={requests.utils.quote(query)}&page={next_page}"

    return jsonify(response)
