# 🎵 API de Letras de Músicas - Letras.com (com sessão segura)

Esta API permite buscar letras de músicas no site [letras.com](https://www.letras.com), utilizando scraping com `requests` e `BeautifulSoup`, com melhorias de segurança para conexões HTTPS via `SSLAdapter`.

## 🚀 Funcionalidades

- 🔍 Busca de letras por **título** e **artista**
- 🔒 Sessão HTTPS com adaptação SSL personalizada
- 🧠 Algoritmo de similaridade para encontrar a melhor correspondência
- 🚫 Remoção de HTML e limpeza do texto
- ⚡ Cache de resultados com validade de 1 hora
- 🩺 Endpoint de saúde com verificação de versão e SSL

## 📦 Requisitos

- Python 3.7 ou superior

## 📥 Instalação

```bash
git clone https://github.com/seu-usuario/seu-repo.git
cd seu-repo
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

**Dependências necessárias** (incluir no `requirements.txt`):

```
Flask
Flask-Caching
requests
beautifulsoup4
urllib3
```

## ▶️ Execução

```bash
python app.py
```

A API ficará disponível em:

```
http://localhost:5000
```

## 🔗 Endpoints

### `GET /api/lyrics`

Busca uma letra com base no título e no nome do artista.

#### Parâmetros:

- `title` (obrigatório): título da música
- `artist` (obrigatório): nome do artista

#### Exemplo de uso:

```bash
curl "http://localhost:5000/api/lyrics?title=Palpite&artist=Vanessa%20Rangel"
```

#### Resposta esperada:

```json
{
  "success": true,
  "lyrics": "Palpite
Eu espero...",
  "title": "Palpite",
  "artist": "Vanessa Rangel",
  "similarity_score": 0.93,
  "message": "Letra encontrada com sucesso"
}
```

#### Códigos de erro:

- `400`: parâmetros ausentes
- `404`: música/artista não encontrados
- `502`: erro de SSL
- `500`: erro interno inesperado

---

### `GET /health`

Verifica se a API está funcionando corretamente.

#### Resposta:

```json
{
  "status": "healthy",
  "ssl_verified": true,
  "version": "1.0.0"
}
```

## ⚠️ Segurança

- O código utiliza um adaptador SSL para garantir conexões seguras sem desativar verificações (diferente da versão anterior).
- Evite uso em larga escala sem respeitar os termos de uso do letras.com.

## 🧠 Como funciona a busca

A API coleta os links de músicas listadas para um artista e compara seus títulos com o título informado, usando `difflib.SequenceMatcher` para calcular similaridade e selecionar a melhor opção.

## 📄 Licença

MIT

---

Desenvolvido por **Alexandre Marques** 🚀
