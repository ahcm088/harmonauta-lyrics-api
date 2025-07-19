from flask import Flask, request, jsonify
from flask_caching import Cache
import requests
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
import ssl
import re
import os
from urllib3.util.ssl_ import create_urllib3_context

app = Flask(__name__)

# Configuração do cache
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 3600  # 1 hora de cache
})

# Configurações de User-Agent
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
]

class SSLAdapter(requests.adapters.HTTPAdapter):
    """Adaptador personalizado para configuração SSL segura"""
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

def create_session():
    """Cria uma sessão com configurações seguras"""
    session = requests.Session()
    
    # Configura SSL seguro
    adapter = SSLAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # Configura headers padrão
    session.headers.update({
        'Accept-Language': 'pt-BR',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive'
    })
    
    # Armazena a função original request
    original_request = session.request
    
    # Cria uma nova função com timeout padrão
    def request_with_timeout(method, url, **kwargs):
        kwargs.setdefault('timeout', (3.05, 27))  # (connect, read)
        return original_request(method, url, **kwargs)
    
    # Substitui o método request
    session.request = request_with_timeout
    
    return session

def sanitize_slug(text):
    """Sanitiza texto para uso em URLs"""
    return (
        text.strip()
        .lower()
        .replace(" ", "-")
        .replace("'", "")
        .replace("á", "a").replace("à", "a").replace("ã", "a").replace("â", "a")
        .replace("é", "e").replace("ê", "e")
        .replace("í", "i").replace("î", "i")
        .replace("ó", "o").replace("ô", "o").replace("õ", "o")
        .replace("ú", "u").replace("û", "u")
        .replace("ç", "c")
    )

def clean_lyrics(text):
    """Limpa o texto da letra"""
    text = re.sub(r'\n{3,}', '\n\n', text)  # Remove múltiplas quebras de linha
    text = re.sub(r'^\s+', '', text)  # Remove espaços no início
    text = re.sub(r'<[^>]+>', '', text)  # Remove tags HTML
    return text.strip()

@app.route('/api/lyrics', methods=['GET'])
@cache.cached(timeout=3600, query_string=True)
def get_lyrics():
    title = request.args.get('title', '').strip().title()
    artist = request.args.get('artist', '').strip()
    
    if not title or not artist:
        return jsonify({
            'success': False,
            'message': 'Por favor, forneça o título e o artista'
        }), 400

    try:
        # Cria sessão segura
        session = create_session()
        session.headers.update({'User-Agent': USER_AGENTS[0]})
        
        artist_slug = sanitize_slug(artist)
        
        # Tentar diferentes variações da URL do artista
        artist_urls = [
            f"https://www.letras.com/{artist_slug}/",
            f"https://www.letras.com/{artist_slug}-mc/",
            f"https://www.letras.com/{artist_slug}-banda/",
            f"https://www.letras.com/{artist_slug}-musica/",
        ]

        response = None
        for url in artist_urls:
            try:
                response = session.get(url)
                if response.status_code == 200:
                    break
            except requests.exceptions.SSLError as e:
                app.logger.warning(f"SSL Error for {url}: {str(e)}")
                continue
            except requests.RequestException:
                continue

        if not response or response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Artista não encontrado no letras.com'
            }), 404

        soup = BeautifulSoup(response.text, "html.parser")
        song_links = soup.find_all("a", title=True)

        # Compara títulos por similaridade
        def similarity(a, b):
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

        best_match = None
        best_score = 0.0

        for link in song_links:
            candidate = link.get("title")
            if candidate:
                score = similarity(title, candidate)
                if score > best_score:
                    best_score = score
                    best_match = link

        if not best_match or best_score < 0.6:
            return jsonify({
                'success': False,
                'message': 'Música não encontrada ou muito diferente do título fornecido'
            }), 404

        lyrics_url = "https://www.letras.com" + best_match["href"]
        lyrics_response = session.get(lyrics_url)

        if lyrics_response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Erro ao acessar a página da música'
            }), 500

        lyrics_soup = BeautifulSoup(lyrics_response.text, "html.parser")
        lyrics_div = lyrics_soup.find("div", class_="lyric-original")

        if not lyrics_div:
            return jsonify({
                'success': False,
                'message': 'Letra não encontrada'
            }), 404

        lyrics = clean_lyrics(lyrics_div.get_text(separator="\n", strip=True))

        if not lyrics.strip():
            return jsonify({
                'success': False,
                'message': 'Letra encontrada, mas está vazia'
            }), 404

        return jsonify({
            'success': True,
            'lyrics': lyrics,
            'title': best_match.get('title'),
            'artist': artist,
            'similarity_score': best_score,
            'message': 'Letra encontrada com sucesso'
        })

    except requests.exceptions.SSLError as e:
        app.logger.error(f"SSL Error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Erro de segurança na conexão'
        }), 502
    except Exception as e:
        app.logger.error(f"Error fetching lyrics: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro inesperado: {str(e)}'
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'ssl_verified': True,
        'version': '1.0.0'
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    