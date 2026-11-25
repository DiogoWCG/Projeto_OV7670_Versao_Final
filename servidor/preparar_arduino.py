import os
import socket
from pathlib import Path

from dotenv import load_dotenv


BASE = Path(__file__).resolve().parent
ARQUIVO_ENV = BASE / ".env"
PASTA_ARDUINO = (
    BASE.parent / "esp32" / "OV7670_Versao_Final"
)
ARQUIVO_CREDENCIAIS = PASTA_ARDUINO / "Credenciais.h"


def descobrir_ip_local():
    conexao = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        conexao.connect(("8.8.8.8", 80))
        return conexao.getsockname()[0]
    except OSError:
        return ""
    finally:
        conexao.close()


def escapar_cpp(texto):
    return texto.replace("\\", "\\\\").replace('"', '\\"')


def valor_obrigatorio(nome):
    valor = os.getenv(nome, "").strip()

    if not valor or "COLE_" in valor:
        raise ValueError(f"Preencha {nome} no arquivo .env.")

    return valor


def main():
    load_dotenv(ARQUIVO_ENV, override=True)

    ssid = valor_obrigatorio("WIFI_SSID")
    senha = valor_obrigatorio("WIFI_PASSWORD")
    ip = os.getenv("IP_SERVIDOR", "AUTO").strip()

    if not ip or ip.upper() == "AUTO":
        ip = descobrir_ip_local()

    if not ip:
        raise ValueError(
            "Nao foi possivel descobrir o IP. Preencha IP_SERVIDOR no .env."
        )

    conteudo = f'''#pragma once

// Gerado automaticamente a partir de servidor/.env.
const char *WIFI_SSID = "{escapar_cpp(ssid)}";
const char *WIFI_PASSWORD = "{escapar_cpp(senha)}";
const char *IP_SERVIDOR = "{escapar_cpp(ip)}";
'''

    ARQUIVO_CREDENCIAIS.write_text(conteudo, encoding="utf-8")

    print()
    print("Credenciais.h gerado com sucesso.")
    print(f"IP do servidor colocado no Arduino: {ip}")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print()
        print("ERRO AO PREPARAR O ARDUINO:")
        print(erro)
        print()
        raise SystemExit(1)
