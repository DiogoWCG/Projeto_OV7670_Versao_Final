#include "OV7670.h"
#include "BMP.h"
#include "Credenciais.h"
#include <WiFi.h>

const uint16_t PORTA_SERVIDOR = 5000;

// Sensor PIR e LED. Estes pinos nao sao usados pela camera.
const int PINO_SENSOR = 33;
const int PINO_LED = 14;

// Depois de cada evento, a camera descansa por este intervalo antes de o
// sistema aceitar uma nova presenca.
const unsigned long INTERVALO_REARME_CAMERA = 10000;

// Quinze fotos a tres quadros por segundo = video de cinco segundos.
const int QUANTIDADE_FOTOS = 15;
const int FPS_CAPTURA = 3;
const int DURACAO_VIDEO_SEGUNDOS = 5;
const unsigned long INTERVALO_FOTOS = 1000 / FPS_CAPTURA;

bool aguardandoRearme = false;
unsigned long inicioDoRearme = 0;

// OV7670: ligacao que ja foi testada no circuito.
const int SIOD  = 21;
const int SIOC  = 22;
const int VSYNC = 25;
const int HREF  = 26;
const int XCLK  = 32;
const int PCLK  = 27;

const int D0 = 5;
const int D1 = 18;
const int D2 = 19;
const int D3 = 23;
const int D4 = 34;
const int D5 = 35;
const int D6 = 36;
const int D7 = 39;

const int RESET_CAMERA = 4;
const int PWDN_CAMERA  = 13;

OV7670 *camera = nullptr;
unsigned char cabecalhoBMP[BMP::headerSize];

bool conectarWiFi(unsigned long tempoLimite)
{
  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleep(false);
    return true;
  }

  Serial.print("Conectando ao Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  const unsigned long inicio = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - inicio < tempoLimite
  ) {
    Serial.print(".");
    delay(500);
  }

  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Falha ao conectar ao Wi-Fi.");
    return false;
  }

  Serial.print("Wi-Fi conectado. IP do ESP32: ");
  Serial.println(WiFi.localIP());
  WiFi.setSleep(false);
  return true;
}

bool receberRespostaHTTP(
  WiFiClient &cliente,
  unsigned long tempoLimite
)
{
  const unsigned long inicio = millis();

  while (!cliente.available()) {
    if (!cliente.connected()) {
      return false;
    }

    if (millis() - inicio >= tempoLimite) {
      Serial.println("Tempo de resposta do servidor esgotado.");
      cliente.stop();
      return false;
    }

    delay(10);
  }

  String status = cliente.readStringUntil('\n');
  const bool sucesso =
    status.indexOf(" 200 ") >= 0 ||
    status.indexOf(" 201 ") >= 0;

  // A primeira linha ja informa se o servidor aceitou o quadro.
  // Nao esperamos a conexao fechar, pois isso atrasava cada foto.
  cliente.stop();
  return sucesso;
}

bool enviarTodosOsBytes(
  WiFiClient &cliente,
  const uint8_t *dados,
  size_t tamanho,
  unsigned long tempoLimite
)
{
  size_t totalEnviado = 0;
  unsigned long ultimoProgresso = millis();

  while (totalEnviado < tamanho) {
    if (!cliente.connected()) {
      return false;
    }

    size_t restante = tamanho - totalEnviado;
    size_t bloco = restante > 4096 ? 4096 : restante;
    size_t enviado = cliente.write(dados + totalEnviado, bloco);

    if (enviado > 0) {
      totalEnviado += enviado;
      ultimoProgresso = millis();
    } else {
      if (millis() - ultimoProgresso >= tempoLimite) {
        return false;
      }

      delay(1);
    }
  }

  return true;
}

bool enviarComandoServidor(
  const String &rota,
  unsigned long tempoLimite
)
{
  WiFiClient cliente;
  cliente.setTimeout(tempoLimite);

  if (!cliente.connect(IP_SERVIDOR, PORTA_SERVIDOR)) {
    Serial.println("Nao foi possivel acessar o servidor.");
    return false;
  }

  cliente.print("POST ");
  cliente.print(rota);
  cliente.println(" HTTP/1.1");
  cliente.print("Host: ");
  cliente.println(IP_SERVIDOR);
  cliente.println("Content-Length: 0");
  cliente.println("Connection: close");
  cliente.println();

  return receberRespostaHTTP(cliente, tempoLimite);
}

int enviarSequenciaServidor(const String &evento)
{
  // O LED somente acendera quando a primeira foto realmente for capturada.
  digitalWrite(PINO_LED, LOW);

  WiFiClient cliente;
  cliente.setTimeout(30000);
  cliente.setNoDelay(true);

  if (!cliente.connect(IP_SERVIDOR, PORTA_SERVIDOR)) {
    Serial.println("Nao foi possivel acessar o servidor.");
    return 0;
  }

  const int tamanhoPixels = camera->xres * camera->yres;
  const int tamanhoFoto = BMP::headerSize + tamanhoPixels;
  const uint32_t tamanhoTotal =
    (uint32_t)tamanhoFoto * QUANTIDADE_FOTOS;

  String rota =
    "/sequencia?evento=" + evento +
    "&quantidade=" + String(QUANTIDADE_FOTOS) +
    "&tamanho=" + String(tamanhoFoto);

  cliente.print("POST ");
  cliente.print(rota);
  cliente.println(" HTTP/1.1");
  cliente.print("Host: ");
  cliente.println(IP_SERVIDOR);
  cliente.println("Content-Type: image/bmp");
  cliente.print("Content-Length: ");
  cliente.println(tamanhoTotal);
  cliente.println("Connection: close");
  cliente.println();

  int fotosEnviadas = 0;
  unsigned long proximoQuadro = millis();

  for (int indice = 0; indice < QUANTIDADE_FOTOS; indice++) {
    const unsigned long inicioCaptura = millis();

    Serial.printf(
      "Capturando foto %d de %d...\n",
      indice + 1,
      QUANTIDADE_FOTOS
    );

    camera->oneFrame();

    if (indice == 0) {
      digitalWrite(PINO_LED, HIGH);
      Serial.println(
        "Primeira foto capturada. Camera respondeu e LED aceso."
      );
    }

    const unsigned long tempoCaptura = millis() - inicioCaptura;
    const unsigned long inicioEnvio = millis();

    const bool cabecalhoEnviado = enviarTodosOsBytes(
      cliente,
      cabecalhoBMP,
      BMP::headerSize,
      15000
    );

    const bool pixelsEnviados = enviarTodosOsBytes(
      cliente,
      camera->frame,
      tamanhoPixels,
      15000
    );

    const unsigned long tempoEnvio = millis() - inicioEnvio;

    if (!cabecalhoEnviado || !pixelsEnviados) {
      Serial.printf(
        "Falha na foto %d | captura: %lu ms | envio: %lu ms\n",
        indice + 1,
        tempoCaptura,
        tempoEnvio
      );

      digitalWrite(PINO_LED, LOW);
      Serial.println("Captura interrompida. LED apagado.");
      cliente.stop();
      return fotosEnviadas;
    }

    fotosEnviadas++;

    Serial.printf(
      "Foto %d enviada | captura: %lu ms | envio: %lu ms\n",
      indice + 1,
      tempoCaptura,
      tempoEnvio
    );

    proximoQuadro += INTERVALO_FOTOS;

    const long espera = (long)(proximoQuadro - millis());

    if (espera > 0) {
      delay((unsigned long)espera);
    }
  }

  // As 15 fotos ja foram capturadas e enviadas. A criacao do MP4 e o envio
  // ao Telegram acontecem depois, com o LED apagado.
  digitalWrite(PINO_LED, LOW);
  Serial.println("Todas as fotos terminaram. LED apagado.");

  Serial.println("Sequencia enviada. Aguardando confirmacao do servidor...");

  if (!receberRespostaHTTP(cliente, 30000)) {
    Serial.println("O servidor nao confirmou a sequencia completa.");
    return 0;
  }

  return fotosEnviadas;
}

String criarIdEvento()
{
  const uint64_t chip = ESP.getEfuseMac();
  char id[48];

  snprintf(
    id,
    sizeof(id),
    "%08X%08X_%lu",
    (uint32_t)(chip >> 32),
    (uint32_t)chip,
    millis()
  );

  return String(id);
}

void capturarVideoCurto()
{
  digitalWrite(PINO_LED, LOW);

  if (!conectarWiFi(15000)) {
    return;
  }

  const String evento = criarIdEvento();
  const String rotaInicio = "/iniciar?evento=" + evento;

  Serial.println();
  Serial.print("Iniciando evento: ");
  Serial.println(evento);

  if (!enviarComandoServidor(rotaInicio, 15000)) {
    Serial.println("O servidor nao iniciou o evento.");
    return;
  }

  const unsigned long inicioSequencia = millis();
  const int fotosEnviadas = enviarSequenciaServidor(evento);
  const unsigned long tempoSequencia = millis() - inicioSequencia;

  // Garantia adicional: nenhum caminho de erro deixa o LED ligado.
  digitalWrite(PINO_LED, LOW);

  Serial.printf(
    "%d de %d fotos chegaram ao servidor em %.2f segundos.\n",
    fotosEnviadas,
    QUANTIDADE_FOTOS,
    tempoSequencia / 1000.0
  );

  if (fotosEnviadas < 2) {
    Serial.println("Nao ha fotos suficientes para criar o video.");
    return;
  }

  String rotaFinal =
    "/finalizar?evento=" + evento +
    "&duracao=" + String(DURACAO_VIDEO_SEGUNDOS);

  Serial.println("Solicitando a criacao do MP4...");

  if (enviarComandoServidor(rotaFinal, 120000)) {
    Serial.println("Servidor concluiu o processamento do evento.");
  } else {
    Serial.println("O servidor nao conseguiu finalizar o video.");
  }
}

void setup()
{
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("=== OV7670 - VERSAO FINAL ===");

  pinMode(PINO_SENSOR, INPUT);
  pinMode(PINO_LED, OUTPUT);
  digitalWrite(PINO_LED, LOW);

  pinMode(PWDN_CAMERA, OUTPUT);
  digitalWrite(PWDN_CAMERA, LOW);

  pinMode(RESET_CAMERA, OUTPUT);
  digitalWrite(RESET_CAMERA, LOW);
  delay(20);
  digitalWrite(RESET_CAMERA, HIGH);
  delay(100);

  Serial.println("Inicializando a camera...");

  camera = new OV7670(
    OV7670::Mode::QVGA_RGB565,
    SIOD,
    SIOC,
    VSYNC,
    HREF,
    XCLK,
    PCLK,
    D0,
    D1,
    D2,
    D3,
    D4,
    D5,
    D6,
    D7
  );

  if (camera == nullptr || camera->frame == nullptr) {
    Serial.println("Falha ao iniciar a camera.");

    while (true) {
      delay(1000);
    }
  }

  BMP::construct8BitHeader(
    cabecalhoBMP,
    camera->xres,
    camera->yres
  );

  Serial.printf(
    "Camera pronta: %dx%d, RGB332.\n",
    camera->xres,
    camera->yres
  );

  conectarWiFi(20000);

  Serial.println("Aguardando o sensor PIR estabilizar por 30 segundos...");
  delay(30000);
  Serial.println("Sistema pronto. Aguardando presenca.");
}

void loop()
{
  const bool detectouPresenca =
    digitalRead(PINO_SENSOR) == HIGH;

  if (aguardandoRearme) {
    const bool pirLiberado = !detectouPresenca;
    const bool intervaloConcluido =
      millis() - inicioDoRearme >= INTERVALO_REARME_CAMERA;

    // Um novo evento somente e liberado quando as duas condicoes forem
    // atendidas: o PIR voltou para LOW e a camera descansou 10 segundos.
    if (pirLiberado && intervaloConcluido) {
      aguardandoRearme = false;
      Serial.println("Sistema rearmado. Aguardando nova presenca.");
    }

    delay(50);
    return;
  }

  if (detectouPresenca) {
    // Bloqueia outros disparos enquanto este evento esta sendo processado.
    aguardandoRearme = true;

    Serial.println("Presenca detectada. Acionando a camera...");
    capturarVideoCurto();

    digitalWrite(PINO_LED, LOW);
    inicioDoRearme = millis();

    Serial.println("Evento finalizado. LED apagado.");
    Serial.printf(
      "Aguardando o PIR liberar e a camera descansar %lu segundos.\n",
      INTERVALO_REARME_CAMERA / 1000
    );
  }

  delay(50);
}
