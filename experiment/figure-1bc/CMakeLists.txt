cmake_minimum_required(VERSION 3.16)
project(figure1bc_engine LANGUAGES CXX)

find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

add_executable(figure1bc_engine cpp/figure1bc_engine.cpp)
target_compile_features(figure1bc_engine PRIVATE cxx_std_17)
target_compile_options(figure1bc_engine PRIVATE -O3 -Wall -Wextra -Wpedantic)
target_link_libraries(figure1bc_engine PRIVATE OpenSSL::Crypto Threads::Threads)
