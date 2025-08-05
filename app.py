from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
import re
from db import get_conn, init_db
import json
from urllib.parse import quote

app = Flask(__name__)
init_db()

# Configurazione CORS
@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

# Utility Functions
def parse_youtube_date(published_text):
    now = datetime.now()
    try:
        num = int(''.join(filter(str.isdigit, published_text)))
        if 'hour' in published_text:
            return (now - timedelta(hours=num)).strftime("%d/%m/%Y")
        elif 'day' in published_text:
            return (now - timedelta(days=num)).strftime("%d/%m/%Y")
        elif 'week' in published_text:
            return (now - timedelta(weeks=num)).strftime("%d/%m/%Y")
        elif 'month' in published_text:
            return (now - timedelta(days=num*30)).strftime("%d/%m/%Y")
        elif 'year' in published_text:
            return (now - timedelta(days=num*365)).strftime("%d/%m/%Y")
    except:
        return published_text
    return published_text

# Menu principale MSX
@app.route("/menu")
def msx_menu():
    return jsonify({
        "type": "menu",
        "headline": "YouTube MSX",
        "items": [
            {
                "title": "Cerca YouTube",
                "image": "https://i.ibb.co/6WXJq7P/youtube-search.png",
                "action": f"search:request:http://{request.host}/msx_search?input=$search$"
            },
            {
                "title": "Preferiti",
                "image": "https://i.ibb.co/0jW2Z6x/favorites.png",
                "action": f"content:load:http://{request.host}/favorites"
            },
            {
                "title": "Cronologia",
                "image": "https://i.ibb.co/7Yk6z0G/history.png",
                "action": f"content:load:http://{request.host}/history"
            }
        ]
    })

# Ricerca YouTube
@app.route("/msx_search", methods=["GET"])
def msx_search():
    query = request.args.get("input", "").strip()
    view_type = request.args.get("view", "grid")
    
    if not query:
        return jsonify({
            "type": "pages",
            "headline": "YouTube Search",
            "template": get_view_template(view_type),
            "items": []
        })

    try:
        items = []
        url = f"https://www.youtube.com/results?search_query={quote(query)}"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text
        yt_data = json.loads(re.search(r'var ytInitialData = ({.*?});</script>', html).group(1))
        
        for section in yt_data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']:
            for item in section.get('itemSectionRenderer', {}).get('contents', []):
                if 'videoRenderer' in item:
                    vid = item['videoRenderer']['videoId']
                    title = item['videoRenderer']['title']['runs'][0]['text']
                    channel = item['videoRenderer']['ownerText']['runs'][0]['text']
                    channel_id = item['videoRenderer']['ownerText']['runs'][0]['navigationEndpoint']['browseEndpoint']['browseId']
                    thumb = item['videoRenderer']['thumbnail']['thumbnails'][-1]['url']
                    date = parse_youtube_date(item['videoRenderer']['publishedTimeText']['simpleText'])
                    views = item['videoRenderer']['viewCountText']['simpleText']
                    
                    items.append({
                        "title": title,
                        "label": channel,
                        "footer": f"{date} • {views}",
                        "image": thumb,
                        "action": f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={vid}",
                        "buttons": [
                            {
                                "title": "📺 Canale",
                                "action": f"content:load:http://{request.host}/channel?channel_id={channel_id}"
                            }
                        ]
                    })
        
        return jsonify({
            "type": "pages",
            "headline": f"Risultati: {query}",
            "template": get_view_template(view_type),
            "actions": get_view_actions(query, view_type),
            "items": items[:20]
        })
        
    except Exception as e:
        return jsonify({
            "type": "pages",
            "headline": "Errore",
            "items": [{
                "title": "Errore durante la ricerca",
                "label": str(e),
                "image": "https://i.ibb.co/0jW2Z6x/error.png",
                "action": "none"
            }]
        })

# Gestione visualizzazioni
def get_view_template(view_type):
    templates = {
        "grid": {
            "type": "grid",
            "layout": "0,0,2,4",
            "display": "vertical",
            "color": "#FF0000",
            "imageFiller": "cover",
            "itemLayout": {
                "titleFontSize": "medium",
                "labelFontSize": "small",
                "footerFontSize": "small"
            }
        },
        "list": {
            "type": "list",
            "layout": "0,0,8,1",
            "display": "horizontal",
            "color": "#FF0000",
            "itemLayout": {
                "height": "small",
                "titleFontSize": "medium",
                "labelFontSize": "small"
            }
        }
    }
    return templates.get(view_type, templates["grid"])

def get_view_actions(query, current_view):
    views = ["grid", "list"]
    icons = {"grid": "🖼️", "list": "📋"}
    actions = []
    
    for view in views:
        if view != current_view:
            actions.append({
                "title": f"{icons[view]} {view.capitalize()}",
                "action": f"content:load:http://{request.host}/msx_search?input={quote(query)}&view={view}"
            })
    
    actions.extend([
        {
            "title": "🔍 Nuova ricerca",
            "action": "search:request"
        },
        {
            "title": "🏠 Home",
            "action": "menu:load:http://{request.host}/menu"
        }
    ])
    
    return actions

# Canali YouTube
@app.route("/channel")
def channel_videos():
    channel_id = request.args.get("channel_id")
    
    try:
        # Implementazione reale dello scraping del canale
        return jsonify({
            "type": "pages",
            "headline": "Video del Canale",
            "template": get_view_template("grid"),
            "actions": [
                {
                    "title": "🔙 Indietro",
                    "action": "back"
                }
            ],
            "items": [
                {
                    "title": "Video di esempio 1",
                    "label": "Nome Canale",
                    "image": "https://i.ibb.co/0jW2Z6x/video-placeholder.png",
                    "action": "none"
                }
            ]
        })
    except Exception as e:
        return jsonify({
            "type": "pages",
            "headline": "Errore Canale",
            "items": [{
                "title": "Errore caricamento canale",
                "label": str(e),
                "action": "none"
            }]
        })

# ====================
# FAVORITES
# ====================
@app.route("/favorites", methods=["POST"])
def add_favorite():
    data = request.json or request.form
    title = data.get("title")
    url = data.get("url") or f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={data.get('video_id')}"
    img = data.get("image", f"https://img.youtube.com/vi/{data.get('video_id')}/hqdefault.jpg")
    channel = data.get("channel", "")

    if not title or not url:
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO favorites (title, url, image, channel)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING;
                """, (title, url, img, channel))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites", methods=["GET"])
def list_favorites():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, url, image, channel FROM favorites ORDER BY created_at DESC;")
                rows = cur.fetchall()
        
        items = [{
            "title": r[0],
            "label": r[3],
            "image": r[2],
            "action": r[1],
            "buttons": [
                {
                    "title": "❌ Rimuovi",
                    "action": f"service:http://{request.host}/favorites/delete?url={quote(r[1])}"
                }
            ]
        } for r in rows]

        return jsonify({
            "type": "pages",
            "headline": "Preferiti",
            "actions": [
                {
                    "title": "🔙 Indietro",
                    "action": "back"
                }
            ],
            "template": get_view_template("grid"),
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites/delete", methods=["GET", "POST"])
def delete_favorite():
    url = request.args.get("url") or (request.json or request.form).get("url")
    if not url:
        return jsonify({"error": "URL mancante"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM favorites WHERE url = %s;", (url,))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ====================
# HISTORY
# ====================
@app.route("/history", methods=["POST"])
def add_history():
    data = request.json or request.form
    title = data.get("title")
    url = data.get("url") or f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={data.get('video_id')}"
    img = data.get("image", f"https://img.youtube.com/vi/{data.get('video_id')}/hqdefault.jpg")
    channel = data.get("channel", "")

    if not title or not url:
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO history (title, url, image, channel)
                    VALUES (%s, %s, %s, %s);
                """, (title, url, img, channel))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history", methods=["GET"])
def list_history():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT title, url, image, channel, created_at 
                    FROM history 
                    ORDER BY created_at DESC
                    LIMIT 50;
                """)
                rows = cur.fetchall()
        
        items = [{
            "title": r[0],
            "label": f"{r[3]} • {r[4].strftime('%d/%m/%Y')}",
            "image": r[2],
            "action": r[1],
            "buttons": [
                {
                    "title": "💖 Aggiungi",
                    "action": f"service:http://{request.host}/favorites?action=add&title={quote(r[0])}&url={quote(r[1])}"
                }
            ]
        } for r in rows]

        return jsonify({
            "type": "pages",
            "headline": "Cronologia",
            "actions": [
                {
                    "title": "🔙 Indietro",
                    "action": "back"
                },
                {
                    "title": "🗑️ Pulisci",
                    "action": f"service:http://{request.host}/history/clear"
                }
            ],
            "template": get_view_template("list"),
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history/clear", methods=["POST"])
def clear_history():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM history;")
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
