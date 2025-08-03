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
    contents = data.get("contents", {}) \
        .get("twoColumnSearchResultsRenderer", {}) \
        .get("primaryContents", {}) \
        .get("sectionListRenderer", {}) \
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
    try:
        page = int(request.args.get("page", "1"))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    items_per_page = 8
    base_url = "https://youtube-msx-scraper.onrender.com/msx_search"

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

    try:
        all_items = search_youtube_scrape(query, max_results=50)
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

    start = (page - 1) * items_per_page
    end = start + items_per_page
    paginated_items = all_items[start:end]

    nav_items = []

    if page > 1:
        nav_items.append({
            "title": "Pagina precedente",
            "image": "https://via.placeholder.com/320x180.png?text=<<",
            "action": f"page:{base_url}?input={requests.utils.quote(query)}&page={page - 1}"
        })
    if end < len(all_items):
        nav_items.append({
            "title": "Pagina successiva",
            "image": "https://via.placeholder.com/320x180.png?text=>>",
            "action": f"page:{base_url}?input={requests.utils.quote(query)}&page={page + 1}"
        })

    return jsonify({
        "type": "pages",
        "headline": f"Risultati per '{query}' (pagina {page})",
        "template": {
            "type": "separate",
            "layout": "0,0,3,3",
            "color": "black",
            "imageFiller": "cover"
        },
        "items": paginated_items + nav_items
    })
