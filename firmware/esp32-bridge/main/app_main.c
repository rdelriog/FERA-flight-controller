#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/uart.h"
#include "nvs_flash.h"

static const char *TAG = "companion";

static void uart_bridge_task(void *arg) {
  const int uart_num = UART_NUM_1;
  uart_config_t cfg = {
    .baud_rate = 921600,
    .data_bits = UART_DATA_8_BITS,
    .parity    = UART_PARITY_DISABLE,
    .stop_bits = UART_STOP_BITS_1,
    .flow_ctrl = UART_HW_FLOWCTRL_DISABLE
  };
  uart_param_config(uart_num, &cfg);
  uart_set_pin(uart_num, 17, 16, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
  uart_driver_install(uart_num, 4096, 4096, 0, NULL, 0);

  uint8_t buf[512];
  while (1) {
    int n = uart_read_bytes(uart_num, buf, sizeof(buf), pdMS_TO_TICKS(10));
    if (n > 0) {
      ESP_LOGI(TAG, "UART %d bytes", n);
    }
  }
}

void app_main(void) {
  ESP_ERROR_CHECK(nvs_flash_init());
  ESP_LOGI(TAG, "Boot");
  xTaskCreate(uart_bridge_task, "uart_bridge", 4096, NULL, 5, NULL);
}
