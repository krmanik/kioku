# The patched sources of Qt's iOS platform plugin (qios), compiled the way
# qtbase src/plugins/platforms/ios/CMakeLists.txt does: tools/build_qt_plugin.sh
# drives it and puts the objects in place of their copies in the prebuilt
# static libqios.a. Only the files that ios/patches/qios-*.patch change.
cmake_minimum_required(VERSION 3.21)
project(qios LANGUAGES CXX OBJCXX)

set(QTBASE_SRC "" CACHE PATH "qtbase source tree")
find_package(Qt6 REQUIRED COMPONENTS Core Gui CorePrivate GuiPrivate)

set(SRC ${QTBASE_SRC}/src/plugins/platforms/ios)
set(SOURCES qiosplatformaccessibility.mm qiostextinputoverlay.mm qiostextresponder.mm quiview.mm)
list(TRANSFORM SOURCES PREPEND ${SRC}/)

add_library(qios OBJECT ${SOURCES})
set_target_properties(qios PROPERTIES
    # like Qt's own build: the plugin's symbols stay inside the app
    CXX_VISIBILITY_PRESET hidden
    OBJCXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)
target_include_directories(qios PRIVATE ${SRC})
target_compile_definitions(qios PRIVATE QT_PLUGIN QT_STATICPLUGIN QT_NO_FOREACH)
target_compile_options(qios PRIVATE -fno-exceptions -fstack-protector-strong)
target_link_libraries(qios PRIVATE Qt6::Core Qt6::CorePrivate Qt6::Gui Qt6::GuiPrivate)
