from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
from db import get_conn, init_db
import os
import json

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

init_db()

# Helper per risposte standard MSX
def msx_response(headline, contents):
    return {
        "type": "pages",
        "headline": headline,
        "contents": contents
    }

@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

def search_youtube_scrape(query, max_results=20):
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        html = res.text

        # Parsing più robusto con BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        script = soup.find('script', string=re.compile('var ytInitialData'))
        
        if not script:
            return []

        json_str = script.string.split('var ytInitialData = ')[1].split(';')[0]
        data = json.loads(json_str)

        videos = []
        contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [{}])[0].get('itemSectionRenderer', {}).get('contents', [])

        for item in contents:
            if len(videos) >= max_results:
                break
                
            if 'videoRenderer' not in item:
                continue
                
            video = item['videoRenderer']
            video_id = video.get('videoId')
            title = video.get('title', {}).get('runs', [{}])[0].get('text', '')
            thumbnail = video.get('thumbnail', {}).get('thumbnails', [{}])[-1].get('url', '')
            channel = video.get('ownerText', {}).get('runs', [{}])[0].get('text', '')
            
            videos.append({
                "type": "video",
                "title": title,
                "id": video_id,
                "thumbnail": thumbnail,
                "channel": channel,
                "actions": [
                    {
                        "label": "Play",
                        "action": "youtube:play",
                        "payload": {"videoId": video_id}
                    },
                    {
                        "label": "Salva",
                        "action": "youtube:save",
                        "payload": {
                            "title": title,
                            "videoId": video_id,
                            "thumbnail": thumbnail,
                            "channel": channel
                        }
                    }
                ]
            })

        return videos

    except Exception as e:
        print(f"Error during scraping: {str(e)}")
        return []

@app.route("/msx_search", methods=["GET", "OPTIONS"])
def msx_search():
    if request.method == "OPTIONS":
        return '', 204

    query = request.args.get("input", "").strip()
    if not query:
        return jsonify(msx_response("YouTube Search", []))

    try:
        items = search_youtube_scrape(query)

        # Salva la ricerca nella cronologia
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO history (query) VALUES (%s)
                        ON CONFLICT (query) DO UPDATE SET timestamp = CURRENT_TIMESTAMP;
                    """, (query,))
                    conn.commit()
        except Exception as db_error:
            print(f"[WARN] Errore salvataggio history: {db_error}")

        return jsonify(msx_response(f"Risultati per '{query}'", items))

    except Exception as e:
        error_item = {
            "type": "item",
            "title": "Errore durante la ricerca",
            "image": "https://via.placeholder.com/320x180.png?text=Error",
            "actions": [{
                "label": "Dettagli",
                "action": "text",
                "payload": {"message": str(e)}
            }]
        }
        return jsonify(msx_response("Errore scraping", [error_item])), 500

@app.route("/favorites", methods=["GET", "OPTIONS"])
def list_favorites():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Query corretta per estrarre video_id
                cur.execute("""
                    SELECT 
                        title, 
                        url, 
                        image, 
                        type,
                        CASE
                            WHEN url ~ 'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})' THEN 
                                (regexp_matches(url, 'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})'))[1]
                            WHEN url ~ 'youtu\.be/([a-zA-Z0-9_-]{11})' THEN 
                                (regexp_matches(url, 'youtu\.be/([a-zA-Z0-9_-]{11})'))[1]
                            ELSE NULL
                        END as video_id,
                        channel
                    FROM favorites;
                """)
                rows = cur.fetchall()
                
        contents = []
        for r in rows:
            item = {
                "type": r[3] if r[3] in ["video", "directory"] else "video",
                "title": r[0],
                "id": r[4],
                "thumbnail": r[2],
                "actions": [
                    {
                        "label": "Play" if r[3] == "video" else "Apri",
                        "action": "youtube:play",
                        "payload": {"videoId": r[4]}
                    },
                    {
                        "label": "Rimuovi",
                        "action": "youtube:remove",
                        "payload": {"url": r[1]}
                    }
                ]
            }
            if r[5]:  # Se esiste il campo channel
                item["channel"] = r[5]
            contents.append(item)
            
        return jsonify(msx_response("Preferiti", contents))
        
    except Exception as e:
        return jsonify(msx_response("Errore", [{
            "type": "item",
            "title": "Errore nel caricamento",
            "actions": [{
                "label": "Dettagli",
                "action": "text",
                "payload": {"message": str(e)}
            }]
        }])), 500

@app.route("/favorites", methods=["POST", "OPTIONS"])
def add_favorite():
    if request.method == "OPTIONS":
        return '', 204
        
    data = request.json
    required_fields = ["title", "videoId"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO favorites (
                        type, 
                        title, 
                        url, 
                        image, 
                        video_id,
                        channel
                    ) VALUES (
                        %s, %s, 
                        %s, %s, 
                        %s, %s
                    )
                    ON CONFLICT (video_id) DO NOTHING;
                """, (
                    data.get("type", "video"),
                    data["title"],
                    f"https://youtube.com/watch?v={data['videoId']}",
                    data.get("thumbnail", ""),
                    data["videoId"],
                    data.get("channel", "")
                ))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites/delete", methods=["POST", "OPTIONS"])
def delete_favorite():
    if request.method == "OPTIONS":
        return '', 204
        
    data = request.json
    if "url" not in data:
        return jsonify({"error": "URL mancante"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM favorites WHERE url = %s;", (data["url"],))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history", methods=["GET", "OPTIONS"])
def get_history():
    if request.method == "OPTIONS":
        return '', 204
        
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT query FROM history 
                    ORDER BY timestamp DESC 
                    LIMIT 30;
                """)
                rows = cur.fetchall()
                
        contents = [{
            "type": "item",
            "title": r[0],
            "image": "https://via.placeholder.com/320x180.png?text=History",
            "actions": [{
                "label": "Cerca",
                "action": "youtube:search",
                "payload": {"query": r[0]}
            }]
        } for r in rows]
        
        return jsonify(msx_response("Cronologia", contents))
        
    except Exception as e:
        return jsonify(msx_response("Errore", [{
            "type": "item",
            "title": "Errore nel caricamento",
            "actions": [{
                "label": "Dettagli",
                "action": "text",
                "payload": {"message": str(e)}
            }]
        }])), 500

@app.route("/history/delete", methods=["POST", "OPTIONS"])
def delete_history_item():
    if request.method == "OPTIONS":
        return '', 204
        
    data = request.json
    if "query" not in data:
        return jsonify({"error": "Query mancante"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM history WHERE query = %s;", (data["query"],))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

