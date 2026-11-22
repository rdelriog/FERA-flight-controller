/****************************************************************************
 *
 *   Copyright (c) 2026 PX4 Development Team. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in
 *    the documentation and/or other materials provided with the
 *    distribution.
 * 3. Neither the name PX4 nor the names of its contributors may be
 *    used to endorse or promote products derived from this software
 *    without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
 * OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
 * AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 * LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 * ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 ****************************************************************************/

/**
 * @file board_config.h
 *
 * FERA Core rev A internal definitions.
 * Pin allocation: hardware/fera-core/pinmap.md and gen/design.py in the FERA repo.
 */

#pragma once

#include <px4_platform_common/px4_config.h>
#include <nuttx/compiler.h>
#include <stdint.h>

#include <stm32_gpio.h>

/* LEDs: PC13 red, PC14 green, PC15 blue (rev A brings them to test pads only).
 * Driven high = on. */
#define GPIO_LED_RED            /* PC13 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTC|GPIO_PIN13)
#define GPIO_LED_GREEN          /* PC14 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTC|GPIO_PIN14)
#define GPIO_LED_BLUE           /* PC15 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTC|GPIO_PIN15)

#define BOARD_HAS_CONTROL_STATUS_LEDS   1
#define BOARD_OVERLOAD_LED              LED_RED
#define BOARD_ARMED_STATE_LED           LED_BLUE

/* ADC: PC0 = system rail (VSYS) through a 10 k / 10 k divider.
 * Battery voltage and current come from the INA226 on I2C2, not from the ADC. */
#define ADC1_CH(n)                  (n)

#define PX4_ADC_GPIO  \
	/* PC0 */  GPIO_ADC123_INP10

#define ADC_SCALED_V5_SENSE         /* PC0 */  ADC1_CH(10)

#define ADC_CHANNELS \
	((1 << ADC_SCALED_V5_SENSE))

/* Battery: one digital monitor (INA226), no analogue battery inputs */
#define BOARD_NUMBER_DIGITAL_BRICKS 1

/* ADC_V5_V_FULL_SCALE defaults to 6.6 V, which is this 2:1 divider. */
#define BOARD_ADC_USB_CONNECTED     (px4_arch_gpioread(GPIO_OTGFS_VBUS))

/* PWM: 12 outputs, three per port.
 *   1-4  S1 (ESC, DShot)   TIM1 CH1-4  PE9  PE11 PE13 PE14
 *   5-8  S2 (servo)        TIM4 CH1-4  PD12 PD13 PD14 PD15
 *   9-12 S3 (servo)        TIM3 CH1-4  PC6  PC7  PB0  PB1
 * Within a role, output n belongs to port n-1 (FRONT, RIGHT, BACK, LEFT). */
#define DIRECT_PWM_OUTPUT_CHANNELS   12
#define DIRECT_INPUT_TIMER_CHANNELS  12

#define BOARD_HAS_PWM  DIRECT_PWM_OUTPUT_CHANNELS
#define BOARD_NUM_IO_TIMERS 3

/* FERA ports (docs/port-spec.md). Index 0..3 = FRONT, RIGHT, BACK, LEFT.
 *   EN     TPS2069C enable, high = module 5 V on. A 10 k pull-down holds it off in reset;
 *          it is set low here at boot. Turn a port on only after its module ID is read.
 *   nFLT   TPS2069C fault, open drain, low = overcurrent (9 ms deglitch).
 *   nLATCH DRV5032AJ hall switch, open drain, low = latch closed.
 *   ID     1-Wire to the module EEPROM, 2.2 k pull-up on the board. */
#define GPIO_FERA_P0_EN     /* PE1  */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTE|GPIO_PIN1)
#define GPIO_FERA_P1_EN     /* PB12 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTB|GPIO_PIN12)
#define GPIO_FERA_P2_EN     /* PE12 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTE|GPIO_PIN12)
#define GPIO_FERA_P3_EN     /* PA2  */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTA|GPIO_PIN2)

#define GPIO_FERA_P0_nFLT   /* PB4  */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTB|GPIO_PIN4)
#define GPIO_FERA_P1_nFLT   /* PD11 */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTD|GPIO_PIN11)
#define GPIO_FERA_P2_nFLT   /* PE10 */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTE|GPIO_PIN10)
#define GPIO_FERA_P3_nFLT   /* PA1  */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTA|GPIO_PIN1)

#define GPIO_FERA_P0_nLATCH /* PD3  */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTD|GPIO_PIN3)
#define GPIO_FERA_P1_nLATCH /* PD4  */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTD|GPIO_PIN4)
#define GPIO_FERA_P2_nLATCH /* PD7  */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTD|GPIO_PIN7)
#define GPIO_FERA_P3_nLATCH /* PD10 */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTD|GPIO_PIN10)

#define GPIO_FERA_P0_ID     /* PB5  */ (GPIO_INPUT|GPIO_FLOAT|GPIO_PORTB|GPIO_PIN5)
#define GPIO_FERA_P1_ID     /* PA10 */ (GPIO_INPUT|GPIO_FLOAT|GPIO_PORTA|GPIO_PIN10)
#define GPIO_FERA_P2_ID     /* PB2  */ (GPIO_INPUT|GPIO_FLOAT|GPIO_PORTB|GPIO_PIN2)
#define GPIO_FERA_P3_ID     /* PC1  */ (GPIO_INPUT|GPIO_FLOAT|GPIO_PORTC|GPIO_PIN1)

#define FERA_PORT_COUNT 4

#define FERA_PORT_GPIO_INIT \
	GPIO_FERA_P0_EN, GPIO_FERA_P1_EN, GPIO_FERA_P2_EN, GPIO_FERA_P3_EN, \
	GPIO_FERA_P0_nFLT, GPIO_FERA_P1_nFLT, GPIO_FERA_P2_nFLT, GPIO_FERA_P3_nFLT, \
	GPIO_FERA_P0_nLATCH, GPIO_FERA_P1_nLATCH, GPIO_FERA_P2_nLATCH, GPIO_FERA_P3_nLATCH, \
	GPIO_FERA_P0_ID, GPIO_FERA_P1_ID, GPIO_FERA_P2_ID, GPIO_FERA_P3_ID

/* Safety button: PA15 to ground, so it reads LOW when pressed. PX4's safety_button driver
 * expects high = pressed, so it is not enabled on this board yet (rev B: invert in hardware
 * or add an active-low option to the driver). */
#define GPIO_nBTN_SAFETY    /* PA15 */ (GPIO_INPUT|GPIO_PULLUP|GPIO_PORTA|GPIO_PIN15)

/* Tone alarm: PA0, TIM2 CH1 (rev A: test pad only, no driver transistor fitted) */
#define TONE_ALARM_TIMER        2  /* timer 2 */
#define TONE_ALARM_CHANNEL      1  /* PA0 TIM2_CH1 */
#define GPIO_BUZZER_1           /* PA0 */ (GPIO_OUTPUT|GPIO_PUSHPULL|GPIO_SPEED_2MHz|GPIO_OUTPUT_CLEAR|GPIO_PORTA|GPIO_PIN0)
#define GPIO_TONE_ALARM_IDLE    GPIO_BUZZER_1
#define GPIO_TONE_ALARM         GPIO_TIM2_CH1OUT_1

/* USB OTG FS: PA9 VBUS sense (10 k series resistor) */
#define GPIO_OTGFS_VBUS         /* PA9 */ (GPIO_INPUT|GPIO_PULLDOWN|GPIO_SPEED_100MHz|GPIO_PORTA|GPIO_PIN9)

/* High-resolution timer: TIM5, no pin used */
#define HRT_TIMER               5
#define HRT_TIMER_CHANNEL       1

/* RC input: CRSF / ELRS on USART3 (PD8 TX, PD9 RX) */
#define RC_SERIAL_PORT          "/dev/ttyS2"
#define BOARD_SUPPORTS_RC_SERIAL_PORT_OUTPUT

/* SD card on SDMMC1, card detect PA8 (low = card present) */
#define SDIO_SLOTNO             0
#define SDIO_MINOR              0
#define GPIO_SDMMC1_NCD         /* PA8 */ (GPIO_INPUT|GPIO_PULLUP|GPIO_EXTI|GPIO_PORTA|GPIO_PIN8)

#define BOARD_DMA_ALLOC_POOL_SIZE 5120

#define BOARD_HAS_ON_RESET 1

#define PX4_GPIO_INIT_LIST { \
		PX4_ADC_GPIO, \
		FERA_PORT_GPIO_INIT, \
		GPIO_nBTN_SAFETY, \
		GPIO_TONE_ALARM_IDLE, \
	}

#define BOARD_ENABLE_CONSOLE_BUFFER

__BEGIN_DECLS

#ifndef __ASSEMBLY__

int stm32_sdio_initialize(void);

extern void stm32_spiinitialize(void);

extern void stm32_usbinitialize(void);

extern void board_peripheral_reset(int ms);

#include <px4_platform_common/board_common.h>

#endif /* __ASSEMBLY__ */

__END_DECLS
