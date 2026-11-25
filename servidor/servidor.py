import json
import os
import re
import shutil
import socket
import subprocess
import time
from threading import Lock, Thread
from pathlib import Path

import imageio_ffmpeg
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request


BASE = Path(__file__).resolve().parent
PASTA_EVENTOS = BASE / "eventos"
PASTA_VIDEOS = BASE / "videos"

PASTA_EVENTOS.mkdir(exist_ok=True)
PASTA_VIDEOS.mkdir(exist_ok=True)

load_dotenv(BASE / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

app = Flask(__name__)

# Estado compartilhado entre as rotas do ESP32 e o monitor dos botoes do
# Telegram. O Lock evita conflito quando um clique acontece durante o envio.
ESTADOS_EVENTOS = {}
LOCK_EVENTOS = Lock()


def telegram_configurado():
    return (
        BOT_TOKEN
        and CHAT_ID
        and "COLE_" not in BOT_TOKEN
        and "COLE_" not in CHAT_ID
    )


def id_evento_valido(evento):
    # O prefixo "descartar:" tambem ocupa espaco no callback_data do
    # Telegram, cujo limite total e 64 bytes.
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,48}", evento or ""))


def pasta_do_evento(evento):
    return PASTA_EVENTOS / evento


def video_do_evento(evento):
    return PASTA_VIDEOS / f"{evento}.mp4"


def teclado_descartar(evento):
    return {
        "inline_keyboard": [[
            {
                "text": "🗑️ Descartar gravação",
                "callback_data": f"descartar:{evento}",
            }
        ]]
    }


def chamar_telegram(metodo, dados, tempo_limite=30):
    if not telegram_configurado():
        return None

    try:
        resposta = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/{metodo}",
            json=dados,
            timeout=tempo_limite,
        )
    except requests.RequestException as erro:
        print(f"Falha ao acessar o Telegram em {metodo}: {erro}")
        return None

    try:
        conteudo = resposta.json()
    except ValueError:
        conteudo = {}

    if not resposta.ok or not conteudo.get("ok"):
        print(f"Erro do Telegram em {metodo}: {resposta.text}")
        return None

    return conteudo.get("result")


def registrar_evento(evento):
    with LOCK_EVENTOS:
        ESTADOS_EVENTOS[evento] = {
            "descartado": False,
            "finalizado": False,
            "aviso_message_id": None,
            "video_message_id": None,
        }


def evento_descartado(evento):
    with LOCK_EVENTOS:
        estado = ESTADOS_EVENTOS.get(evento)
        return bool(estado and estado["descartado"])


def salvar_aviso_message_id(evento, message_id):
    with LOCK_EVENTOS:
        estado = ESTADOS_EVENTOS.get(evento)

        if estado:
            estado["aviso_message_id"] = message_id


def enviar_aviso_descarte_em_segundo_plano(evento):
    def tarefa():
        resultado = chamar_telegram(
            "sendMessage",
            {
                "chat_id": CHAT_ID,
                "text": (
                    "🚨 Presença detectada! A captura começou.\n\n"
                    "Se não quiser guardar esta gravação, toque no botão. "
                    "Se não fizer nada, o vídeo será enviado normalmente."
                ),
                "reply_markup": teclado_descartar(evento),
            },
        )

        if isinstance(resultado, dict):
            salvar_aviso_message_id(evento, resultado.get("message_id"))

    Thread(target=tarefa, daemon=True).start()


def editar_aviso(evento, texto, manter_botao=False):
    with LOCK_EVENTOS:
        estado = ESTADOS_EVENTOS.get(evento)
        message_id = estado.get("aviso_message_id") if estado else None

    if not message_id:
        return False

    dados = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": texto,
        "reply_markup": (
            teclado_descartar(evento)
            if manter_botao
            else {"inline_keyboard": []}
        ),
    }

    return chamar_telegram("editMessageText", dados) is not None


def apagar_mensagem_telegram(message_id):
    if not message_id:
        return False

    resultado = chamar_telegram(
        "deleteMessage",
        {"chat_id": CHAT_ID, "message_id": message_id},
    )
    return resultado is True


def responder_callback(callback_id, texto, alerta=False):
    chamar_telegram(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id,
            "text": texto,
            "show_alert": alerta,
        },
    )


def remover_gravacao_local(evento):
    pasta = pasta_do_evento(evento)
    caminho_video = video_do_evento(evento)

    try:
        if pasta.exists():
            shutil.rmtree(pasta)

        if caminho_video.exists():
            caminho_video.unlink()
    except OSError as erro:
        print(f"Nao foi possivel apagar os arquivos de {evento}: {erro}")


def marcar_evento_descartado(evento, message_id_origem=None):
    with LOCK_EVENTOS:
        estado = ESTADOS_EVENTOS.get(evento)

        # Permite descartar um video antigo depois de reiniciar o servidor,
        # desde que o MP4 ainda exista no notebook.
        if not estado and video_do_evento(evento).exists():
            estado = {
                "descartado": True,
                "finalizado": True,
                "aviso_message_id": None,
                "video_message_id": message_id_origem,
            }
            ESTADOS_EVENTOS[evento] = estado

        if not estado:
            return None

        estado["descartado"] = True

        if message_id_origem and not estado["video_message_id"]:
            estado["video_message_id"] = message_id_origem

        return dict(estado)


def processar_callback(update):
    callback = update.get("callback_query") or {}
    callback_id = callback.get("id")
    dados = callback.get("data", "")
    mensagem = callback.get("message") or {}
    chat = mensagem.get("chat") or {}

    if not callback_id:
        return

    if str(chat.get("id", "")) != CHAT_ID:
        responder_callback(callback_id, "Este botão não pertence a este chat.", True)
        return

    if not dados.startswith("descartar:"):
        responder_callback(callback_id, "Comando desconhecido.", True)
        return

    evento = dados.split(":", 1)[1]

    if not id_evento_valido(evento):
        responder_callback(callback_id, "Identificador inválido.", True)
        return

    message_id_origem = mensagem.get("message_id")
    origem_e_video = "video" in mensagem
    estado = marcar_evento_descartado(
        evento,
        message_id_origem if origem_e_video else None,
    )

    if not estado:
        responder_callback(
            callback_id,
            "Esta gravação não está mais disponível.",
            True,
        )
        return

    removido_telegram = False

    if estado["finalizado"] and estado["video_message_id"]:
        removido_telegram = apagar_mensagem_telegram(
            estado["video_message_id"]
        )

    if estado["finalizado"]:
        remover_gravacao_local(evento)

    editar_aviso(
        evento,
        (
            "🗑️ Gravação descartada. O vídeo foi removido."
            if removido_telegram
            else "🗑️ Gravação marcada para descarte."
        ),
    )

    responder_callback(
        callback_id,
        (
            "Gravação descartada e vídeo removido."
            if removido_telegram
            else "Gravação marcada para descarte."
        ),
    )

    print(f"Evento descartado pelo Telegram: {evento}")


def monitorar_botoes_telegram():
    if not telegram_configurado():
        print("Telegram nao configurado; botoes de descarte desativados.")
        return

    # O projeto usa getUpdates. Remover um webhook antigo evita conflito com
    # o recebimento dos cliques nos botoes.
    chamar_telegram("deleteWebhook", {"drop_pending_updates": False})
    offset = None

    while True:
        dados = {
            "timeout": 25,
            "allowed_updates": ["callback_query"],
        }

        if offset is not None:
            dados["offset"] = offset

        atualizacoes = chamar_telegram("getUpdates", dados, 35)

        if atualizacoes is None:
            time.sleep(2)
            continue

        for update in atualizacoes:
            offset = max(offset or 0, update.get("update_id", 0) + 1)
            processar_callback(update)


def enviar_video(caminho, evento):
    if not telegram_configurado():
        print("Telegram nao configurado; video mantido no notebook.")
        return None

    with caminho.open("rb") as arquivo:
        resposta = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
            data={
                "chat_id": CHAT_ID,
                "caption": "Presenca detectada: video de 5 segundos.",
                "supports_streaming": "true",
                "reply_markup": json.dumps(teclado_descartar(evento)),
            },
            files={"video": (caminho.name, arquivo, "video/mp4")},
            timeout=120,
        )

    if not resposta.ok:
        print("Erro do Telegram:", resposta.text)
        return None

    try:
        conteudo = resposta.json()
        return conteudo["result"]["message_id"]
    except (KeyError, TypeError, ValueError):
        print("O Telegram enviou o video, mas nao retornou o message_id.")
        return None


def criar_mp4(pasta_evento, caminho_video, duracao):
    quadros = sorted(pasta_evento.glob("quadro_*.bmp"))

    if len(quadros) < 2:
        raise RuntimeError("Sao necessarias pelo menos duas fotos.")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    entrada = str(pasta_evento / "quadro_%03d.bmp")
    fps_entrada = len(quadros) / duracao

    comando = [
        ffmpeg,
        "-y",
        "-framerate",
        str(fps_entrada),
        "-i",
        entrada,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-r",
        "10",
        str(caminho_video),
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if resultado.returncode != 0:
        print(resultado.stderr)
        raise RuntimeError("O FFmpeg nao conseguiu criar o MP4.")


@app.get("/")
def pagina_inicial():
    return jsonify(
        status="online",
        mensagem="Servidor OV7670 pronto para receber fotos.",
    )


@app.post("/iniciar")
def iniciar_evento():
    evento = request.args.get("evento", "")

    if not id_evento_valido(evento):
        return jsonify(erro="Identificador de evento invalido."), 400

    pasta = pasta_do_evento(evento)

    if pasta.exists():
        shutil.rmtree(pasta)

    pasta.mkdir(parents=True)

    print(f"Evento iniciado: {evento}")
    registrar_evento(evento)
    enviar_aviso_descarte_em_segundo_plano(evento)

    return jsonify(ok=True, evento=evento), 201


@app.post("/quadro")
def receber_quadro():
    evento = request.args.get("evento", "")

    if not id_evento_valido(evento):
        return jsonify(erro="Identificador de evento invalido."), 400

    pasta = pasta_do_evento(evento)

    if not pasta.is_dir():
        return jsonify(erro="O evento ainda nao foi iniciado."), 404

    dados = request.get_data(cache=False)

    if len(dados) < 1000 or dados[:2] != b"BM":
        return jsonify(erro="O arquivo recebido nao e um BMP valido."), 400

    # A numeracao e feita pelo servidor para nao deixar lacunas caso
    # uma tentativa de envio anterior tenha falhado.
    numero = len(list(pasta.glob("quadro_*.bmp")))
    destino = pasta / f"quadro_{numero:03d}.bmp"
    destino.write_bytes(dados)

    print(f"{evento}: quadro {numero:03d} recebido ({len(dados)} bytes)")

    return jsonify(ok=True, quadro=numero, bytes=len(dados)), 201


def ler_exatamente(fonte, quantidade):
    partes = []
    recebido = 0

    while recebido < quantidade:
        parte = fonte.read(quantidade - recebido)

        if not parte:
            break

        partes.append(parte)
        recebido += len(parte)

    return b"".join(partes)


@app.post("/sequencia")
def receber_sequencia():
    evento = request.args.get("evento", "")

    if not id_evento_valido(evento):
        return jsonify(erro="Identificador de evento invalido."), 400

    pasta = pasta_do_evento(evento)

    if not pasta.is_dir():
        return jsonify(erro="O evento ainda nao foi iniciado."), 404

    try:
        quantidade = int(request.args.get("quantidade", "0"))
        tamanho = int(request.args.get("tamanho", "0"))
    except ValueError:
        return jsonify(erro="Quantidade ou tamanho invalido."), 400

    if not 1 <= quantidade <= 60:
        return jsonify(erro="Quantidade fora do limite."), 400

    if not 1000 <= tamanho <= 200000:
        return jsonify(erro="Tamanho de quadro fora do limite."), 400

    tamanho_esperado = quantidade * tamanho

    if request.content_length != tamanho_esperado:
        return jsonify(
            erro="Content-Length diferente do tamanho esperado.",
            esperado=tamanho_esperado,
            recebido=request.content_length,
        ), 400

    recebidos = 0

    for numero in range(quantidade):
        dados = ler_exatamente(request.stream, tamanho)

        if len(dados) != tamanho:
            return jsonify(
                erro="A conexao terminou antes do fim da sequencia.",
                quadros=recebidos,
                bytes_ultimo_quadro=len(dados),
            ), 400

        if dados[:2] != b"BM":
            return jsonify(
                erro="Foi recebido um quadro que nao e BMP.",
                quadro=numero,
            ), 400

        destino = pasta / f"quadro_{numero:03d}.bmp"
        destino.write_bytes(dados)
        recebidos += 1

        print(
            f"{evento}: quadro {numero:03d} recebido "
            f"({len(dados)} bytes)"
        )

    print(f"{evento}: sequencia completa com {recebidos} quadros")

    return jsonify(ok=True, quadros=recebidos), 201


@app.post("/finalizar")
def finalizar_evento():
    evento = request.args.get("evento", "")

    if not id_evento_valido(evento):
        return jsonify(erro="Identificador de evento invalido."), 400

    try:
        duracao = int(request.args.get("duracao", "5"))
    except ValueError:
        return jsonify(erro="Duracao invalida."), 400

    duracao = max(1, min(duracao, 15))
    pasta = pasta_do_evento(evento)

    if not pasta.is_dir():
        return jsonify(erro="Evento nao encontrado."), 404

    caminho_video = video_do_evento(evento)
    quantidade = len(list(pasta.glob("quadro_*.bmp")))

    if evento_descartado(evento):
        remover_gravacao_local(evento)

        with LOCK_EVENTOS:
            ESTADOS_EVENTOS[evento]["finalizado"] = True

        editar_aviso(evento, "🗑️ Gravação descartada antes do envio.")
        print(f"Evento descartado antes de criar o MP4: {evento}")

        return jsonify(
            ok=True,
            evento=evento,
            quadros=quantidade,
            descartado=True,
            telegram=False,
        )

    try:
        criar_mp4(pasta, caminho_video, duracao)
    except Exception as erro:
        return jsonify(erro=str(erro)), 500

    if evento_descartado(evento):
        remover_gravacao_local(evento)

        with LOCK_EVENTOS:
            ESTADOS_EVENTOS[evento]["finalizado"] = True

        editar_aviso(evento, "🗑️ Gravação descartada antes do envio.")
        print(f"Evento descartado antes de enviar o MP4: {evento}")

        return jsonify(
            ok=True,
            evento=evento,
            quadros=quantidade,
            descartado=True,
            telegram=False,
        )

    video_message_id = enviar_video(caminho_video, evento)

    with LOCK_EVENTOS:
        estado = ESTADOS_EVENTOS[evento]
        estado["video_message_id"] = video_message_id
        estado["finalizado"] = True
        descartado_durante_envio = estado["descartado"]

    telegram_enviado = video_message_id is not None

    if descartado_durante_envio:
        if video_message_id:
            apagar_mensagem_telegram(video_message_id)

        remover_gravacao_local(evento)
        editar_aviso(evento, "🗑️ Gravação descartada e vídeo removido.")
        print(f"Evento descartado durante o envio: {evento}")

        return jsonify(
            ok=True,
            evento=evento,
            quadros=quantidade,
            descartado=True,
            telegram=False,
        )

    # O MP4 permanece na pasta videos; as fotos temporarias sao removidas.
    shutil.rmtree(pasta)

    editar_aviso(
        evento,
        (
            "✅ Vídeo enviado. Para apagá-lo do Telegram e do notebook, "
            "use o botão abaixo do próprio vídeo."
            if telegram_enviado
            else (
                "⚠️ O vídeo foi criado no notebook, mas não chegou ao "
                "Telegram. Você ainda pode descartá-lo pelo botão."
            )
        ),
        manter_botao=not telegram_enviado,
    )

    # Cobre o caso raro de o clique acontecer ao mesmo tempo que a mensagem
    # acima e garante que o estado final mostrado seja o de descarte.
    if evento_descartado(evento):
        if video_message_id:
            apagar_mensagem_telegram(video_message_id)

        remover_gravacao_local(evento)
        editar_aviso(evento, "🗑️ Gravação descartada e vídeo removido.")
        telegram_enviado = False

    print(f"Video criado: {caminho_video}")

    return jsonify(
        ok=True,
        evento=evento,
        quadros=quantidade,
        video=str(caminho_video),
        telegram=telegram_enviado,
        descartado=evento_descartado(evento),
    )


def descobrir_ip_local():
    conexao = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        conexao.connect(("8.8.8.8", 80))
        return conexao.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        conexao.close()


if __name__ == "__main__":
    ip = descobrir_ip_local()

    Thread(target=monitorar_botoes_telegram, daemon=True).start()

    print()
    print("==============================================")
    print(" SERVIDOR OV7670 - VERSAO FINAL")
    print(f" Endereco para testar: http://{ip}:5000")
    print(f" Coloque no codigo do ESP32: {ip}")
    print("==============================================")
    print()

    app.run(host="0.0.0.0", port=5000, threaded=True)
