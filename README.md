# Projeto OV7670 — Versão Final

Protótipo acadêmico de monitoramento com ESP32, câmera OV7670 sem FIFO,
sensor PIR, LED indicador, servidor local e integração com o Telegram.

Ao detectar presença, o sistema captura 15 imagens em 320 × 240, envia os
quadros ao notebook, gera um vídeo MP4 de 5 segundos e o entrega pelo Telegram.
O usuário também pode descartar a gravação por um botão no próprio bot.

## Funcionalidades

- Detecção de presença com sensor PIR.
- Captura de imagens pela OV7670 sem FIFO.
- LED aceso somente durante a captura e o envio das 15 fotos.
- Criação automática de vídeo MP4 no notebook.
- Envio do vídeo para o Telegram.
- Botão **Descartar gravação** enviado no começo do evento.
- Exclusão do vídeo do Telegram e do notebook quando descartado.
- Rearme automático após o PIR voltar para `LOW` e a câmera descansar 10 segundos.
- Vários eventos sem reiniciar o ESP32.
- Credenciais privadas fora do código-fonte.

## Componentes

- ESP32 DOIT DevKit V1.
- Câmera OV7670 VGA 640 × 480 sem FIFO, utilizada em 320 × 240.
- Sensor PIR de presença.
- LED.
- Resistor de 220 Ω a 1 kΩ.
- Protoboard e cabos jumper.
- Notebook com Python 3.

## Ligações

### OV7670 → ESP32

| OV7670 | ESP32 |
| --- | ---: |
| 3.3V | 3V3 |
| GND | GND |
| SDA / SIOD | GPIO 21 |
| SCL / SIOC | GPIO 22 |
| VS | GPIO 25 |
| HS | GPIO 26 |
| XLK / XCLK | GPIO 32 |
| PLK / PCLK | GPIO 27 |
| D0 | GPIO 5 |
| D1 | GPIO 18 |
| D2 | GPIO 19 |
| D3 | GPIO 23 |
| D4 | GPIO 34 |
| D5 | GPIO 35 |
| D6 | GPIO 36 |
| D7 | GPIO 39 |
| RET / RESET | GPIO 4 |
| PWDN | GPIO 13 |

### PIR e LED

| Componente | ESP32 |
| --- | ---: |
| PIR OUT | GPIO 33 |
| PIR VCC | VIN (5 V) |
| PIR GND | GND comum |
| LED — perna longa | GPIO 14 |
| LED — perna curta | Resistor e GND comum |

## Estrutura

```text
Projeto_OV7670_Versao_Final/
├── esp32/
│   └── OV7670_Versao_Final/
│       ├── OV7670_Versao_Final.ino
│       ├── Credenciais.h.example
│       └── arquivos do controlador da OV7670
└── servidor/
    ├── iniciar_servidor.bat
    ├── preparar_arduino.py
    ├── servidor.py
    ├── requirements.txt
    └── .env.example
```

## Configuração

### 1. Preparar o servidor

1. Instale o Python 3. Durante a instalação, marque **Add Python to PATH**.
2. Abra a pasta `servidor`.
3. Execute `iniciar_servidor.bat`.
4. Na primeira execução, será criado e aberto o arquivo `.env`.
5. Preencha:

```env
BOT_TOKEN=TOKEN_DO_BOT
CHAT_ID=ID_DO_CHAT
WIFI_SSID=NOME_DO_WIFI
WIFI_PASSWORD=SENHA_DO_WIFI
IP_SERVIDOR=AUTO
```

6. Salve e feche o arquivo.
7. Se o Firewall do Windows perguntar, permita o acesso em redes privadas.

O script instala as dependências, descobre o IP do notebook e cria
`Credenciais.h` automaticamente na pasta do Arduino.

### 2. Programar o ESP32

1. Abra `esp32/OV7670_Versao_Final/OV7670_Versao_Final.ino`.
2. Selecione **DOIT ESP32 DEVKIT V1**.
3. Escolha a porta COM correta.
4. Envie o código para o ESP32.
5. Abra o Monitor Serial em `115200 baud`.

## Teste

1. Conecte o notebook e o ESP32 ao mesmo Wi-Fi.
2. Mantenha `iniciar_servidor.bat` aberto.
3. Aguarde os 30 segundos de estabilização do PIR.
4. Passe diante do sensor.
5. O LED acenderá depois da primeira foto capturada.
6. O LED apagará depois do envio da 15ª foto.
7. O servidor criará o MP4 e o enviará ao Telegram.
8. Para descartar, use o botão do aviso inicial ou o botão no vídeo.
9. Quando aparecer `Sistema rearmado`, outro movimento poderá gerar um novo vídeo.

## Funcionamento do descarte

- Se o botão não for pressionado, o vídeo é enviado normalmente.
- Se for pressionado durante a captura, as fotos são recebidas, mas o MP4 não é enviado.
- Se for pressionado no vídeo já entregue, o bot remove a mensagem e apaga o MP4 local.
- O servidor precisa permanecer aberto para processar os botões.

## Limitação conhecida

A câmera normalmente captura cada quadro em cerca de 40 a 80 ms. Entretanto,
o código envia uma foto antes de capturar a próxima. Portanto, um Wi-Fi lento
pode aumentar o intervalo entre as fotos e fazer a sequência levar mais de
5 segundos. O servidor ainda distribui os 15 quadros em um MP4 final de
5 segundos. Essa variação é da rede, não da captura da OV7670.

## Segurança

Os arquivos `.env` e `Credenciais.h` são ignorados pelo Git e não devem ser
publicados. O repositório contém somente os modelos `.env.example` e
`Credenciais.h.example`.

