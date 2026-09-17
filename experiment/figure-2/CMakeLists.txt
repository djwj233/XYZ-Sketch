cmake_minimum_required(VERSION 3.16)
project(figure2_experiment LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)

find_package(OpenSSL REQUIRED)
find_library(NTL_LIBRARY ntl REQUIRED)
find_library(GMP_LIBRARY gmp REQUIRED)
find_package(Threads REQUIRED)

add_executable(figure2_dataset_engine cpp/dataset_engine.cpp)
target_link_libraries(figure2_dataset_engine PRIVATE OpenSSL::Crypto)

add_executable(figure2_xyz_engine cpp/xyz_engine.cpp)
target_include_directories(figure2_xyz_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../XYZ-Sketch)
target_link_libraries(figure2_xyz_engine PRIVATE OpenSSL::Crypto)

add_library(figure2_minisketch STATIC
    ../../external/minisketch/src/minisketch.cpp
    ../../external/minisketch/src/fields/generic_1byte.cpp
    ../../external/minisketch/src/fields/generic_2bytes.cpp
    ../../external/minisketch/src/fields/generic_3bytes.cpp
    ../../external/minisketch/src/fields/generic_4bytes.cpp
    ../../external/minisketch/src/fields/generic_5bytes.cpp
    ../../external/minisketch/src/fields/generic_6bytes.cpp
    ../../external/minisketch/src/fields/generic_7bytes.cpp
    ../../external/minisketch/src/fields/generic_8bytes.cpp
    ../../external/minisketch/src/fields/clmul_1byte.cpp
    ../../external/minisketch/src/fields/clmul_2bytes.cpp
    ../../external/minisketch/src/fields/clmul_3bytes.cpp
    ../../external/minisketch/src/fields/clmul_4bytes.cpp
    ../../external/minisketch/src/fields/clmul_5bytes.cpp
    ../../external/minisketch/src/fields/clmul_6bytes.cpp
    ../../external/minisketch/src/fields/clmul_7bytes.cpp
    ../../external/minisketch/src/fields/clmul_8bytes.cpp
)
target_include_directories(figure2_minisketch PUBLIC ../../external/minisketch/include)
target_compile_definitions(figure2_minisketch PRIVATE
    HAVE_CLMUL HAVE_CLZ
    DISABLE_FIELD_2 DISABLE_FIELD_3 DISABLE_FIELD_4 DISABLE_FIELD_5 DISABLE_FIELD_6
    DISABLE_FIELD_7 DISABLE_FIELD_8 DISABLE_FIELD_9 DISABLE_FIELD_10 DISABLE_FIELD_11
    DISABLE_FIELD_12 DISABLE_FIELD_13 DISABLE_FIELD_14 DISABLE_FIELD_15 DISABLE_FIELD_16
    DISABLE_FIELD_17 DISABLE_FIELD_18 DISABLE_FIELD_19 DISABLE_FIELD_20 DISABLE_FIELD_21
    DISABLE_FIELD_22 DISABLE_FIELD_23 DISABLE_FIELD_24 DISABLE_FIELD_25 DISABLE_FIELD_26
    DISABLE_FIELD_27 DISABLE_FIELD_28 DISABLE_FIELD_29 DISABLE_FIELD_31 DISABLE_FIELD_32
    DISABLE_FIELD_33 DISABLE_FIELD_34 DISABLE_FIELD_35 DISABLE_FIELD_36 DISABLE_FIELD_37
    DISABLE_FIELD_38 DISABLE_FIELD_39 DISABLE_FIELD_40 DISABLE_FIELD_41 DISABLE_FIELD_42
    DISABLE_FIELD_43 DISABLE_FIELD_44 DISABLE_FIELD_45 DISABLE_FIELD_46 DISABLE_FIELD_47
    DISABLE_FIELD_48 DISABLE_FIELD_49 DISABLE_FIELD_50 DISABLE_FIELD_51 DISABLE_FIELD_52
    DISABLE_FIELD_53 DISABLE_FIELD_54 DISABLE_FIELD_55 DISABLE_FIELD_56 DISABLE_FIELD_57
    DISABLE_FIELD_58 DISABLE_FIELD_59 DISABLE_FIELD_60 DISABLE_FIELD_61 DISABLE_FIELD_62
    DISABLE_FIELD_63 DISABLE_FIELD_64
)
set_source_files_properties(
    ../../external/minisketch/src/fields/clmul_1byte.cpp
    ../../external/minisketch/src/fields/clmul_2bytes.cpp
    ../../external/minisketch/src/fields/clmul_3bytes.cpp
    ../../external/minisketch/src/fields/clmul_4bytes.cpp
    ../../external/minisketch/src/fields/clmul_5bytes.cpp
    ../../external/minisketch/src/fields/clmul_6bytes.cpp
    ../../external/minisketch/src/fields/clmul_7bytes.cpp
    ../../external/minisketch/src/fields/clmul_8bytes.cpp
    PROPERTIES COMPILE_OPTIONS -mpclmul
)
add_executable(figure2_minisketch_engine cpp/minisketch_engine.cpp)
target_link_libraries(figure2_minisketch_engine PRIVATE figure2_minisketch OpenSSL::Crypto)

add_executable(figure2_external_iblt_engine
    cpp/external_iblt_engine.cpp
    ../../external/IBLT_Cplusplus/iblt.cpp
    ../../external/IBLT_Cplusplus/murmurhash3.cpp
)
target_include_directories(figure2_external_iblt_engine PRIVATE ../../external/IBLT_Cplusplus)
target_link_libraries(figure2_external_iblt_engine PRIVATE OpenSSL::Crypto)

add_executable(figure2_project_iblt_engine cpp/project_iblt_engine.cpp)
target_include_directories(figure2_project_iblt_engine PRIVATE ../../IBLT)
target_link_libraries(figure2_project_iblt_engine PRIVATE OpenSSL::Crypto)

set(CPISYNC_SOURCES
    ../../external/cpisync/src/CommString.cpp
    ../../external/cpisync/src/Communicant.cpp
    ../../external/cpisync/src/CPISync.cpp
    ../../external/cpisync/src/DataObject.cpp
    ../../external/cpisync/src/Logger.cpp
    ../../external/cpisync/src/SyncMethod.cpp
    ../../external/cpisync/src/UID.cpp
    ../../external/cpisync/src/IBLT.cpp
    ../../external/cpisync/src/StrataEst.cpp
)
add_executable(figure2_cpisync_engine cpp/cpisync_engine.cpp ${CPISYNC_SOURCES})
set_property(TARGET figure2_cpisync_engine PROPERTY CXX_STANDARD 11)
target_include_directories(figure2_cpisync_engine PRIVATE ../../external/cpisync/include)
target_compile_definitions(figure2_cpisync_engine PRIVATE DEFAULT_LOGLEVEL=TEST)
target_link_libraries(figure2_cpisync_engine PRIVATE ${NTL_LIBRARY} ${GMP_LIBRARY} Threads::Threads OpenSSL::Crypto)

foreach(target
    figure2_dataset_engine figure2_xyz_engine figure2_minisketch_engine
    figure2_external_iblt_engine figure2_project_iblt_engine
    figure2_cpisync_engine)
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wno-deprecated-declarations)
endforeach()
