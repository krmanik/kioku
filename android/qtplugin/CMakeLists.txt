# Qt's Android platform plugin (qtforandroid), rebuilt from qtbase's sources
# with android/patches/qtforandroid-*.patch applied; tools/build_qt_plugin.sh
# drives it and puts the result in place of the prebuilt plugin.
# Source list: qtbase src/plugins/platforms/android/CMakeLists.txt, with the
# features of the prebuilt Qt (egl, vulkan, clipboard, accessibility,
# android_style_assets).
cmake_minimum_required(VERSION 3.21)
project(qtforandroid LANGUAGES CXX)

set(QTBASE_SRC "" CACHE PATH "qtbase source tree")
find_package(Qt6 REQUIRED COMPONENTS Core Gui CorePrivate GuiPrivate)

set(SRC ${QTBASE_SRC}/src/plugins/platforms/android)
set(SOURCES
    androidcontentfileengine.cpp qandroidapkfileengine.cpp androidjniinput.cpp
    androidjnimain.cpp androidjnimenu.cpp main.cpp qandroidassetsfileenginehandler.cpp
    qandroideventdispatcher.cpp qandroidinputcontext.cpp qandroidplatformdialoghelpers.cpp
    qandroidplatformfiledialoghelper.cpp qandroidplatformfontdatabase.cpp
    qandroidplatformforeignwindow.cpp qandroidplatformfileiconengine.cpp
    qandroidplatformiconengine.cpp qandroidplatformintegration.cpp qandroidplatformmenu.cpp
    qandroidplatformmenubar.cpp qandroidplatformmenuitem.cpp qandroidplatformscreen.cpp
    qandroidplatformservices.cpp qandroidplatformtheme.cpp qandroidplatformwindow.cpp
    qandroidsystemlocale.cpp androidwindowembedding.cpp androidbackendregister.cpp
    extract.cpp
    qandroidplatformclipboard.cpp qandroidplatformdrag.cpp
    androidjniaccessibility.cpp qandroidplatformaccessibility.cpp
    qandroidplatformopenglcontext.cpp qandroidplatformopenglwindow.cpp
    qandroidplatformoffscreensurface.cpp
    qandroidplatformvulkaninstance.cpp qandroidplatformvulkanwindow.cpp
)
list(TRANSFORM SOURCES PREPEND ${SRC}/)

add_library(qtforandroid SHARED ${SOURCES})
set_target_properties(qtforandroid PROPERTIES
    AUTOMOC ON
    # like Qt's own build: only the plugin and JNI entry points are exported
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
    OUTPUT_NAME plugins_platforms_qtforandroid_${ANDROID_ABI}
)
# some private headers include qpa headers without the qpa/ prefix
target_include_directories(qtforandroid PRIVATE ${SRC} ${QTBASE_SRC}/src/3rdparty/android
    ${QT6_INSTALL_PREFIX}/include/QtGui/${Qt6_VERSION}/QtGui/qpa)
target_compile_definitions(qtforandroid PRIVATE QT_PLUGIN QT_NO_FOREACH)
target_link_libraries(qtforandroid PRIVATE
    Qt6::Core Qt6::CorePrivate Qt6::Gui Qt6::GuiPrivate
    EGL GLESv2 android jnigraphics log
)
target_link_options(qtforandroid PRIVATE -s)
