from flask import Flask, request, jsonify, make_response
import requests
import re
import json

app = Flask(__name__)

# CORS sempre abilitato
@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    return response

# Ping per debug
@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

def search_youtube_scrape(query, max_results=50):
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    html = res.text

    match = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not match:
        return []

    data = json.loads(match.group(1))
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

@app.route("/msx_search", methods=["GET", "OPTIONS"])
def msx_search():
    if request.method == "OPTIONS":
        return '', 204

    query = request.args.get("input", "").strip()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    per_page = 8

    # Risposta vuota per input mancante
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

    # Esegue lo scraping
    try:
        all_items = search_youtube_scrape(query, max_results=50)
    except Exception as e:
        return make_response(jsonify({
            "type": "pages",
            "headline": "Errore scraping",
            "template": {
                "type": "separate",
                "layout": "0,0,3,3",
                "color": "black",
                "imageFiller": "cover"
            },
            "items": [{
                "title": "Errore durante scraping",
                "playerLabel": str(e),
                "image": "https://via.placeholder.com/320x180.png?text=Error",
                "action": f"text:Errore interno"
            }]
        }), 500)

    # Suddivide in pagine
    start = (page - 1) * per_page
    end = start + per_page
    page_items = all_items[start:end]

    # Aggiunge navigazione
    nav = []
    if page > 1:
        nav.append({
            "title": "← Pagina precedente",
            "playerLabel": "Vai alla pagina precedente",
            "image": "https://via.placeholder.com/320x180.png?text=Prev",
            "action": f"page:/msx_search?input={requests.utils.quote(query)}&page={page-1}"
        })
    if end < len(all_items):
        nav.append({
            "title": "Pagina successiva →",
            "playerLabel": "Vai alla pagina successiva",
            "image": "https://via.placeholder.com/320x180.png?text=Next",
            "action": f"page:/msx_search?input={requests.utils.quote(query)}&page={page+1}"
        })

    # Costruisce il JSON di risposta
    return jsonify({
        "type": "pages",
        "headline": f"Risultati per '{query}' (pagina {page})",
        "template": {
            "type": "separate",
            "layout": "0,0,3,3",
            "color": "black",
            "imageFiller": "cover"
        },
        "items": page_items + nav
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__('os').environ.get('PORT', 5000)))
