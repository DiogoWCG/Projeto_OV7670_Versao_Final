// Geracao do XCLK da OV7670 para Arduino-ESP32 2.x e 3.x.
// Baseado no projeto ESP32CameraI2S de bitluni.

#include "XClk.h"
#include "driver/ledc.h"
#include "driver/periph_ctrl.h"

bool ClockEnable(int pin, int Hz)
{
    periph_module_enable(PERIPH_LEDC_MODULE);

    ledc_timer_config_t timer_conf = {};
    timer_conf.duty_resolution = LEDC_TIMER_1_BIT;
    timer_conf.freq_hz = Hz;
    timer_conf.speed_mode = LEDC_HIGH_SPEED_MODE;
    timer_conf.timer_num = LEDC_TIMER_0;
    timer_conf.clk_cfg = LEDC_AUTO_CLK;

    esp_err_t err = ledc_timer_config(&timer_conf);
    if (err != ESP_OK) {
        return false;
    }

    ledc_channel_config_t ch_conf = {};
    ch_conf.channel = LEDC_CHANNEL_0;
    ch_conf.timer_sel = LEDC_TIMER_0;
    ch_conf.intr_type = LEDC_INTR_DISABLE;
    ch_conf.duty = 1;
    ch_conf.speed_mode = LEDC_HIGH_SPEED_MODE;
    ch_conf.gpio_num = pin;
    ch_conf.hpoint = 0;

    err = ledc_channel_config(&ch_conf);
    return err == ESP_OK;
}

void ClockDisable()
{
    periph_module_disable(PERIPH_LEDC_MODULE);
}

