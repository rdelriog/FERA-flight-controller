cmake_minimum_required(VERSION 3.22)
project(fc_f730 C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
include(cmake/arm-none-eabi-toolchain.cmake)
add_definitions(-DSTM32F730xx -DUSE_HAL_DRIVER)
add_compile_options(-O2 -g3 -ffast-math -fdata-sections -ffunction-sections -fno-exceptions -fno-rtti -Wall -Wextra)
add_link_options(-Wl,--gc-sections -Wl,-Map=${PROJECT_NAME}.map)
file(GLOB FW_SRC src/*.c src/*/*.c src/*/*/*.c third_party/cmsis/*.c third_party/stm32_hal/*.c)
add_executable(${PROJECT_NAME}.elf ${FW_SRC} startup_stm32f730xx.s)
target_include_directories(${PROJECT_NAME}.elf PRIVATE include third_party/cmsis third_party/stm32_hal)
set(LINKER_SCRIPT "${CMAKE_SOURCE_DIR}/linker.ld")
target_link_options(${PROJECT_NAME}.elf PRIVATE -T ${LINKER_SCRIPT})
add_custom_command(TARGET ${PROJECT_NAME}.elf POST_BUILD
  COMMAND ${CMAKE_SIZE} ${PROJECT_NAME}.elf
  COMMAND ${CMAKE_OBJCOPY} -O ihex ${PROJECT_NAME}.elf ${PROJECT_NAME}.hex
  COMMAND ${CMAKE_OBJCOPY} -O binary ${PROJECT_NAME}.elf ${PROJECT_NAME}.bin
)
