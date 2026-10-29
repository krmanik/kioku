#!/bin/bash
# Build the programs add-ons start with subprocess (ffmpeg, ffprobe, ...) for
# the native apps, from source, with the libraries they need.
#
# Every program's main is renamed kioku_<name>_main (KIOKU_MAIN) and its sources get
# shared/programs/kioku_prog.h, so it can also run inside the app; each
# program is prelinked into one object exporting only its entry point
# (ffmpeg and ffprobe, like most programs, define clashing globals).
#   ios, ios-sim: libkiokuprog.a with the _kioku_programs module, linked into
#                 the app (inittab in main.mm)
#   android:      libkiokuprog.so, an executable (packaged as a native library
#                 so Android lets the app run it) that picks the program from
#                 the name it was started as
#   macos:        libkiokuprog.dylib with the module, to test the in-app runs
#                 on the build machine
# Output: build/programs/<target>/lib, and build/programs/data (programs' data
# files; the apps bundle it as kioku_programs_data in site-packages)
# Usage: build_programs.sh ios|ios-sim|android|macos
# Env: ANDROID_NDK_ROOT (android), JOBS (default: all cores)
set -euo pipefail
SHARED=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$SHARED/.." && pwd)
source "$SHARED/versions.env"
TARGET=${1:?ios, ios-sim, android or macos}
WORK=$ROOT/build/programs
SRC=$WORK/src
OUT=$WORK/$TARGET
PREFIX=$OUT/prefix
BUILD=$OUT/build
STAMPS=$OUT/stamps
JOBS=${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || nproc)}
mkdir -p "$SRC" "$PREFIX/lib" "$PREFIX/include" "$BUILD" "$STAMPS"

# Toolchain --------------------------------------------------------------------
case $TARGET in
ios | ios-sim | macos)
    case $TARGET in
    ios) SDKNAME=iphoneos; TRIPLE=arm64-apple-ios17.0 ;;
    ios-sim) SDKNAME=iphonesimulator; TRIPLE=arm64-apple-ios17.0-simulator ;;
    macos) SDKNAME=macosx; TRIPLE=arm64-apple-macos13.0 ;;
    esac
    SDK=$(xcrun --sdk $SDKNAME --show-sdk-path)
    ARCHFLAGS="-target $TRIPLE -isysroot $SDK"
    CC="$(xcrun -f clang) $ARCHFLAGS"
    CXX="$(xcrun -f clang++) $ARCHFLAGS"
    AR=$(xcrun -f ar)
    RANLIB=$(xcrun -f ranlib)
    NM=$(xcrun -f nm)
    STRIP=$(xcrun -f strip)
    HOST=aarch64-apple-darwin
    CMAKE_TARGET=(-DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_SYSROOT="$SDK"
        -DCMAKE_C_FLAGS="-target $TRIPLE" -DCMAKE_CXX_FLAGS="-target $TRIPLE")
    if [ "$TARGET" = macos ]; then
        CMAKE_TARGET+=(-DCMAKE_OSX_DEPLOYMENT_TARGET=13.0)
    else
        # no app bundles for the libraries' own programs (libaom's)
        CMAKE_TARGET+=(-DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 -DCMAKE_MACOSX_BUNDLE=OFF
            -DCMAKE_SYSTEM_PROCESSOR=aarch64)
    fi
    PYINC=$ROOT/ios/deps/python-ios/Python.xcframework/ios-arm64/include/python$PYTHON_VERSION
    [ "$TARGET" = macos ] && PYINC=$(python$PYTHON_VERSION -c 'import sysconfig; print(sysconfig.get_path("include"))')
    ;;
android)
    NDK=${ANDROID_NDK_ROOT:-${ANDROID_NDK:-$HOME/Library/Android/sdk/ndk/28.2.13676358}}
    LLVM=$NDK/toolchains/llvm/prebuilt/$( [ "$(uname)" = Darwin ] && echo darwin-x86_64 || echo linux-x86_64 )/bin
    CC=$LLVM/aarch64-linux-android28-clang
    CXX=$LLVM/aarch64-linux-android28-clang++
    AR=$LLVM/llvm-ar
    RANLIB=$LLVM/llvm-ranlib
    NM=$LLVM/llvm-nm
    STRIP=$LLVM/llvm-strip
    HOST=aarch64-linux-android
    ARCHFLAGS=
    CMAKE_TARGET=(-DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake"
        -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=28)
    ;;
*)
    echo "unknown target $TARGET" >&2; exit 1 ;;
esac
CFLAGS="-O2 -fPIC"
export PKG_CONFIG_LIBDIR=$PREFIX/lib/pkgconfig PKG_CONFIG_PATH=

fetch() {  # fetch <url> <directory it unpacks to>
    [ -d "$SRC/$2" ] && return
    echo "fetching $2"
    local tmp=$SRC/.tmp-$2
    rm -rf "$tmp" && mkdir -p "$tmp"
    curl -fsSL --retry 3 "$1" | tar xf - -C "$tmp"
    mv "$tmp"/* "$SRC/$2" && rmdir "$tmp"
}

step() {  # step <name>: true if <name> still has to be built
    [ ! -f "$STAMPS/$1" ] && echo "building $1 ($TARGET)"
}
done_step() { touch "$STAMPS/$1"; }

cmake_build() {  # cmake_build <name> <source dir> [cmake args]
    local name=$1 src=$2; shift 2
    step "$name" || return 0
    rm -rf "$BUILD/$name"
    cmake -S "$src" -B "$BUILD/$name" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_PREFIX_PATH="$PREFIX" \
        -DCMAKE_FIND_ROOT_PATH="$PREFIX" -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
        "${CMAKE_TARGET[@]}" "$@" > "$BUILD/$name.log" 2>&1
    cmake --build "$BUILD/$name" -j"$JOBS" >> "$BUILD/$name.log" 2>&1
    cmake --install "$BUILD/$name" >> "$BUILD/$name.log" 2>&1
    done_step "$name"
}

autotools_build() {  # autotools_build <name> <source dir> [configure args]
    local name=$1 src=$2; shift 2
    step "$name" || return 0
    rm -rf "$BUILD/$name" && mkdir -p "$BUILD/$name"
    (cd "$BUILD/$name" && CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB" \
        CFLAGS="$CFLAGS" CXXFLAGS="$CFLAGS" \
        "$src/configure" --host=$HOST --prefix="$PREFIX" --enable-static --disable-shared \
        "$@" && make -j"$JOBS" && make install) > "$BUILD/$name.log" 2>&1
    done_step "$name"
}

# Sources ----------------------------------------------------------------------
fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" ffmpeg-$FFMPEG_VERSION
fetch "https://downloads.sourceforge.net/project/lame/lame/$LAME_VERSION/lame-$LAME_VERSION.tar.gz" lame-$LAME_VERSION
fetch "https://downloads.xiph.org/releases/ogg/libogg-$OGG_VERSION.tar.xz" libogg-$OGG_VERSION
fetch "https://downloads.xiph.org/releases/vorbis/libvorbis-$VORBIS_VERSION.tar.xz" libvorbis-$VORBIS_VERSION
fetch "https://downloads.xiph.org/releases/opus/opus-$OPUS_VERSION.tar.gz" opus-$OPUS_VERSION
fetch "https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-$WEBP_VERSION.tar.gz" libwebp-$WEBP_VERSION
fetch "https://github.com/webmproject/libvpx/archive/refs/tags/v$VPX_VERSION.tar.gz" libvpx-$VPX_VERSION
fetch "https://storage.googleapis.com/aom-releases/libaom-$AOM_VERSION.tar.gz" libaom-$AOM_VERSION
fetch "https://downloads.sourceforge.net/project/libpng/libpng16/$PNG_VERSION/libpng-$PNG_VERSION.tar.xz" libpng-$PNG_VERSION
fetch "https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/$JPEG_VERSION/libjpeg-turbo-$JPEG_VERSION.tar.gz" libjpeg-turbo-$JPEG_VERSION
fetch "https://github.com/libffi/libffi/releases/download/v$LIBFFI_VERSION/libffi-$LIBFFI_VERSION.tar.gz" libffi-$LIBFFI_VERSION
fetch "https://download.savannah.gnu.org/releases/freetype/freetype-$FREETYPE_VERSION.tar.xz" freetype-$FREETYPE_VERSION
fetch "https://github.com/DanBloomberg/leptonica/releases/download/$LEPTONICA_VERSION/leptonica-$LEPTONICA_VERSION.tar.gz" leptonica-$LEPTONICA_VERSION
fetch "https://github.com/tesseract-ocr/tesseract/archive/refs/tags/$TESSERACT_VERSION.tar.gz" tesseract-$TESSERACT_VERSION
fetch "https://github.com/espeak-ng/espeak-ng/archive/refs/tags/$ESPEAK_VERSION.tar.gz" espeak-ng-$ESPEAK_VERSION
fetch "http://kakasi.namazu.org/stable/kakasi-$KAKASI_VERSION.tar.xz" kakasi-$KAKASI_VERSION
fetch "https://github.com/taku910/mecab/archive/$MECAB_COMMIT.tar.gz" mecab-$MECAB_COMMIT
fetch "https://code.videolan.org/videolan/x264/-/archive/$X264_COMMIT/x264-$X264_COMMIT.tar.bz2" x264-$X264_COMMIT

# FFmpeg's pipe: protocol: pipe:0/1/2 are the add-on's pipes inside the app
FILE_C=$SRC/ffmpeg-$FFMPEG_VERSION/libavformat/file.c
if ! grep -q 'kioku_fd(c->fd)' "$FILE_C"; then
    grep -q '^int kioku_fd' "$FILE_C" || perl -0pi -e \
        's/(static int pipe_open\(URLContext \*h, const char \*filename, int flags\)\n\{)/int kioku_fd(int fd);\n\n$1/' "$FILE_C"
    perl -0pi -e 's/(\n    c->fd = fd_dup\(h, c->fd\);\n    if \(c->fd == -1\)\n        return AVERROR\(errno\);\n    h->is_streamed = 1;)/\n    c->fd = kioku_fd(c->fd);$1/' "$FILE_C"
    grep -q 'kioku_fd(c->fd)' "$FILE_C" || { echo "file.c patch failed" >&2; exit 1; }
fi

# Codec libraries -----------------------------------------------------------------
# no mpg123 (FFmpeg decodes MP3): lame encodes only; no terminal libraries
# (the iOS SDK has curses without its headers)
autotools_build lame "$SRC/lame-$LAME_VERSION" --disable-frontend --disable-gtktest --disable-decoder \
    ac_cv_lib_termcap_initscr=no ac_cv_lib_curses_initscr=no ac_cv_lib_ncurses_initscr=no
cmake_build ogg "$SRC/libogg-$OGG_VERSION" -DINSTALL_DOCS=OFF -DBUILD_TESTING=OFF
cmake_build vorbis "$SRC/libvorbis-$VORBIS_VERSION"
cmake_build opus "$SRC/opus-$OPUS_VERSION" -DOPUS_BUILD_PROGRAMS=OFF -DOPUS_BUILD_TESTING=OFF
# libpng and libjpeg-turbo: for libwebp's cwebp/dwebp, leptonica and Pillow
cmake_build png "$SRC/libpng-$PNG_VERSION" -DPNG_SHARED=OFF -DPNG_TESTS=OFF -DPNG_TOOLS=OFF \
    -DPNG_FRAMEWORK=OFF
cmake_build jpeg "$SRC/libjpeg-turbo-$JPEG_VERSION" -DENABLE_SHARED=OFF -DWITH_TURBOJPEG=OFF \
    -DWITH_TOOLS=OFF -DWITH_TESTS=OFF
# libwebp, with cwebp and dwebp (AJT Media Converter converts images with cwebp)
cmake_build webp "$SRC/libwebp-$WEBP_VERSION" -DWEBP_BUILD_ANIM_UTILS=OFF -DWEBP_BUILD_CWEBP=ON \
    -DWEBP_BUILD_DWEBP=ON -DWEBP_BUILD_GIF2WEBP=OFF -DWEBP_BUILD_IMG2WEBP=OFF \
    -DWEBP_BUILD_VWEBP=OFF -DWEBP_BUILD_WEBPINFO=OFF -DWEBP_BUILD_WEBPMUX=OFF \
    -DWEBP_BUILD_EXTRAS=OFF -DWEBP_USE_THREAD=ON
# Pillow (build_wheels.sh) links -lwebp alone: libwebp.a with libsharpyuv in it
if [ "$TARGET" = android ] && ! "$NM" "$PREFIX/lib/libwebp.a" 2>/dev/null | grep -q " T SharpYuvInit"; then
    printf 'create %s\naddlib %s\naddlib %s\nsave\nend\n' "$PREFIX/lib/libwebp-all.a" \
        "$PREFIX/lib/libwebp.a" "$PREFIX/lib/libsharpyuv.a" | "$AR" -M
    mv "$PREFIX/lib/libwebp-all.a" "$PREFIX/lib/libwebp.a"
fi
# runtime CPU detection (libvpx and libaom): newer instructions (SVE, i8mm)
# only where the phone has them
cmake_build aom "$SRC/libaom-$AOM_VERSION" -DENABLE_DOCS=0 -DENABLE_EXAMPLES=0 -DENABLE_TESTS=0 \
    -DENABLE_TOOLS=0 -DAOM_TARGET_CPU=arm64

if step vpx; then
    # arm64-darwin-gcc is iOS (with the iPhone SDK); no arm64 simulator target
    case $TARGET in
    android) VPX_TARGET=arm64-android-gcc ;;
    ios) VPX_TARGET=arm64-darwin-gcc ;;
    ios-sim) VPX_TARGET=generic-gnu ;;
    macos) VPX_TARGET=arm64-darwin23-gcc ;;
    esac
    rm -rf "$BUILD/vpx" && mkdir -p "$BUILD/vpx"
    (cd "$BUILD/vpx" && CC="$CC" CXX="$CXX" AR="$AR" LD="$CC" AS=as STRIP="$STRIP" \
        CFLAGS="$CFLAGS" CXXFLAGS="$CFLAGS" LDFLAGS="$ARCHFLAGS" \
        "$SRC/libvpx-$VPX_VERSION/configure" --target=$VPX_TARGET --prefix="$PREFIX" \
        --enable-pic --disable-examples --disable-tools --disable-docs --disable-unit-tests \
        --enable-vp9-highbitdepth --as=auto \
        && make -j"$JOBS" && make install) > "$BUILD/vpx.log" 2>&1
    done_step vpx
fi

if step x264; then
    rm -rf "$BUILD/x264" && mkdir -p "$BUILD/x264"
    (cd "$BUILD/x264" && CC="$CC" AR="$AR" RANLIB="$RANLIB" STRIP="$STRIP" AS="$CC" \
        "$SRC/x264-$X264_COMMIT/configure" --host=$HOST --prefix="$PREFIX" \
        --enable-static --enable-pic --disable-cli --extra-cflags="$CFLAGS" \
        && make -j"$JOBS" && make install) > "$BUILD/x264.log" 2>&1
    done_step x264
fi

# FFmpeg -------------------------------------------------------------------------
FFBUILD=$BUILD/ffmpeg
FFLIBS="avdevice avfilter avformat avcodec swresample swscale avutil"
if step ffmpeg; then
    case $TARGET in
    # libvorbis.pc leaves out -lm
    android) FFOS=(--target-os=android --disable-iconv --disable-vulkan --extra-libs=-lm) ;;
    *) FFOS=(--target-os=darwin --enable-videotoolbox --enable-audiotoolbox) ;;
    esac
    # devices: only lavfi (generated input: anullsrc, sine, testsrc)
    rm -rf "$FFBUILD" && mkdir -p "$FFBUILD"
    (cd "$FFBUILD" && "$SRC/ffmpeg-$FFMPEG_VERSION/configure" \
        --prefix="$PREFIX" --enable-cross-compile --arch=aarch64 "${FFOS[@]}" \
        --cc="$CC" --cxx="$CXX" --ar="$AR" --ranlib="$RANLIB" --nm="$NM" --strip="$STRIP" \
        --extra-cflags="$CFLAGS -I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib" \
        --pkg-config=pkg-config --pkg-config-flags=--static \
        --enable-gpl --enable-version3 --enable-static --disable-shared \
        --disable-indevs --enable-indev=lavfi --disable-outdevs \
        --disable-doc --disable-debug --disable-ffplay --disable-sdl2 --disable-xlib \
        --disable-libxcb --disable-securetransport --disable-appkit --disable-avfoundation \
        --disable-coreimage --disable-metal \
        --enable-libmp3lame --enable-libvorbis --enable-libopus --enable-libwebp \
        --enable-libx264 --enable-libvpx --enable-libaom --enable-zlib \
        && printf 'print-%%:\n\t@echo $($*)\n' > print.mk \
        && make -j"$JOBS" $(for l in $FFLIBS; do echo lib$l/lib$l.a; done)) \
        > "$BUILD/ffmpeg.log" 2>&1 || {
        tail -30 "$BUILD/ffmpeg.log"; [ -f "$FFBUILD/ffbuild/config.log" ] && tail -30 "$FFBUILD/ffbuild/config.log"; exit 1; }
    done_step ffmpeg
fi

# Programs: compiled with kioku_prog.h, each prelinked into <name>.o ---------------
PROG=$OUT/obj
mkdir -p "$PROG"
INCLUDE_PROG="-include $SHARED/programs/kioku_prog.h"

# state_<family>.h puts a program's writable globals in sections of their
# own, which kioku_state_reset() puts back to their first values before each
# run inside the app (programs expect to start in a fresh process)
state_header() {  # state_header <family>: prints the -include option
    local h=$PROG/state_$1.h
    case $TARGET in
    android) echo "#pragma clang section bss=\"kb_$1\" data=\"kd_$1\"" > "$h" ;;
    *) echo "#pragma clang section bss=\"__DATA,__kb_$1\" data=\"__DATA,__kd_$1\"" > "$h" ;;
    esac
    echo "-include $h"
}

prelink() {  # prelink <output object> <entry symbol> <objects and archives...>
    local out=$1 entry=$2; shift 2
    case $TARGET in
    android)
        "$LLVM/ld.lld" -r -o "$out.tmp" "$@"
        "$LLVM/llvm-objcopy" --keep-global-symbol="$entry" "$out.tmp" "$out"
        rm "$out.tmp" ;;
    *)
        echo "_$entry" > "$out.exports"
        xcrun ld -r -arch arm64 -o "$out" -exported_symbols_list "$out.exports" "$@" ;;
    esac
}

if step fftools; then
    # a variable of FFmpeg's Makefile (print.mk: see above)
    ffvar() { make -s -C "$FFBUILD" -f Makefile -f print.mk "print-$1" | tail -1; }
    # without the tools' own ffmpeg.o/ffprobe.o and the shared objects, which
    # are compiled separately below
    COMMON="fftools/cmdutils.o fftools/opt_common.o"
    FFTOOLS_OBJS=$(ffvar OBJS-ffmpeg | tr ' ' '\n' | grep -vxE 'fftools/(ffmpeg|cmdutils|opt_common)\.o' | sort -u | tr '\n' ' ')
    FFPROBE_OBJS=$(ffvar OBJS-ffprobe | tr ' ' '\n' | grep -vxE 'fftools/(ffprobe|cmdutils|opt_common)\.o' | sort -u | tr '\n' ' ')
    # one family: ffmpeg and ffprobe never run at once
    FFCC="$CC $INCLUDE_PROG $(state_header ff)"
    (cd "$FFBUILD" && rm -f $FFTOOLS_OBJS $FFPROBE_OBJS $COMMON fftools/ffmpeg.o fftools/ffprobe.o \
        && make -j"$JOBS" CC="$FFCC" $FFTOOLS_OBJS $FFPROBE_OBJS $COMMON \
        && make CC="$FFCC -DKIOKU_MAIN=kioku_ffmpeg_tool_main" fftools/ffmpeg.o \
        && make CC="$FFCC -DKIOKU_MAIN=kioku_ffprobe_tool_main" fftools/ffprobe.o) \
        > "$BUILD/fftools.log" 2>&1 || { tail -30 "$BUILD/fftools.log"; exit 1; }
    (cd "$FFBUILD" && prelink "$PROG/ffmpeg.o" kioku_ffmpeg_tool_main \
        fftools/ffmpeg.o $FFTOOLS_OBJS $COMMON)
    (cd "$FFBUILD" && prelink "$PROG/ffprobe.o" kioku_ffprobe_tool_main \
        fftools/ffprobe.o $FFPROBE_OBJS $COMMON)
    $CC $CFLAGS -I"$FFBUILD" -I"$SRC/ffmpeg-$FFMPEG_VERSION" -c \
        "$SHARED/programs/ffmpeg_glue.c" -o "$PROG/ffmpeg_glue.o"
    done_step fftools
fi

glue() {  # glue <name> [family]: kioku_<name>_main (prog_glue.c)
    $CC $CFLAGS -DKIOKU_NAME=$1 ${2:+-DKIOKU_FAMILY=$2} -c "$SHARED/programs/prog_glue.c" \
        -o "$PROG/$1_glue.o"
}
compile() {  # compile <compiler and flags> <source> <object>
    echo "$1 -c $2 -o $3" >> "$BUILD/$NAME.log"
    $1 -c "$2" -o "$3" >> "$BUILD/$NAME.log" 2>&1 || { tail -20 "$BUILD/$NAME.log"; exit 1; }
}

# lame's command-line encoder (AwesomeTTS and others encode WAV with it)
NAME=lame-cli
if step $NAME; then
    L=$SRC/lame-$LAME_VERSION
    O=$BUILD/$NAME
    rm -rf "$O" && mkdir -p "$O" && : > "$BUILD/$NAME.log"
    LCC="$CC $CFLAGS $INCLUDE_PROG $(state_header lame) -DHAVE_CONFIG_H -I$BUILD/lame \
        -I$L/include -I$L/libmp3lame -I$L/frontend"
    # 3.101's frontend still calls two UCS-2 functions the library dropped
    cp "$L/frontend/parse.c" "$O/parse.c"
    perl -pi -e 's/id3tag_set_comment_ucs2\(gfp, 0, 0, str\)/id3tag_set_comment_utf8(gfp, 0, 0, (char const *)str)/;
        s/id3tag_set_fieldvalue_ucs2\(gfp, str\)/id3tag_set_fieldvalue(gfp, (char const *)str)/' "$O/parse.c"
    for f in main brhist console get_audio lametime parse timestatus lame_main; do
        flags=$LCC
        [ $f = main ] && flags="$LCC -DKIOKU_MAIN=kioku_lame_tool_main"
        src=$L/frontend/$f.c
        [ $f = parse ] && src=$O/parse.c
        compile "$flags" "$src" "$O/$f.o"
    done
    prelink "$PROG/lame.o" kioku_lame_tool_main "$O"/*.o
    glue lame lame
    done_step $NAME
fi

# kakasi (Japanese Support): its dictionaries come with the add-on
NAME=kakasi
if step $NAME; then
    K=$SRC/kakasi-$KAKASI_VERSION/src
    O=$BUILD/$NAME
    rm -rf "$O" && mkdir -p "$O" && : > "$BUILD/$NAME.log"
    cp "$SHARED/programs/kakasi_config.h" "$O/config.h"
    # 2.3.6 reads a dictionary without the "KAKASI" header (the older format
    # add-ons ship) from byte 6, after looking for the header
    cp "$K/dict.c" "$O/dict.c"
    perl -0pi -e 's/(    \} else \{\n\tdict_endian_mark = 0;)/$1\n\tfseek(kanwadict, 0, SEEK_SET);/' "$O/dict.c"
    grep -q 'fseek(kanwadict, 0, SEEK_SET)' "$O/dict.c" || { echo "kakasi dict.c patch failed" >&2; exit 1; }
    KCC="$CC $CFLAGS -w $INCLUDE_PROG $(state_header kakasi) -DHAVE_CONFIG_H -I$O -I$K"
    for f in kakasi a2 g2 j2 k2 ee2 hh2 jj2 kk2 dict itaiji kanjiio 78_83 level; do
        flags=$KCC
        [ $f = kakasi ] && flags="$KCC -DKIOKU_MAIN=kioku_kakasi_tool_main"
        src=$K/$f.c
        [ $f = dict ] && src=$O/dict.c
        compile "$flags" "$src" "$O/$f.o"
    done
    prelink "$PROG/kakasi.o" kioku_kakasi_tool_main "$O"/*.o
    glue kakasi kakasi
    done_step $NAME
fi

# MeCab: several runs at once (add-ons keep one open), so no state reset;
# std::cin/cout/cerr become the run's streams (kioku_iostream.cpp)
NAME=mecab
if step $NAME; then
    M=$SRC/mecab-$MECAB_COMMIT/mecab/src
    O=$BUILD/$NAME
    rm -rf "$O" && mkdir -p "$O/src" && : > "$BUILD/$NAME.log"
    cp "$M"/*.cpp "$M"/*.h "$O/src/"
    cp "$SHARED/programs/mecab_config.h" "$O/src/config.h"
    perl -pi -e 's/std::cin\b/kioku_cin()/g; s/std::cout\b/kioku_cout()/g; s/std::cerr\b/kioku_cerr()/g' \
        "$O"/src/*.cpp "$O"/src/*.h
    MCXX="$CXX $CFLAGS -std=c++11 -w $INCLUDE_PROG -DHAVE_CONFIG_H -I$O/src"
    for f in char_property connector context_id dictionary dictionary_compiler \
            dictionary_generator dictionary_rewriter eval feature_index iconv_utils lbfgs \
            learner learner_tagger libmecab nbest_generator param string_buffer tagger \
            tokenizer utils viterbi writer mecab; do
        flags=$MCXX
        [ $f = mecab ] && flags="$MCXX -DKIOKU_MAIN=kioku_mecab_tool_main"
        compile "$flags" "$O/src/$f.cpp" "$O/src/$f.o" &
    done
    wait
    compile "$CXX $CFLAGS -std=c++17" "$SHARED/programs/kioku_iostream.cpp" "$O/kioku_iostream.o"
    prelink "$PROG/mecab.o" kioku_mecab_tool_main "$O"/src/*.o "$O/kioku_iostream.o"
    glue mecab
    done_step $NAME
fi

# cwebp and dwebp: libwebp's example programs, over its image I/O libraries
NAME=webp-tools
if step $NAME; then
    W=$SRC/libwebp-$WEBP_VERSION
    O=$BUILD/$NAME
    rm -rf "$O" && mkdir -p "$O" && : > "$BUILD/$NAME.log"
    for t in cwebp dwebp; do
        compile "$CC $CFLAGS -w $INCLUDE_PROG $(state_header $t) -DKIOKU_MAIN=kioku_${t}_tool_main -DKIOKU_MAIN_CONST_ARGV \
            -DWEBP_HAVE_PNG -DWEBP_HAVE_JPEG -I$W -I$W/src -I$W/examples -I$PREFIX/include" \
            "$W/examples/$t.c" "$O/$t.o"
        prelink "$PROG/$t.o" kioku_${t}_tool_main "$O/$t.o" \
            "$BUILD/webp/libimagedec.a" "$BUILD/webp/libimageenc.a" "$BUILD/webp/libimageioutil.a" \
            "$BUILD/webp/libexampleutil.a"
        glue $t $t
    done
    done_step $NAME
fi

# Tesseract, with leptonica; only the program's own
# file gets kioku_prog.h (tesseract_glue.c does the rest)
# libffi: not for the programs, for cffi on Android (build_wheels.sh; Android's
# Python has no headers for its own)
if [ "$TARGET" = android ]; then
    autotools_build libffi "$SRC/libffi-$LIBFFI_VERSION" --with-pic --disable-docs --disable-multi-os-directory
fi
# FreeType: not for the programs, for Pillow's ImageFont (build_wheels.sh)
cmake_build freetype "$SRC/freetype-$FREETYPE_VERSION" -DFT_DISABLE_HARFBUZZ=ON \
    -DFT_DISABLE_BROTLI=ON -DFT_DISABLE_BZIP2=ON -DFT_DISABLE_PNG=ON -DFT_DISABLE_ZLIB=ON
cmake_build leptonica "$SRC/leptonica-$LEPTONICA_VERSION" -DSW_BUILD=OFF -DBUILD_PROG=OFF \
    -DENABLE_GIF=OFF -DENABLE_TIFF=OFF -DENABLE_OPENJPEG=OFF -DENABLE_WEBP=OFF
NAME=tesseract
if step $NAME; then
    T=$SRC/tesseract-$TESSERACT_VERSION
    # its check for leptonica's TIFF support runs a program (not possible
    # when cross-compiling); there's no TIFF either way
    grep -q 'if(NOT DISABLE_TIFF)\ncheck_leptonica' "$T/CMakeLists.txt" ||
        perl -0pi -e 's/\ncheck_leptonica_tiff_support\(\)\n/\nif(NOT DISABLE_TIFF)\n  check_leptonica_tiff_support()\nendif()\n/' "$T/CMakeLists.txt"
    # Google's cpu_features, for NEON on 32-bit ARM only (arm64 always has it)
    perl -0pi -e 's/  find_package\(CpuFeaturesNdkCompat REQUIRED\)\n.*?CpuFeatures::ndk_compat\)\n//s' "$T/CMakeLists.txt"
    O=$BUILD/$NAME
    rm -rf "$O" && mkdir -p "$O" && : > "$BUILD/$NAME.log"
    cmake -S "$T" -B "$O/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_PREFIX_PATH="$PREFIX" -DCMAKE_FIND_ROOT_PATH="$PREFIX" \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DLeptonica_DIR="$PREFIX/lib/cmake/leptonica" \
        -DBUILD_TRAINING_TOOLS=OFF -DGRAPHICS_DISABLED=ON -DOPENMP_BUILD=OFF \
        -DDISABLE_TIFF=ON -DDISABLE_ARCHIVE=ON -DDISABLE_CURL=ON -DENABLE_CCACHE=OFF \
        -DENABLE_PRECOMPILED_HEADERS=OFF -DENABLE_NATIVE=OFF -DINSTALL_CONFIGS=OFF \
        "${CMAKE_TARGET[@]}" >> "$BUILD/$NAME.log" 2>&1
    cmake --build "$O/build" -j"$JOBS" --target libtesseract >> "$BUILD/$NAME.log" 2>&1 || {
        tail -30 "$BUILD/$NAME.log"; exit 1; }
    cp "$T/src/tesseract.cpp" "$O/tesseract.cpp"
    perl -pi -e 's/std::cout\b/kioku_cout()/g; s/std::cerr\b/kioku_cerr()/g' "$O/tesseract.cpp"
    compile "$CXX $CFLAGS -std=c++17 -w $INCLUDE_PROG -DKIOKU_MAIN=kioku_tesseract_tool_main \
        -I$T/include -I$O/build/include -I$T/src/ccutil -I$T/src/ccstruct -I$T/src/api \
        -I$T/src/ccmain -I$T/src/viewer -I$T/src/dict -I$T/src/textord -I$T/src/wordrec \
        -I$T/src/classify -I$T/src/cutil -I$T/src/arch -I$T/src/lstm -I$T/src/training \
        -I$PREFIX/include/leptonica -I$PREFIX/include" "$O/tesseract.cpp" "$O/tesseract.o"
    compile "$CXX $CFLAGS -std=c++17" "$SHARED/programs/kioku_iostream.cpp" "$O/kioku_iostream.o"
    prelink "$PROG/tesseract.o" kioku_tesseract_tool_main "$O/tesseract.o" "$O/kioku_iostream.o"
    cp "$(find "$O/build" -name 'libtesseract*.a' | head -1)" "$PREFIX/lib/libtesseract.a"
    $CC $CFLAGS -c "$SHARED/programs/tesseract_glue.c" -o "$PROG/tesseract_glue.o"
    done_step $NAME
fi

# espeak-ng: its data is compiled by running espeak-ng, so once on the build
# machine (the data is the same everywhere); the targets build the library
# and the program. No sound output: add-ons write WAV (-w, --stdout).
ESPEAK=$SRC/espeak-ng-$ESPEAK_VERSION
ESPEAK_OPTIONS=(-DUSE_MBROLA=OFF -DUSE_LIBSONIC=OFF -DUSE_LIBPCAUDIO=OFF -DUSE_ASYNC=OFF
    -DUSE_SPEECHPLAYER=OFF -DESPEAK_BUILD_MANPAGES=OFF -DCOMPILE_INTONATIONS=ON)
ESPEAK_DATA=$WORK/data/espeak-ng-data
if [ ! -f "$ESPEAK_DATA/phondata" ]; then
    echo "building espeak-ng data"
    H=$WORK/host/espeak-ng
    rm -rf "$H"
    cmake -S "$ESPEAK" -B "$H" -G Ninja -DCMAKE_BUILD_TYPE=Release "${ESPEAK_OPTIONS[@]}" \
        > "$WORK/espeak-data.log" 2>&1
    cmake --build "$H" -j"$JOBS" >> "$WORK/espeak-data.log" 2>&1 || {
        tail -30 "$WORK/espeak-data.log"; exit 1; }
    rm -rf "$ESPEAK_DATA" && mkdir -p "$WORK/data"
    cp -R "$H/espeak-ng-data" "$ESPEAK_DATA"
fi
NAME=espeak
if step $NAME; then
    O=$BUILD/$NAME
    rm -rf "$O" && mkdir -p "$O" && : > "$BUILD/$NAME.log"
    # the library's globals too: state_espeak.h only adds a pragma. Room for
    # the data folder's path (160 bytes by default: too few in the iOS
    # Simulator). iOS has le16toh() and co. in sys/endian.h, which its
    # configure misses
    STATE_ESPEAK="$(state_header espeak) -DN_PATH_HOME=1024"
    case $TARGET in ios | ios-sim) STATE_ESPEAK="$STATE_ESPEAK -include sys/endian.h" ;; esac
    cmake -S "$ESPEAK" -B "$O/build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON "${ESPEAK_OPTIONS[@]}" "${CMAKE_TARGET[@]}" \
        -DCMAKE_C_FLAGS_RELEASE="-O2 -DNDEBUG $STATE_ESPEAK" \
        >> "$BUILD/$NAME.log" 2>&1
    cmake --build "$O/build" -j"$JOBS" --target espeak-ng >> "$BUILD/$NAME.log" 2>&1 || {
        tail -30 "$BUILD/$NAME.log"; exit 1; }
    compile "$CC $CFLAGS -w $INCLUDE_PROG $STATE_ESPEAK -DKIOKU_MAIN=kioku_espeak_tool_main \
        -I$ESPEAK/src/include -I$ESPEAK/src/include/compat -I$O/build/src/libespeak-ng/include" \
        "$ESPEAK/src/espeak-ng.c" "$O/espeak-ng.o"
    LIBS=$(find "$O/build" -name '*.a')
    prelink "$PROG/espeak.o" kioku_espeak_tool_main "$O/espeak-ng.o" $LIBS
    glue espeak espeak
    done_step $NAME
fi

# Tesseract's language data (tessdata_fast): TESSDATA_PREFIX (programs.py)
TESSDATA=$WORK/data/tessdata
mkdir -p "$TESSDATA"
# output configs: tsv, hocr, pdf, ... (pytesseract's image_to_data uses tsv)
# and pdf.ttf for searchable PDFs
cp -R "$SRC/tesseract-$TESSERACT_VERSION/tessdata/configs" "$SRC/tesseract-$TESSERACT_VERSION/tessdata/tessconfigs" \
    "$SRC/tesseract-$TESSERACT_VERSION/tessdata/pdf.ttf" "$TESSDATA/"
for lang in $TESSDATA_LANGS; do
    [ -s "$TESSDATA/$lang.traineddata" ] || curl -fsSL --retry 3 -o "$TESSDATA/$lang.traineddata" \
        "https://github.com/tesseract-ocr/tessdata_fast/raw/$TESSDATA_COMMIT/$lang.traineddata"
done

# The library or executable ----------------------------------------------------------
FFLIB_FILES=()
for l in $FFLIBS; do FFLIB_FILES+=("$FFBUILD/lib$l/lib$l.a"); done
CODEC_LIBS=("$PREFIX"/lib/{libtesseract,libleptonica,libpng16,libjpeg,libmp3lame,libvorbisenc,libvorbis,libogg,libopus,libwebpmux,libwebpdemux,libwebp,libsharpyuv,libvpx,libaom,libx264}.a)
OBJS=("$PROG/ffmpeg.o" "$PROG/ffprobe.o" "$PROG/ffmpeg_glue.o")
for p in lame kakasi mecab tesseract espeak cwebp dwebp; do OBJS+=("$PROG/$p.o" "$PROG/${p}_glue.o"); done

LIB=$OUT/lib
rm -rf "$LIB" && mkdir -p "$LIB"
case $TARGET in
ios | ios-sim)
    $CC $CFLAGS -DKIOKU_PYTHON -I"$PYINC" -c "$SHARED/programs/kioku_prog.c" -o "$PROG/kioku_prog.o"
    prelink "$PROG/kiokuprog.o" PyInit__kioku_programs "$PROG/kioku_prog.o" "${OBJS[@]}" \
        "${FFLIB_FILES[@]}" "${CODEC_LIBS[@]}"
    xcrun libtool -static -o "$LIB/libkiokuprog.a" "$PROG/kiokuprog.o"
    ;;
macos)
    $CC $CFLAGS -DKIOKU_PYTHON -I"$PYINC" -c "$SHARED/programs/kioku_prog.c" -o "$PROG/kioku_prog.o"
    $CC -shared -undefined dynamic_lookup -o "$LIB/_kioku_programs.so" "$PROG/kioku_prog.o" \
        "${OBJS[@]}" "${FFLIB_FILES[@]}" "${CODEC_LIBS[@]}" -lz -lbz2 -liconv \
        -lc++ -framework VideoToolbox -framework AudioToolbox -framework CoreMedia \
        -framework CoreVideo -framework CoreFoundation -framework CoreServices
    ;;
android)
    $CC $CFLAGS -DKIOKU_EXECUTABLE -c "$SHARED/programs/kioku_prog.c" -o "$PROG/kioku_prog.o"
    $CXX -pie -o "$LIB/libkiokuprog.so" "$PROG/kioku_prog.o" "${OBJS[@]}" \
        "${FFLIB_FILES[@]}" "${CODEC_LIBS[@]}" -lz -lm -llog -landroid -static-libstdc++
    "$STRIP" --strip-unneeded "$LIB/libkiokuprog.so"
    ;;
esac
ls -la "$LIB"
