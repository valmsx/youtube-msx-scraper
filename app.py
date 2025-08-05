from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
import re
from db import get_conn, init_db
import json

app = Flask(__name__)
init_db()

@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

def parse_youtube_date(published_text):
    """Convert YouTube relative date (e.g. '2 years ago') to exact date"""
    if not published_text:
        return ""
    
    now = datetime.now()
    try:
        if "hour" in published_text:
            hours = int(published_text.split()[0])
            return (now - timedelta(hours=hours)).strftime("%d/%m/%Y")
        elif "day" in published_text:
            days = int(published_text.split()[0])
            return (now - timedelta(days=days)).strftime("%d/%m/%Y")
        elif "week" in published_text:
            weeks = int(published_text.split()[0])
            return (now - timedelta(weeks=weeks)).strftime("%d/%m/%Y")
        elif "month" in published_text:
            months = int(published_text.split()[0])
            return (now - timedelta(days=months*30)).strftime("%d/%m/%Y")
        elif "year" in published_text:
            years = int(published_text.split()[0])
            return (now - timedelta(days=years*365)).strftime("%d/%m/%Y")
    except:
        return published_text
    return published_text

def search_youtube_scrape(query, max_results=20, layout="grid"):
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    html = res.text

    match = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not match:
        return []

    data = json.loads(match.group(1))
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
            channel = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "Unknown")
            date = vr.get("publishedTimeText", {}).get("simpleText", "")

            exact_date = parse_youtube_date(date)
            items.append({
                "title": title,
                "playerLabel": title,
                "label": f"{channel}\n{exact_date} • {date}" if exact_date else f"{channel} • {date}",
                "image": thumb,
                "action": f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={vid}",
                "style": {
                    "height": "medium" if layout == "grid" else "small"
                }
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
    layout = request.args.get("layout", "grid")

    if not query:
        return jsonify({
            "type": "pages",
            "headline": "YouTube Search",
            "template": {
                "type": "separate" if layout == "grid" else "list",
                "layout": "0,0,2,4" if layout == "grid" else "0,0,8,1",
                "color": "#FF0000",
                "imageFiller": "cover",
                "display": "vertical" if layout == "grid" else "horizontal"
            },
            "items": []
        })

    try:
        items = search_youtube_scrape(query, layout=layout)
    except Exception as e:
        return jsonify({
            "type": "pages",
            "headline": "Error",
            "items": [{
                "title": "Error",
                "label": str(e),
                "image": "https://via.placeholder.com/320x180.png?text=Error",
                "action": "none"
            }]
        }), 500

    response_data = {
        "type": "pages",
        "headline": f"YouTube: {query}",
        "actions": [
            {
                "title": "Grid View",
                "action": f"search:replace:http://{request.host}/msx_search?input={query}&layout=grid"
            },
            {
                "title": "List View",
                "action": f"search:replace:http://{request.host}/msx_search?input={query}&layout=list"
            },
            {
                "title": "Compact View",
                "action": f"search:replace:http://{request.host}/msx_search?input={query}&layout=compact"
            }
        ],
        "template": {
            "type": "separate" if layout == "grid" else "list",
            "layout": "0,0,2,4" if layout == "grid" else ("0,0,8,1" if layout == "list" else "0,0,10,1"),
            "color": "#FF0000",
            "imageFiller": "cover",
            "display": "vertical" if layout == "grid" else "horizontal",
            "itemLayout": {
                "titleFontSize": "medium",
                "labelFontSize": "small",
                "titleLines": 2,
                "labelLines": 2
            }
        },
        "items": items
    }

    return jsonify(response_data)

# ====================
# FAVORITES
# ====================

@app.route("/favorites", methods=["POST"])
def add_favorite():
    data = request.json
    title = data.get("title")
    url = data.get("url")
    img = data.get("image", "")
    fav_type = data.get("type", "video")
    channel = data.get("channel", "")
    video_id = data.get("video_id", "")

    if not title or not url:
        return jsonify({"error": "Missing data"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO favorites (type, title, url, image, channel, video_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING;
                """, (fav_type, title, url, img, channel, video_id))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites", methods=["GET"])
def list_favorites():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, url, image, type, channel FROM favorites ORDER BY created_at DESC;")
                rows = cur.fetchall()
        items = [{
            "title": r[0],
            "action": r[1],
            "image": r[2],
            "label": r[4],
            "style": {"height": "medium"}
        } for r in rows]
        return jsonify({
            "type": "pages",
            "headline": "Favorites",
            "template": {
                "type": "separate",
                "layout": "0,0,2,4",
                "color": "#FF0000",
                "imageFiller": "cover",
                "display": "vertical"
            },
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites/delete", methods=["POST"])
def delete_favorite():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "Missing URL"}), 400

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

@app.route("/history", methods=["GET"])
def list_history():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, url, image, channel, created_at FROM history ORDER BY created_at DESC;")
                rows = cur.fetchall()
        items = [{
            "title": r[0],
            "action": r[1],
            "image": r[2],
            "label": f"{r[3]}\n{r[4].strftime('%d/%m/%Y')}",
            "style": {"height": "medium"}
        } for r in rows]
        return jsonify({
            "type": "pages",
            "headline": "History",
            "template": {
                "type": "separate",
                "layout": "0,0,2,4",
                "color": "#FF0000",
                "imageFiller": "cover",
                "display": "vertical"
            },
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history", methods=["POST"])
def add_history():
    data = request.json
    title = data.get("title")
    url = data.get("url")
    img = data.get("image", "")
    hist_type = data.get("type", "video")
    channel = data.get("channel", "")
    video_id = data.get("video_id", "")

    if not title or not url:
        return jsonify({"error": "Missing data"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO history (type, title, url, image, channel, video_id)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (hist_type, title, url, img, channel, video_id))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
