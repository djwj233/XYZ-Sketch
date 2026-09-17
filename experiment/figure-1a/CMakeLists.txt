cmake_minimum_required(VERSION 3.16)
project(figure1a_experiment LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenSSL REQUIRED)

add_executable(figure1a_engine cpp/figure1a_engine.cpp)
target_include_directories(figure1a_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../XYZ-Sketch)
target_link_libraries(figure1a_engine PRIVATE OpenSSL::Crypto)
target_compile_options(figure1a_engine PRIVATE -Wall -Wextra -Wno-deprecated-declarations)
