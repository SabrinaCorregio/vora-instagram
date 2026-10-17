"""Publica no Instagram o PRIMEIRO post da fila (ordem alfabetica das pastas em fila/).

Estrutura de cada pasta (nomeie como 01, 02, 03... para definir a ordem):
  fila/01/legenda.txt
  fila/01/1.jpg            -> 1 imagem  = post de imagem
  fila/02/video.mp4        -> 1 video   = Reels
  fila/03/1.jpg, 2.jpg ... -> 2+ arquivos = carrossel (ordem alfabetica)

Roda uma vez por dia: publica uma pasta e a move para postados/.
"""
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

API = "https://graph.instagram.com/v25.0"  # Instagram API com login do Instagram
IG_USER_ID = os.environ.get("IG_USER_ID") or "me"  # "me" = a conta dona do token
TOKEN = os.environ["IG_ACCESS_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

IMAGENS = {".jpg", ".jpeg", ".png"}
VIDEOS = {".mp4", ".mov"}


def chamar(metodo, caminho, **params):
    params["access_token"] = TOKEN
    r = requests.request(metodo, f"{API}/{caminho}", params=params, timeout=60)
    if not r.ok:
        sys.exit(f"Erro da API ({r.status_code}): {r.text}")
    return r.json()


def url_publica(pasta: Path, arquivo: Path) -> str:
    return (
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"
        f"{quote(pasta.parent.name)}/{quote(pasta.name)}/{quote(arquivo.name)}"
    )


def esperar_processamento(container_id: str):
    for _ in range(60):  # ate ~10 min
        status = chamar("GET", container_id, fields="status_code,status")
        codigo = status.get("status_code")
        if codigo == "FINISHED":
            return
        if codigo in ("ERROR", "EXPIRED"):
            sys.exit(f"Falha no processamento da midia: {status}")
        time.sleep(10)
    sys.exit("Tempo esgotado esperando o Instagram processar a midia.")


def criar_container(pasta: Path, arquivo: Path, legenda: str, item_carrossel=False):
    url = url_publica(pasta, arquivo)
    ext = arquivo.suffix.lower()
    params = {}
    if ext in VIDEOS:
        if item_carrossel:
            params.update(media_type="VIDEO", video_url=url)
        else:
            params.update(media_type="REELS", video_url=url)
    else:
        params["image_url"] = url
    if item_carrossel:
        params["is_carousel_item"] = "true"
    else:
        params["caption"] = legenda
    container = chamar("POST", f"{IG_USER_ID}/media", **params)["id"]
    if ext in VIDEOS:
        esperar_processamento(container)
    return container


def main():
    fila = Path("fila")
    pastas = sorted(p for p in fila.iterdir() if p.is_dir()) if fila.is_dir() else []
    if not pastas:
        print("Fila vazia. Nada a publicar hoje.")
        return
    pasta = pastas[0]
    print(f"Publicando: {pasta.name} (restam {len(pastas) - 1} depois deste)")

    legenda_path = pasta / "legenda.txt"
    legenda = legenda_path.read_text(encoding="utf-8").strip() if legenda_path.exists() else ""
    midias = sorted(p for p in pasta.iterdir() if p.suffix.lower() in IMAGENS | VIDEOS)
    if not midias:
        sys.exit(f"A pasta {pasta} nao tem imagens nem videos.")

    if len(midias) == 1:
        container = criar_container(pasta, midias[0], legenda)
    else:
        if len(midias) > 10:
            sys.exit("Carrossel aceita no maximo 10 itens.")
        filhos = [criar_container(pasta, m, legenda, item_carrossel=True) for m in midias]
        container = chamar(
            "POST", f"{IG_USER_ID}/media",
            media_type="CAROUSEL", children=",".join(filhos), caption=legenda,
        )["id"]
        esperar_processamento(container)

    post = chamar("POST", f"{IG_USER_ID}/media_publish", creation_id=container)
    print(f"Publicado! ID do post: {post['id']}")

    destino = Path("postados") / pasta.name
    destino.parent.mkdir(exist_ok=True)
    if destino.exists():
        destino = Path("postados") / f"{pasta.name}-{int(time.time())}"
    shutil.move(str(pasta), str(destino))


if __name__ == "__main__":
    main()
