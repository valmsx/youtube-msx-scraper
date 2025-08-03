from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

@app.after_request
def apply_cors(response):
    # Modifica l'header CORS per permettere l'accesso da MSX
    response.headers["Access-Control-Allow-Origin"] = "https://msx.benzac.de"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    return response

@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

def search_youtube_scrape(query, max_results=8, page_token=None):
    # Nota: Youtube non usa 'page_token' nella ricerca semplice, ma useremo 'page' per la paginazione simulata
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"
    }
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    html = res.text

    match = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not match:
        return [], None

    data = __import__("json").loads(match.group(1))
    contents = data.get("contents", {})\
        .get("twoColumnSearchResultsRenderer", {})\
        .get("primaryContents", {})\
        .get("sectionListRenderer", {})\
        .get("contents", [])

    items = []
    count = 0
    for section in contents:
        for c in section.get("itemSectionRenderer", {}).get("contents", []):
            vr = c.get("videoRenderer")
            if not vr:
                continue
            if count >= max_results:
                break
            vid = vr.get("videoId")
            title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
            thumb = vr.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url", "")
            items.append({
                "title": title,
                "playerLabel": title,
                "image": thumb,
                "action": f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={vid}"
            })
            count += 1
        if count >= max_results:
            break

    # Nota: qui non abbiamo un vero nextPageToken perché è scraping semplice
    # Simuliamo nextPage se ci sono ancora risultati
    next_page = None
    if count == max_results:
        next_page = True  # flag per mostrare bottone pagina successiva

    return items, next_page

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

    # Gestione pagine: MSX manda ?page=1,2,...
    page = int(request.args.get("page", "1"))
    per_page = 8  # risultati per pagina

    try:
        # Per ora ignoriamo page_token (non implementato nel scraping)
        items, has_next = search_youtube_scrape(query, max_results=per_page * page)
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

    # Prendiamo solo i risultati della pagina corrente (paginazione manuale)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    # Se ci sono più risultati oltre questa pagina, aggiungiamo bottone pagina successiva
    if len(items) > end:
        next_page_num = page + 1
        page_items.append({
            "title": f"Pagina successiva ({next_page_num})",
            "playerLabel": f"Vai alla pagina {next_page_num}",
            "image": "https://via.placeholder.com/320x180.png?text=Next+Page",
            "action": f"page:/msx_search?input={requests.utils.quote(query)}&page={next_page_num}"
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
        "items": page_items
    })

if __name__ == "__main__":
    app.run(debug=True)
