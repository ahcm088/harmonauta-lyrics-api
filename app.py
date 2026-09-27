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

        # letras.com passou a bloquear scraping (retorna 403 Access Denied
        # mesmo com User-Agent de navegador). letras.com.br é um domínio
        # diferente (empresa diferente) que responde normalmente.
        artist_url = f"https://www.letras.com.br/{artist_slug}/"

        try:
            response = session.get(artist_url)
        except requests.exceptions.SSLError as e:
            app.logger.warning(f"SSL Error for {artist_url}: {str(e)}")
            response = None
        except requests.RequestException:
            response = None

        if not response or response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Artista não encontrado no letras.com.br'
            }), 404

        # No letras.com.br as músicas do artista aparecem como links
        # <a href="https://www.letras.com.br/{artista}/{slug-da-musica}">
        # direto no HTML (sem atributo title, diferente do letras.com).
        soup = BeautifulSoup(response.text, "html.parser")
        song_link_pattern = re.compile(
            rf"^https://www\.letras\.com\.br/{re.escape(artist_slug)}/([a-z0-9-]+)$"
        )
        non_song_slugs = {"discografia", "biografia", "curiosidades", "contribuicao", "traducao"}

        song_slugs = set()
        for link in soup.find_all("a", href=True):
            href = link["href"].split("#")[0].rstrip("/")
            match = song_link_pattern.match(href)
            if match and match.group(1) not in non_song_slugs:
                song_slugs.add(match.group(1))

        if not song_slugs:
            return jsonify({
                'success': False,
                'message': 'Nenhuma música encontrada para esse artista'
            }), 404

        # Compara o título pedido com os slugs disponíveis por similaridade
        def similarity(a, b):
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

        title_slug = sanitize_slug(title)
        best_slug, best_score = None, 0.0

        for slug in song_slugs:
            score = similarity(title_slug, slug)
            if score > best_score:
                best_score, best_slug = score, slug

        if not best_slug or best_score < 0.6:
            return jsonify({
                'success': False,
                'message': 'Música não encontrada ou muito diferente do título fornecido'
            }), 404

        lyrics_url = f"https://www.letras.com.br/{artist_slug}/{best_slug}"
        lyrics_response = session.get(lyrics_url)

        if lyrics_response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Erro ao acessar a página da música'
            }), 500

        # A letra fica em <section class="lyrics-section"><p>...<br>...</p></section>
        lyrics_soup = BeautifulSoup(lyrics_response.text, "html.parser")
        lyrics_section = lyrics_soup.find("section", class_="lyrics-section")

        if not lyrics_section:
            return jsonify({
                'success': False,
                'message': 'Letra não encontrada'
            }), 404

        for br in lyrics_section.find_all("br"):
            br.replace_with("\n")

        lyrics = clean_lyrics(lyrics_section.get_text())

        if not lyrics.strip():
            return jsonify({
                'success': False,
                'message': 'Letra encontrada, mas está vazia'
            }), 404

        return jsonify({
            'success': True,
            'lyrics': lyrics,
            'title': best_slug.replace('-', ' ').title(),
            'artist': artist,
            'similarity_score': round(best_score, 2),
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