#pragma once

//assuming pixel lines have multiples of 4 bytes sizes
class BMP
{

  static void setChar(void *buffer, int pos, char ch)
  {
    *(char*)(buffer+pos) = ch;
  }

  static void setLong(void *buffer, int pos, long l)
  {
    *(long*)(buffer+pos) = l;
  }
  
  static void setShort(void *buffer, int pos, short s)
  {
    *(short*)(buffer+pos) = s;
  }
  
public:  
  // Cabecalho BMP + paleta RGB332 com 256 cores.
  static const int headerSize = 54 + (256 * 4);
  
  static void construct8BitHeader(void *buffer, long xres, long yres)
  {
    setChar(buffer, 0, 'B');
    setChar(buffer, 1, 'M');

    // Cada linha do BMP precisa terminar em multiplo de 4 bytes.
    long bytesPerLine = (xres + 3) & ~3;
    setLong(buffer, 2, bytesPerLine * yres + headerSize);
    setLong(buffer, 6, 0);
    
    setLong(buffer, 10, headerSize);

    setLong(buffer, 14, 40);
    setLong(buffer, 18, xres);
    setLong(buffer, 22, yres);
    setShort(buffer, 26, 1);
    setShort(buffer, 28, 8);

    setLong(buffer, 30, 0);
    setLong(buffer, 34, bytesPerLine * yres);
    setLong(buffer, 38, 0);
    setLong(buffer, 42, 0);

    setLong(buffer, 46, 256);
    setLong(buffer, 50, 256);

    // Paleta: indice RRR-GGG-BB -> entrada BGRA do BMP.
    for (int i = 0; i < 256; i++)
    {
      const int vermelho = ((i >> 5) & 0x07) * 255 / 7;
      const int verde = ((i >> 2) & 0x07) * 255 / 7;
      const int azul = (i & 0x03) * 255 / 3;
      const int pos = 54 + i * 4;

      setChar(buffer, pos + 0, azul);
      setChar(buffer, pos + 1, verde);
      setChar(buffer, pos + 2, vermelho);
      setChar(buffer, pos + 3, 0);
    }
  }
};


